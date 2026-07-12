// Предпросмотр формы 1С:Элемент – ДВЕ самостоятельные webview-панели:
//  * "Предпросмотр" – каркас формы по yaml (рендер – formPreviewCore.ts): следует за
//    активным yaml-редактором, живое обновление, масштаб и тема (светлая/тёмная/редактора)
//    в тулбаре, переключаемые вкладки; клик выделяет компонент, Ctrl+клик ведёт к yaml.
//  * "Свойства" – панель выбранного компонента, как в веб-редакторе платформы: открывается
//    отдельной вкладкой (можно перетащить вниз или в сторону), перечисления – списками,
//    Растягивать* – Авто/Истина/Ложь, остальное текстом; правки применяются к yaml
//    точечными заменами (undo работает).
// Выбор компонента и каждая правка позиционируют курсор в yaml-редакторе на изменяемой
// строке (не забирая фокус). Кнопка в заголовке редактора видна только у yaml форм –
// контекст-ключ xbsl.formYaml.

import * as vscode from "vscode";
import { describeNode, esc, NodeDescription, propertyEdit, renderFormPreview } from "./formPreviewCore";

const VIEW_TYPE = "xbslFormPreview";
const PROPS_VIEW_TYPE = "xbslFormProps";
const DEBOUNCE_MS = 300;
const STATE_KEY = "xbsl.formPreview.view";

interface ViewState {
  zoom: number; // проценты
  theme: "light" | "dark" | "editor";
}

const DEFAULT_VIEW: ViewState = { zoom: 125, theme: "light" };

let panel: vscode.WebviewPanel | undefined;
let propsPanel: vscode.WebviewPanel | undefined;
let target: vscode.Uri | undefined;
let timer: NodeJS.Timeout | undefined;
let view: ViewState = DEFAULT_VIEW;
let lastDesc: NodeDescription | undefined;

// Похоже ли содержимое на форму: компонент интерфейса с наследованием и содержимым.
function looksLikeForm(doc: vscode.TextDocument): boolean {
  if (doc.languageId !== "yaml") {
    return false;
  }
  const head = doc.getText(new vscode.Range(0, 0, Math.min(50, doc.lineCount), 0));
  return head.includes("КомпонентИнтерфейса") && doc.getText().includes("Наследует");
}

// -- панель предпросмотра ---------------------------------------------------------------------

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
  #canvas { overflow-x: auto; }
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
  #canvas [data-off]:hover { outline: 1px solid var(--fp-focus); outline-offset: 1px; }
  #canvas .sel { outline: 2px solid var(--fp-focus) !important; outline-offset: 1px; }
  .note { opacity: .7; font-style: italic; margin-top: 12px; }
</style></head>
<body class="theme-${view.theme}">
<div class="bar">
  <select id="theme">${themeOptions}</select>
  <span class="sp"></span>
  <button id="zo" title="&#8722;">&#8722;</button><span class="zv" id="zv">${view.zoom}%</span><button id="zi" title="+">+</button>
