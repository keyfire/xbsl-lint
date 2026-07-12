// Webview-панель "Предпросмотр формы": показывает каркас формы 1С:Элемент по её yaml
// (рендер – в formPreviewCore.ts). Панель одна, следует за активным yaml-редактором,
// обновляется по мере правки (с задержкой); клик по элементу каркаса выделяет его
// yaml-узел в редакторе. В тулбаре панели – масштаб и тема (светлая, как веб-клиент
// платформы, по умолчанию; тёмная; тема редактора) – выбор сохраняется между сессиями.
// Кнопка в заголовке редактора видна только у yaml форм – контекст-ключ xbsl.formYaml.

import * as vscode from "vscode";
import { esc, renderFormPreview } from "./formPreviewCore";

const VIEW_TYPE = "xbslFormPreview";
const DEBOUNCE_MS = 300;
const STATE_KEY = "xbsl.formPreview.view";

interface ViewState {
  zoom: number; // проценты
  theme: "light" | "dark" | "editor";
}

const DEFAULT_VIEW: ViewState = { zoom: 125, theme: "light" };

let panel: vscode.WebviewPanel | undefined;
let target: vscode.Uri | undefined;
let timer: NodeJS.Timeout | undefined;
let view: ViewState = DEFAULT_VIEW;

// Похоже ли содержимое на форму: компонент интерфейса с наследованием и содержимым.
function looksLikeForm(doc: vscode.TextDocument): boolean {
  if (doc.languageId !== "yaml") {
    return false;
  }
  const head = doc.getText(new vscode.Range(0, 0, Math.min(50, doc.lineCount), 0));
  return head.includes("КомпонентИнтерфейса") && doc.getText().includes("Наследует");
}

