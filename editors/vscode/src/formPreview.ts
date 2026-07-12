// Webview-панель "Предпросмотр формы": показывает каркас формы 1С:Элемент по её yaml
// (рендер – в formPreviewCore.ts). Панель одна, следует за активным yaml-редактором,
// обновляется по мере правки (с задержкой); клик по элементу каркаса выделяет его
// yaml-узел в редакторе. Кнопка в заголовке редактора видна только у yaml форм –
// контекст-ключ xbsl.formYaml выставляется при смене активного редактора.

import * as vscode from "vscode";
import { esc, renderFormPreview } from "./formPreviewCore";

const VIEW_TYPE = "xbslFormPreview";
const DEBOUNCE_MS = 300;

let panel: vscode.WebviewPanel | undefined;
let target: vscode.Uri | undefined;
let timer: NodeJS.Timeout | undefined;

// Похоже ли содержимое на форму: компонент интерфейса с наследованием и содержимым.
function looksLikeForm(doc: vscode.TextDocument): boolean {
  if (doc.languageId !== "yaml") {
    return false;
  }
  const head = doc.getText(new vscode.Range(0, 0, Math.min(50, doc.lineCount), 0));
  return head.includes("КомпонентИнтерфейса") && doc.getText().includes("Наследует");
}

function shell(body: string, nonce: string): string {
  return `<!DOCTYPE html>
<html><head><meta charset="utf-8">
<meta http-equiv="Content-Security-Policy" content="default-src 'none'; style-src 'unsafe-inline'; script-src 'nonce-${nonce}';">
<style>
  body { font-family: var(--vscode-font-family); color: var(--vscode-foreground); font-size: 13px; padding: 10px 14px; }
  .form-head { display: flex; align-items: baseline; gap: 10px; margin-bottom: 8px; }
  .form-title { font-size: 1.3em; font-weight: 600; }
  .form-type { opacity: .55; font-size: .85em; }
  .cmdbar { display: flex; gap: 6px; padding: 6px 0 10px; border-bottom: 1px solid var(--vscode-panel-border); margin-bottom: 10px; flex-wrap: wrap; }
  .col { display: flex; flex-direction: column; gap: 6px; align-items: flex-start; }
  .row { display: flex; flex-direction: row; gap: 8px; align-items: flex-start; flex-wrap: wrap; }
  .grp, .card, .unknown, .tabs { position: relative; padding: 10px 8px 8px; border-radius: 4px; min-width: 40px; }
  .grp { border: 1px dashed rgba(128,128,128,.35); }
  .card { border: 1px solid var(--vscode-panel-border); border-radius: 8px; padding: 12px; }
  .card.banner { background: rgba(100,148,237,.12); }
  .unknown { border: 1px solid rgba(128,128,128,.5); }
  .tag { position: absolute; top: -8px; left: 8px; font-size: 9px; opacity: .6; background: var(--vscode-editor-background); padding: 0 4px; border-radius: 3px; white-space: nowrap; }
  .lbl {}
  .ph { opacity: .45; font-style: italic; }
  .chip { font-family: var(--vscode-editor-font-family); font-size: .85em; background: rgba(128,128,128,.16); padding: 0 4px; border-radius: 3px; }
  .sechead { font-weight: 600; font-size: 1.05em; margin-top: 4px; }
  .fld { display: inline-flex; flex-direction: column; gap: 2px; min-width: 120px; }
  .fld-cap { font-size: .85em; opacity: .7; }
  .inp { border: 1px solid var(--vscode-input-border, rgba(128,128,128,.5)); background: var(--vscode-input-background); border-radius: 3px; padding: 3px 7px; display: flex; justify-content: space-between; gap: 8px; }
  .dd { opacity: .6; }
  .chk { display: inline-block; }
  .btn { border: 1px solid var(--vscode-button-background, #0e639c); background: transparent; color: var(--vscode-foreground); border-radius: 3px; padding: 3px 12px; font-size: inherit; cursor: pointer; }
  .btn.primary { background: var(--vscode-button-background); color: var(--vscode-button-foreground); }
  .btn.link { border-color: transparent; color: var(--vscode-textLink-foreground); }
  .img { width: 90px; height: 60px; display: flex; align-items: center; justify-content: center; border: 1px solid var(--vscode-panel-border); border-radius: 4px; font-size: 20px; }
  .htmlbox { border: 1px dashed rgba(128,128,128,.6); border-radius: 4px; min-height: 42px; min-width: 120px; position: relative; padding: 10px 8px 8px;
    background: repeating-linear-gradient(45deg, transparent, transparent 6px, rgba(128,128,128,.09) 6px, rgba(128,128,128,.09) 12px); }
  table.tbl { border-collapse: collapse; }
  .tbl th, .tbl td { border: 1px solid var(--vscode-panel-border); padding: 3px 10px; font-size: .9em; text-align: left; }
  .tbl th { background: rgba(128,128,128,.12); }
  .tbl td { opacity: .5; }
  .tabs { border: none; padding: 0; }
  .tabbar { display: flex; gap: 2px; border-bottom: 1px solid var(--vscode-panel-border); }
  .tabbtn { border: 1px solid transparent; border-bottom: none; background: transparent; color: var(--vscode-foreground); padding: 4px 12px; cursor: pointer; border-radius: 3px 3px 0 0; opacity: .75; }
  .tabbtn.act { border-color: var(--vscode-panel-border); opacity: 1; font-weight: 600; }
  .tabpage { display: none; padding-top: 10px; }
  .tabpage.act { display: block; }
  [data-off]:hover { outline: 1px solid var(--vscode-focusBorder); outline-offset: 1px; }
  .note { opacity: .7; font-style: italic; margin-top: 12px; }
</style></head>
<body>${body}
<script nonce="${nonce}">
  const vsapi = acquireVsCodeApi();
  document.addEventListener("click", (e) => {
    const tab = e.target.closest(".tabbtn");
    if (tab) {
      const tabs = tab.closest(".tabs");
      for (const b of tabs.querySelectorAll(":scope > .tabbar > .tabbtn")) { b.classList.toggle("act", b === tab); }
      for (const p of tabs.querySelectorAll(":scope > .tabpage")) { p.classList.toggle("act", p.dataset.tab === tab.dataset.tab); }
    }
    const el = e.target.closest("[data-off]");
    if (el) {
      vsapi.postMessage({ offset: Number(el.dataset.off) });
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
      if (m && typeof m.offset === "number") {
        void revealOffset(m.offset);
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