</div>
<div id="canvas"><div id="root" style="zoom:${view.zoom / 100}">${body}</div></div>
<script nonce="${nonce}">
  const vsapi = acquireVsCodeApi();
  let zoom = ${view.zoom};
  const state = vsapi.getState() || { tabs: {}, sel: undefined };

  const applyView = () => {
    document.getElementById("root").style.zoom = zoom / 100;
    document.getElementById("zv").textContent = zoom + "%";
    vsapi.postMessage({ type: "view", zoom, theme: document.getElementById("theme").value });
  };
  document.getElementById("zi").addEventListener("click", () => { zoom = Math.min(300, zoom + 25); applyView(); });
  document.getElementById("zo").addEventListener("click", () => { zoom = Math.max(50, zoom - 25); applyView(); });
  document.getElementById("theme").addEventListener("change", (e) => {
    document.body.className = "theme-" + e.target.value;
    applyView();
  });

  function setSelection(off) {
    for (const el of document.querySelectorAll("#canvas .sel")) { el.classList.remove("sel"); }
    state.sel = off;
    vsapi.setState(state);
    if (off === undefined) {
      vsapi.postMessage({ type: "deselect" });
      return;
    }
    const el = document.querySelector('#canvas [data-off="' + off + '"]');
    if (el) { el.classList.add("sel"); }
    vsapi.postMessage({ type: "select", offset: off });
  }

  document.addEventListener("click", (e) => {
    if (e.target.closest(".bar")) { return; }
    const tab = e.target.closest(".tabbtn");
    if (tab) {
      const tabs = tab.closest(".tabs");
      for (const b of tabs.querySelectorAll(":scope > .tabbar > .tabbtn")) { b.classList.toggle("act", b === tab); }
      for (const p of tabs.querySelectorAll(":scope > .tabpage")) { p.classList.toggle("act", p.dataset.tab === tab.dataset.tab); }
      const owner = tabs.getAttribute("data-off");
      if (owner) { state.tabs[owner] = tab.dataset.tab; vsapi.setState(state); }
    }
    const el = e.target.closest("[data-off]");
    if (el) {
      if (e.ctrlKey || e.metaKey) {
        vsapi.postMessage({ type: "reveal", offset: Number(el.dataset.off) });
      } else {
        setSelection(Number(el.dataset.off));
      }
      e.stopPropagation();
    } else if (e.target.closest("#canvas")) {
      setSelection(undefined);
    }
  });

  // После перерисовки: вернуть активные вкладки и выделение из сохранённого состояния.
  for (const [owner, idx] of Object.entries(state.tabs || {})) {
    const tabs = document.querySelector('#canvas .tabs[data-off="' + owner + '"]');
    if (!tabs) { continue; }
    for (const b of tabs.querySelectorAll(":scope > .tabbar > .tabbtn")) { b.classList.toggle("act", b.dataset.tab === idx); }
    for (const p of tabs.querySelectorAll(":scope > .tabpage")) { p.classList.toggle("act", p.dataset.tab === idx); }
  }
  if (state.sel !== undefined && document.querySelector('#canvas [data-off="' + state.sel + '"]')) {
    setSelection(state.sel);
  }
</script></body></html>`;
}

// -- панель свойств -----------------------------------------------------------------------------

function propsShell(nonce: string): string {
  const labels = {
    hint: vscode.l10n.t("Click an element of the wireframe to inspect and edit its properties."),
    auto: vscode.l10n.t("Auto"),
    autoOption: vscode.l10n.t("(auto)"),
    toYaml: vscode.l10n.t("Show in yaml"),
    note: vscode.l10n.t("An empty value or (auto) removes the property from the yaml."),
  };
  return `<!DOCTYPE html>
<html><head><meta charset="utf-8">
<meta http-equiv="Content-Security-Policy" content="default-src 'none'; style-src 'unsafe-inline'; script-src 'nonce-${nonce}';">
<style>
  body { color: var(--vscode-foreground); font-family: var(--vscode-font-family, "Segoe UI", sans-serif);
    font-size: 13px; padding: 8px 12px; margin: 0; overflow-x: hidden; overflow-wrap: anywhere; }
  .ptitle { display: flex; justify-content: space-between; align-items: flex-start; flex-wrap: wrap; gap: 6px 8px; margin-bottom: 10px; }
  .ptype { font-weight: 600; word-break: break-word; overflow-wrap: anywhere; min-width: 0; }
  .plink { background: transparent; border: 1px solid var(--vscode-panel-border); color: var(--vscode-foreground);
    border-radius: 3px; padding: 2px 8px; cursor: pointer; font-size: 11.5px; white-space: nowrap; }
  .prow { margin-bottom: 9px; }
  .pkey { font-size: .85em; opacity: .75; margin-bottom: 2px; word-break: break-word; overflow-wrap: anywhere; }
  input[type=text], select { width: 100%; max-width: 100%; box-sizing: border-box; background: var(--vscode-input-background);
    color: var(--vscode-input-foreground, var(--vscode-foreground)); border: 1px solid var(--vscode-input-border, rgba(128,128,128,.5));
    border-radius: 3px; padding: 3px 7px; font-size: 12.5px; }
  .tri { display: flex; border: 1px solid var(--vscode-input-border, rgba(128,128,128,.5)); border-radius: 3px; overflow: hidden; }
  .tri button { flex: 1; background: transparent; border: none; color: var(--vscode-foreground); padding: 3px 0; cursor: pointer; font-size: 12px; opacity: .75; }
  .tri button.on { background: var(--vscode-button-background); color: var(--vscode-button-foreground); opacity: 1; }
  .pcomplex { opacity: .6; font-style: italic; word-break: break-word; overflow-wrap: anywhere; }
  .pnote { opacity: .55; font-size: .85em; margin-top: 12px; }
  .phint { opacity: .65; font-style: italic; }