function shell(body: string, nonce: string): string {
  const themeOptions = [
    { value: "light", label: vscode.l10n.t("Light") },
    { value: "dark", label: vscode.l10n.t("Dark") },
    { value: "editor", label: vscode.l10n.t("Editor theme") },
  ]
    .map((o) => `<option value="${o.value}"${o.value === view.theme ? " selected" : ""}>${esc(o.label)}</option>`)
    .join("");
  return `<!DOCTYPE html>
<html><head><meta charset="utf-8">
<meta http-equiv="Content-Security-Policy" content="default-src 'none'; style-src 'unsafe-inline'; script-src 'nonce-${nonce}';">
<style>
  body.theme-editor {
    --fp-bg: var(--vscode-editor-background); --fp-fg: var(--vscode-foreground);
    --fp-border: var(--vscode-panel-border); --fp-soft: rgba(128,128,128,.16);
    --fp-input-bg: var(--vscode-input-background); --fp-input-border: var(--vscode-input-border, rgba(128,128,128,.5));
    --fp-btn-bg: var(--vscode-button-background); --fp-btn-fg: var(--vscode-button-foreground);
    --fp-link: var(--vscode-textLink-foreground); --fp-focus: var(--vscode-focusBorder);
  }
  body.theme-light {
    --fp-bg: #ffffff; --fp-fg: #1f2328; --fp-border: #d5d9de; --fp-soft: rgba(31,35,40,.07);
    --fp-input-bg: #ffffff; --fp-input-border: #c3c9d0;
    --fp-btn-bg: #1668dc; --fp-btn-fg: #ffffff; --fp-link: #1668dc; --fp-focus: #1668dc;
  }
  body.theme-dark {
    --fp-bg: #1e1e1e; --fp-fg: #e6e6e6; --fp-border: #474747; --fp-soft: rgba(230,230,230,.09);
    --fp-input-bg: #2b2b2b; --fp-input-border: #5a5a5a;
    --fp-btn-bg: #2f81f7; --fp-btn-fg: #ffffff; --fp-link: #58a6ff; --fp-focus: #2f81f7;
  }
  body { background: var(--fp-bg); color: var(--fp-fg); font-family: var(--vscode-font-family, "Segoe UI", sans-serif);
    font-size: 14px; padding: 0 14px 14px; margin: 0; }
  .bar { position: sticky; top: 0; z-index: 10; display: flex; align-items: center; gap: 6px; padding: 6px 0;
    background: var(--fp-bg); border-bottom: 1px solid var(--fp-border); margin-bottom: 10px; }
  .bar select, .bar button { background: var(--fp-bg); color: var(--fp-fg); border: 1px solid var(--fp-border);
    border-radius: 3px; padding: 2px 8px; cursor: pointer; font-size: 12px; }
  .bar .zv { min-width: 44px; text-align: center; font-size: 12px; opacity: .8; }
  .bar .sp { flex: 1; }
  .form-head { display: flex; align-items: baseline; gap: 10px; margin-bottom: 8px; }
  .form-title { font-size: 1.35em; font-weight: 600; }
  .form-type { opacity: .55; font-size: .85em; }
  .cmdbar { display: flex; gap: 6px; padding: 6px 0 10px; border-bottom: 1px solid var(--fp-border); margin-bottom: 10px; flex-wrap: wrap; }
  .col { display: flex; flex-direction: column; gap: 7px; align-items: flex-start; }
  .row { display: flex; flex-direction: row; gap: 9px; align-items: flex-start; flex-wrap: wrap; }
  .form-body { align-items: stretch; }
  .grp, .card, .unknown, .tabs { position: relative; padding: 11px 9px 9px; border-radius: 4px; min-width: 40px; }
  .grp { border: 1px dashed rgba(128,128,128,.45); }
  .card { border: 1px solid var(--fp-border); border-radius: 8px; padding: 13px; box-shadow: 0 1px 3px rgba(0,0,0,.08); }
  .card.banner { background: var(--fp-soft); }
  .unknown { border: 1px solid rgba(128,128,128,.55); }
  .tag { position: absolute; top: -8px; left: 8px; font-size: 9px; opacity: .65; background: var(--fp-bg); padding: 0 4px; border-radius: 3px; white-space: nowrap; }
  .ph { opacity: .45; font-style: italic; }
  .chip { font-family: var(--vscode-editor-font-family, monospace); font-size: .85em; background: var(--fp-soft); padding: 0 4px; border-radius: 3px; }
  .sechead { font-weight: 600; font-size: 1.1em; margin-top: 4px; }
  .fld { display: inline-flex; flex-direction: column; gap: 3px; min-width: 160px; }
  .fld-cap { font-size: .85em; opacity: .75; }
  .inp { border: 1px solid var(--fp-input-border); background: var(--fp-input-bg); border-radius: 4px; padding: 5px 9px; display: flex; justify-content: space-between; gap: 8px; }
  .dd { opacity: .6; }
  .chk { display: inline-block; }
  .btn { border: 1px solid var(--fp-btn-bg); background: transparent; color: var(--fp-fg); border-radius: 4px; padding: 5px 14px; font-size: inherit; cursor: pointer; }
  .btn.primary { background: var(--fp-btn-bg); color: var(--fp-btn-fg); border-color: var(--fp-btn-bg); }
  .btn.link { border-color: transparent; color: var(--fp-link); padding-left: 4px; padding-right: 4px; }
  .img { width: 110px; height: 74px; display: flex; align-items: center; justify-content: center; border: 1px solid var(--fp-border); border-radius: 4px; font-size: 24px; background: var(--fp-soft); }
  .htmlbox { border: 1px dashed rgba(128,128,128,.6); border-radius: 4px; min-height: 48px; min-width: 140px; position: relative; padding: 11px 9px 9px;
    background: repeating-linear-gradient(45deg, transparent, transparent 6px, var(--fp-soft) 6px, var(--fp-soft) 12px); }
  table.tbl { border-collapse: collapse; }
  .tbl th, .tbl td { border: 1px solid var(--fp-border); padding: 4px 12px; font-size: .92em; text-align: left; }
  .tbl th { background: var(--fp-soft); }
  .tbl td { opacity: .5; }
  .tabs { border: none; padding: 0; }
  .tabbar { display: flex; gap: 2px; border-bottom: 1px solid var(--fp-border); }
  .tabbtn { border: 1px solid transparent; border-bottom: none; background: transparent; color: var(--fp-fg); padding: 5px 14px; cursor: pointer; border-radius: 4px 4px 0 0; opacity: .7; font-size: inherit; }
  .tabbtn.act { border-color: var(--fp-border); opacity: 1; font-weight: 600; }
  .tabpage { display: none; padding-top: 10px; }
  .tabpage.act { display: block; }
  [data-off]:hover { outline: 1px solid var(--fp-focus); outline-offset: 1px; }
  .note { opacity: .7; font-style: italic; margin-top: 12px; }
</style></head>
<body class="theme-${view.theme}">
<div class="bar">
  <select id="theme">${themeOptions}</select>
  <span class="sp"></span>
  <button id="zo" title="&#8722;">&#8722;</button><span class="zv" id="zv">${view.zoom}%</span><button id="zi" title="+">+</button>
</div>
<div id="root" style="zoom:${view.zoom / 100}">${body}</div>
<script nonce="${nonce}">
  const vsapi = acquireVsCodeApi();
  let zoom = ${view.zoom};
  const apply = () => {
    document.getElementById("root").style.zoom = zoom / 100;
    document.getElementById("zv").textContent = zoom + "%";
    vsapi.postMessage({ type: "view", zoom, theme: document.getElementById("theme").value });
  };
  document.getElementById("zi").addEventListener("click", () => { zoom = Math.min(300, zoom + 25); apply(); });
  document.getElementById("zo").addEventListener("click", () => { zoom = Math.max(50, zoom - 25); apply(); });
  document.getElementById("theme").addEventListener("change", (e) => {
    document.body.className = "theme-" + e.target.value;
    apply();
  });
  document.addEventListener("click", (e) => {
    if (e.target.closest(".bar")) { return; }
    const tab = e.target.closest(".tabbtn");
    if (tab) {
      const tabs = tab.closest(".tabs");
      for (const b of tabs.querySelectorAll(":scope > .tabbar > .tabbtn")) { b.classList.toggle("act", b === tab); }
      for (const p of tabs.querySelectorAll(":scope > .tabpage")) { p.classList.toggle("act", p.dataset.tab === tab.dataset.tab); }
    }
    const el = e.target.closest("[data-off]");
    if (el) {
      vsapi.postMessage({ type: "reveal", offset: Number(el.dataset.off) });
      e.stopPropagation();
    }
  });
</script></body></html>`;
}

function nonce(): string {
  let s = "";
  const alphabet = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789";
  for (let i = 0; i < 24; i++) {
    s += alphabet.charAt(Math.floor(Math.random() * alphabet.length));
  }
  return s;
}

function render(): void {
  if (!panel || !target) {
    return;
  }
  const doc = vscode.workspace.textDocuments.find((d) => d.uri.toString() === target!.toString());
  if (!doc) {
    return;
  }
  const result = renderFormPreview(doc.getText());
  let body: string;
  if (result.ok) {
    body = result.html;
    panel.title = vscode.l10n.t("Preview: {0}", result.title);
  } else if (result.reason === "parse") {
    body = `<p class="note">${esc(vscode.l10n.t("The yaml does not parse: {0}", result.detail ?? ""))}</p>`;
  } else {
    body = `<p class="note">${esc(vscode.l10n.t("No form content here (Наследует → Содержимое) – open a form yaml."))}</p>`;
  }
  panel.webview.html = shell(body, nonce());
}

function scheduleRender(): void {
  if (timer) {
    clearTimeout(timer);
  }
  timer = setTimeout(() => {
    timer = undefined;
    render();
  }, DEBOUNCE_MS);
}

// Клик в каркасе: выделить yaml-узел компонента в редакторе.
async function revealOffset(offset: number): Promise<void> {
  if (!target) {
    return;
  }
  const doc = await vscode.workspace.openTextDocument(target);
  const pos = doc.positionAt(offset);
  const editor = await vscode.window.showTextDocument(doc, {
    viewColumn: vscode.ViewColumn.One,
    preserveFocus: false,
    preview: false,
  });
  editor.selection = new vscode.Selection(pos, pos);
  editor.revealRange(new vscode.Range(pos, pos), vscode.TextEditorRevealType.InCenterIfOutsideViewport);
}

function isViewState(v: unknown): v is ViewState {
  const s = v as ViewState;
  return !!s && typeof s.zoom === "number" && (s.theme === "light" || s.theme === "dark" || s.theme === "editor");
}

function openPreview(context: vscode.ExtensionContext): void {
  const editor = vscode.window.activeTextEditor;
  if (!editor || editor.document.languageId !== "yaml") {
    void vscode.window.showInformationMessage(vscode.l10n.t("XBSL: open a form yaml (КомпонентИнтерфейса) to preview it."));
    return;
  }
  target = editor.document.uri;
  if (!panel) {
    panel = vscode.window.createWebviewPanel(VIEW_TYPE, "XBSL", vscode.ViewColumn.Beside, {
      enableScripts: true,
      retainContextWhenHidden: true,
    });
    panel.onDidDispose(() => {
      panel = undefined;
    }, undefined, context.subscriptions);
    panel.webview.onDidReceiveMessage((m) => {
      if (m && m.type === "reveal" && typeof m.offset === "number") {
        void revealOffset(m.offset);
      } else if (m && m.type === "view") {
        // Масштаб и тема применяются в самом webview; здесь только запоминаем выбор.
        const next = { zoom: Number(m.zoom), theme: m.theme } as ViewState;
        if (isViewState(next)) {
          view = next;
          void context.globalState.update(STATE_KEY, view);
        }
      }
    }, undefined, context.subscriptions);
  } else {
    panel.reveal(vscode.ViewColumn.Beside, true);
  }
  render();
}

function updateContext(editor: vscode.TextEditor | undefined): void {
  const isForm = !!editor && looksLikeForm(editor.document);
  void vscode.commands.executeCommand("setContext", "xbsl.formYaml", isForm);
}

export function registerFormPreview(context: vscode.ExtensionContext): void {
  const saved = context.globalState.get(STATE_KEY);
  if (isViewState(saved)) {
    view = saved;
  }
  context.subscriptions.push(
    vscode.commands.registerCommand("xbsl.previewForm", () => openPreview(context)),
    vscode.window.onDidChangeActiveTextEditor((editor) => {
      updateContext(editor);
      // Панель следует за активным yaml формы – как предпросмотр Markdown.
      if (panel && editor && looksLikeForm(editor.document)) {
        target = editor.document.uri;
        scheduleRender();
      }
    }),
    vscode.workspace.onDidChangeTextDocument((e) => {
      if (panel && target && e.document.uri.toString() === target.toString()) {
        scheduleRender();
      }
    })
  );
  updateContext(vscode.window.activeTextEditor);
}