</style></head>
<body>
<div id="pane"></div>
<script nonce="${nonce}">
  const vsapi = acquireVsCodeApi();
  const L = ${JSON.stringify(labels)};
  const pane = document.getElementById("pane");

  function field(row, off) {
    if (row.complex) {
      const s = document.createElement("div");
      s.className = "pcomplex";
      s.textContent = row.value;
      return s;
    }
    const send = (value) => vsapi.postMessage({ type: "setProp", offset: off, key: row.key, value });
    if (row.control === "tristate") {
      const box = document.createElement("div");
      box.className = "tri";
      for (const v of [null, "Истина", "Ложь"]) {
        const b = document.createElement("button");
        b.textContent = v === null ? L.auto : v;
        if ((v === null && !row.value) || v === row.value) { b.classList.add("on"); }
        b.addEventListener("click", () => send(v));
        box.appendChild(b);
      }
      return box;
    }
    if (row.control === "select") {
      const sel = document.createElement("select");
      const auto = document.createElement("option");
      auto.value = "";
      auto.textContent = L.autoOption;
      sel.appendChild(auto);
      for (const o of row.options || []) {
        const opt = document.createElement("option");
        opt.value = o;
        opt.textContent = o;
        sel.appendChild(opt);
      }
      sel.value = row.value || "";
      sel.addEventListener("change", () => send(sel.value === "" ? null : sel.value));
      return sel;
    }
    const input = document.createElement("input");
    input.type = "text";
    input.value = row.value;
    const commit = () => {
      if (input.value === row.value) { return; }
      send(input.value === "" ? null : input.value);
    };
    input.addEventListener("keydown", (e) => { if (e.key === "Enter") { commit(); } });
    input.addEventListener("blur", commit);
    return input;
  }

  function renderProps(desc) {
    pane.textContent = "";
    if (!desc) {
      const hint = document.createElement("div");
      hint.className = "phint";
      hint.textContent = L.hint;
      pane.appendChild(hint);
      return;
    }
    const title = document.createElement("div");
    title.className = "ptitle";
    const type = document.createElement("span");
    type.className = "ptype";
    type.textContent = desc.typeName || "?";
    const toYaml = document.createElement("button");
    toYaml.className = "plink";
    toYaml.textContent = L.toYaml;
    toYaml.addEventListener("click", () => vsapi.postMessage({ type: "reveal", offset: desc.offset }));
    title.appendChild(type);
    title.appendChild(toYaml);
    pane.appendChild(title);
    for (const row of desc.rows) {
      const div = document.createElement("div");
      div.className = "prow";
      const cap = document.createElement("div");
      cap.className = "pkey";
      cap.textContent = row.key;
      div.appendChild(cap);
      div.appendChild(field(row, desc.offset));
      pane.appendChild(div);
    }
    const note = document.createElement("div");
    note.className = "pnote";
    note.textContent = L.note;
    pane.appendChild(note);
  }

  window.addEventListener("message", (e) => {
    const m = e.data;
    if (m && m.type === "props") { renderProps(m.desc); }
  });
  renderProps(null);
  vsapi.postMessage({ type: "ready" });
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

function targetDocument(): vscode.TextDocument | undefined {
  if (!target) {
    return undefined;
  }
  return vscode.workspace.textDocuments.find((d) => d.uri.toString() === target!.toString());
}

function render(): void {
  if (!panel || !target) {
    return;
  }
  const doc = targetDocument();
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

// Показать место в yaml-редакторе. При выборе и правках фокус остаётся в панели
// (preserveFocus), по явному "Показать в yaml" / Ctrl+клику – переходит в редактор.
async function revealOffset(offset: number, preserveFocus: boolean): Promise<void> {
  if (!target) {
    return;
  }
  const doc = await vscode.workspace.openTextDocument(target);
  const pos = doc.positionAt(offset);
  const existing = vscode.window.visibleTextEditors.find((e) => e.document.uri.toString() === target!.toString());
  const editor = await vscode.window.showTextDocument(doc, {
    viewColumn: existing?.viewColumn ?? vscode.ViewColumn.One,
    preserveFocus,
    preview: false,
  });
  editor.selection = new vscode.Selection(pos, pos);
  editor.revealRange(new vscode.Range(pos, pos), vscode.TextEditorRevealType.InCenterIfOutsideViewport);
}

// Панель свойств: отдельная вкладка рядом с предпросмотром; пересоздаётся по клику,
// если пользователь её закрыл.
function ensurePropsPanel(context: vscode.ExtensionContext): void {
  if (propsPanel) {
    if (!propsPanel.visible) {
      propsPanel.reveal(propsPanel.viewColumn ?? vscode.ViewColumn.Beside, true);
    }
    return;
  }
  propsPanel = vscode.window.createWebviewPanel(
    PROPS_VIEW_TYPE,
    vscode.l10n.t("Properties"),
    { viewColumn: vscode.ViewColumn.Beside, preserveFocus: true },
    { enableScripts: true, retainContextWhenHidden: true }
  );
  propsPanel.webview.html = propsShell(nonce());
  propsPanel.onDidDispose(() => {
    propsPanel = undefined;
  }, undefined, context.subscriptions);
  propsPanel.webview.onDidReceiveMessage((m) => {
    if (!m) {
      return;
    }
    if (m.type === "reveal" && typeof m.offset === "number") {
      void revealOffset(m.offset, false);
    } else if (m.type === "setProp" && typeof m.offset === "number" && typeof m.key === "string") {
      void applyProp(m.offset, m.key, typeof m.value === "string" ? m.value : null);
    } else if (m.type === "ready" && lastDesc) {
      void propsPanel?.webview.postMessage({ type: "props", desc: lastDesc });
    }
  }, undefined, context.subscriptions);
}

// Выбор компонента: свойства в панель + курсор на строку узла в yaml (фокус не забираем).
function selectNode(context: vscode.ExtensionContext, offset: number): void {
  const doc = targetDocument();
  if (!doc) {
    return;
  }
  lastDesc = describeNode(doc.getText(), offset);
  ensurePropsPanel(context);
  if (propsPanel) {
    propsPanel.title = vscode.l10n.t("Properties") + (lastDesc?.typeName ? ": " + lastDesc.typeName : "");
    void propsPanel.webview.postMessage({ type: "props", desc: lastDesc ?? null });
  }
  void revealOffset(offset, true);
}

function deselectNode(): void {
  lastDesc = undefined;
  if (propsPanel) {
    propsPanel.title = vscode.l10n.t("Properties");
    void propsPanel.webview.postMessage({ type: "props", desc: null });
  }
}

// Правка свойства из панели: точечная замена в документе (undo работает) и курсор
// на изменяемой строке в редакторе.
async function applyProp(offset: number, key: string, value: string | null): Promise<void> {
  const doc = targetDocument();
  if (!doc) {
    return;
  }
  const edit = propertyEdit(doc.getText(), offset, key, value);
  if (!edit) {
    return;
  }
  const we = new vscode.WorkspaceEdit();
  we.replace(doc.uri, new vscode.Range(doc.positionAt(edit.start), doc.positionAt(edit.end)), edit.newText);
  await vscode.workspace.applyEdit(we);
  await revealOffset(Math.min(edit.start + Math.max(edit.newText.length - 1, 0), doc.getText().length), true);
  // Свойства обновляем сразу; каркас перерисуется через onDidChangeTextDocument.
  lastDesc = describeNode(doc.getText(), offset);
  if (propsPanel && lastDesc) {
    void propsPanel.webview.postMessage({ type: "props", desc: lastDesc });
  }
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
      propsPanel?.dispose();
    }, undefined, context.subscriptions);
    panel.webview.onDidReceiveMessage((m) => {
      if (!m) {
        return;
      }
      if (m.type === "reveal" && typeof m.offset === "number") {
        void revealOffset(m.offset, false);
      } else if (m.type === "select" && typeof m.offset === "number") {
        selectNode(context, m.offset);
      } else if (m.type === "deselect") {
        deselectNode();
      } else if (m.type === "view") {
        // Масштаб и тема применяются в самом webview; здесь только запоминаем выбор.
        const next = { zoom: Number(m.zoom), theme: m.theme } as ViewState;
        if (isViewState(next)) {
          view = next;
          void context.globalState.update(STATE_KEY, view);
        }
      }
    }, undefined, context.subscriptions);
  } else {
    panel.reveal(panel.viewColumn ?? vscode.ViewColumn.Beside, true);
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
        if (target?.toString() !== editor.document.uri.toString()) {
          target = editor.document.uri;
          deselectNode();
        }
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
