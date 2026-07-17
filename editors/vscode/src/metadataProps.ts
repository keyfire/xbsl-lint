// Properties panel of a 1C:Element metadata object/field - a webview view in the extension
// sidebar, below the metadata tree and the documentation (like the properties palette in the
// Designer/EDT): the code is not obscured by tabs. Row descriptions come from describeMetaNode
// (metadataCore), edits are applied as targeted replacements via propertyEdit (formPreviewCore) -
// the document is not reformatted, undo works. Ид and ВидЭлемента are shown read-only;
// collections are edited via the tree.

import * as vscode from "vscode";
import { propertyEdit } from "./formPreviewCore";
import { describeMetaNode, describeStandardAttr, findAttrOffset, insertItemEdit, MetaNodeDescription } from "./metadataCore";

const VIEW_TYPE = "xbslMetaProps";

let view: vscode.WebviewView | undefined;
// offset - node offset in yaml; std - a standard attribute (may be synthetic - then offset is
// ignored and an edit materializes a record in Реквизиты).
let target: { uri: vscode.Uri; offset: number; std?: { kind: string; name: string } } | undefined;
let lastDesc: MetaNodeDescription | null = null;
// Supplier of type candidates (from the tree provider) for the Тип combobox; may be absent.
let typeCandidatesFn: (() => Promise<string[]>) | undefined;

function nonce(): string {
  let s = "";
  const alphabet = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789";
  for (let i = 0; i < 24; i++) {
    s += alphabet.charAt(Math.floor(Math.random() * alphabet.length));
  }
  return s;
}

function shell(n: string): string {
  const labels = {
    hint: vscode.l10n.t("Select an object or a field in the tree to see and edit its properties."),
    auto: vscode.l10n.t("Auto"),
    autoOption: vscode.l10n.t("(auto)"),
    toYaml: vscode.l10n.t("Show in yaml"),
    note: vscode.l10n.t("An empty value or (auto) removes the property from the yaml."),
    readonly: vscode.l10n.t("read-only"),
  };
  return `<!DOCTYPE html>
<html><head><meta charset="utf-8">
<meta http-equiv="Content-Security-Policy" content="default-src 'none'; style-src 'unsafe-inline'; script-src 'nonce-${n}';">
<style>
  body { color: var(--vscode-foreground); font-family: var(--vscode-font-family, "Segoe UI", sans-serif);
    font-size: 13px; padding: 8px 12px; margin: 0; overflow-x: hidden; overflow-wrap: anywhere; }
  .ptitle { display: flex; justify-content: space-between; align-items: flex-start; flex-wrap: wrap; gap: 6px 8px; margin-bottom: 10px; }
  .ptype { font-weight: 600; word-break: break-word; overflow-wrap: anywhere; min-width: 0; }
  .plink { background: transparent; border: 1px solid var(--vscode-panel-border); color: var(--vscode-foreground);
    border-radius: 3px; padding: 2px 8px; cursor: pointer; font-size: 11.5px; white-space: nowrap; }
  .prow { margin-bottom: 9px; }
  .pkey { font-size: .85em; opacity: .75; margin-bottom: 2px; word-break: break-word; overflow-wrap: anywhere; }
  .pkey .ro { opacity: .6; font-style: italic; }
  input[type=text], select { width: 100%; max-width: 100%; box-sizing: border-box; background: var(--vscode-input-background);
    color: var(--vscode-input-foreground, var(--vscode-foreground)); border: 1px solid var(--vscode-input-border, rgba(128,128,128,.5));
    border-radius: 3px; padding: 3px 7px; font-size: 12.5px; }
  input[readonly] { opacity: .7; }
  .tri { display: flex; border: 1px solid var(--vscode-input-border, rgba(128,128,128,.5)); border-radius: 3px; overflow: hidden; }
  .tri button { flex: 1; background: transparent; border: none; color: var(--vscode-foreground); padding: 3px 0; cursor: pointer; font-size: 12px; opacity: .75; }
  .tri button.on { background: var(--vscode-button-background); color: var(--vscode-button-foreground); opacity: 1; }
  .pnote { opacity: .55; font-size: .85em; margin-top: 12px; }
  .phint { opacity: .65; font-style: italic; }
  .combo { position: relative; }
  .combo-list { position: absolute; left: 0; right: 0; top: 100%; margin-top: 2px; z-index: 20;
    max-height: 220px; overflow-y: auto; background: var(--vscode-dropdown-background, var(--vscode-input-background));
    border: 1px solid var(--vscode-dropdown-border, var(--vscode-input-border, rgba(128,128,128,.5)));
    border-radius: 3px; box-shadow: 0 2px 8px rgba(0,0,0,.28); }
  .combo-opt { padding: 3px 8px; cursor: pointer; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; font-size: 12.5px; }
  .combo-opt:hover { background: var(--vscode-list-hoverBackground, rgba(128,128,128,.18)); }
  .combo-opt.cur { background: var(--vscode-list-activeSelectionBackground, rgba(38,146,222,.35)); color: var(--vscode-list-activeSelectionForeground, inherit); }
</style></head>
<body>
<div id="pane"></div>
<script nonce="${n}">
  const vsapi = acquireVsCodeApi();
  const L = ${JSON.stringify(labels)};
  const pane = document.getElementById("pane");

  function field(row) {
    const send = (value) => vsapi.postMessage({ type: "setProp", key: row.key, value });
    if (row.readonly) {
      const input = document.createElement("input");
      input.type = "text"; input.value = row.value; input.readOnly = true;
      return input;
    }
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
      auto.value = ""; auto.textContent = L.autoOption;
      sel.appendChild(auto);
      for (const o of row.options || []) {
        const opt = document.createElement("option");
        opt.value = o; opt.textContent = o;
        sel.appendChild(opt);
      }
      sel.value = row.value || "";
      sel.addEventListener("change", () => send(sel.value === "" ? null : sel.value));
      return sel;
    }
    if (row.control === "combo") {
      // Custom combobox: on focus ALL candidates are shown (the native datalist filters by the
      // current value and would show only it), typing filters; a value can also be typed manually.
      const wrap = document.createElement("div");
      wrap.className = "combo";
      const input = document.createElement("input");
      input.type = "text"; input.value = row.value;
      const list = document.createElement("div");
      list.className = "combo-list"; list.style.display = "none";
      const opts = row.options || [];
      let last = row.value; // guard against re-sending the same value
      const commit = (v) => { if (v !== last) { last = v; send(v === "" ? null : v); } };
      const build = (showAll) => {
        const q = showAll ? "" : input.value.trim().toLowerCase();
        list.textContent = "";
        const matches = opts.filter((o) => !q || o.toLowerCase().includes(q));
        if (!matches.length) { list.style.display = "none"; return; }
        for (const o of matches) {
          const it = document.createElement("div");
          it.className = "combo-opt" + (o === input.value ? " cur" : "");
          it.textContent = o;
          // mousedown (before blur) so the click manages to pick the item.
          it.addEventListener("mousedown", (e) => { e.preventDefault(); input.value = o; list.style.display = "none"; commit(o); });
          list.appendChild(it);
        }
        list.style.display = "block";
        const cur = list.querySelector(".combo-opt.cur");
        if (cur) { cur.scrollIntoView({ block: "nearest" }); }
      };
      input.addEventListener("focus", () => build(true));
      input.addEventListener("click", () => build(true));
      input.addEventListener("input", () => build(false));
      input.addEventListener("keydown", (e) => {
        if (e.key === "Enter") { list.style.display = "none"; commit(input.value); }
        else if (e.key === "Escape") { list.style.display = "none"; }
      });
      input.addEventListener("blur", () => { setTimeout(() => { list.style.display = "none"; commit(input.value); }, 150); });
      wrap.appendChild(input); wrap.appendChild(list);
      return wrap;
    }
    const input = document.createElement("input");
    input.type = "text"; input.value = row.value;
    const commit = () => { if (input.value !== row.value) { send(input.value === "" ? null : input.value); } };
    input.addEventListener("keydown", (e) => { if (e.key === "Enter") { commit(); } });
    input.addEventListener("blur", commit);
    return input;
  }

  function render(desc) {
    pane.textContent = "";
    if (!desc) {
      const hint = document.createElement("div");
      hint.className = "phint"; hint.textContent = L.hint;
      pane.appendChild(hint);
      return;
    }
    const title = document.createElement("div");
    title.className = "ptitle";
    const type = document.createElement("span");
    type.className = "ptype"; type.textContent = desc.title || "?";
    const toYaml = document.createElement("button");
    toYaml.className = "plink"; toYaml.textContent = L.toYaml;
    toYaml.addEventListener("click", () => vsapi.postMessage({ type: "reveal" }));
    title.appendChild(type); title.appendChild(toYaml);
    pane.appendChild(title);
    for (const row of desc.rows) {
      const div = document.createElement("div");
      div.className = "prow";
      const cap = document.createElement("div");
      cap.className = "pkey"; cap.textContent = row.key;
      if (row.readonly) { const ro = document.createElement("span"); ro.className = "ro"; ro.textContent = " · " + L.readonly; cap.appendChild(ro); }
      div.appendChild(cap);
      div.appendChild(field(row));
      pane.appendChild(div);
    }
    const note = document.createElement("div");
    note.className = "pnote"; note.textContent = L.note;
    pane.appendChild(note);
  }

  window.addEventListener("message", (e) => {
    const m = e.data;
    if (m && m.type === "props") { render(m.desc); }
  });
  render(null);
  vsapi.postMessage({ type: "ready" });
</script></body></html>`;
}

async function targetText(): Promise<string | undefined> {
  if (!target) {
    return undefined;
  }
  const doc = await vscode.workspace.openTextDocument(target.uri);
  return doc.getText();
}

async function render(): Promise<void> {
  if (!view) {
    return;
  }
  const text = await targetText();
  lastDesc = !text || !target
    ? null
    : (target.std ? describeStandardAttr(text, target.std.kind, target.std.name) : describeMetaNode(text, target.offset)) ?? null;
  // Type rows (combobox) are filled with candidates from the tree provider - the core does not
  // know the project contents.
  if (lastDesc && typeCandidatesFn && lastDesc.rows.some((r) => r.control === "combo")) {
    const candidates = await typeCandidatesFn();
    for (const row of lastDesc.rows) {
      if (row.control === "combo") {
        row.options = candidates;
      }
    }
  }
  // The view's section title is set by the manifest; the selected node is shown as the description.
  view.description = lastDesc ? lastDesc.title : undefined;
  void view.webview.postMessage({ type: "props", desc: lastDesc });
}

async function applyProp(key: string, value: string | null): Promise<void> {
  if (!target) {
    return;
  }
  const doc = await vscode.workspace.openTextDocument(target.uri);
  const text = doc.getText();
  const we = new vscode.WorkspaceEdit();

  // Standard attribute: materialized (present in Реквизиты) - edit its record; synthetic - an
  // edit appends a record { Имя: <name>, <key>: <value> } to Реквизиты (materialization).
  if (target.std) {
    const off = findAttrOffset(text, target.std.name);
    if (off === undefined) {
      if (value === null) {
        return; // nothing to remove from a non-existent record
      }
      const ins = insertItemEdit(text, "Реквизиты", [`Имя: ${target.std.name}`, `${key}: ${value}`]);
      we.insert(target.uri, doc.positionAt(ins.start), ins.newText);
    } else {
      const edit = propertyEdit(text, off, key, value);
      if (!edit) {
        return;
      }
      we.replace(target.uri, new vscode.Range(doc.positionAt(edit.start), doc.positionAt(edit.end)), edit.newText);
    }
    await vscode.workspace.applyEdit(we);
    await render();
    return;
  }

  const edit = propertyEdit(text, target.offset, key, value);
  if (!edit) {
    return;
  }
  we.replace(target.uri, new vscode.Range(doc.positionAt(edit.start), doc.positionAt(edit.end)), edit.newText);
  // Тип changed to a non-string one - remove the string-specific Многострочная property (an edit
  // over the same source text, on a different line - it does not overlap the type edit).
  const newIsString = value === "Строка" || value === "Строка?";
  if (key === "Тип" && value !== null && !newIsString) {
    const strip = propertyEdit(text, target.offset, "Многострочная", null);
    if (strip) {
      we.replace(target.uri, new vscode.Range(doc.positionAt(strip.start), doc.positionAt(strip.end)), strip.newText);
    }
  }
  await vscode.workspace.applyEdit(we);
  await render();
}

async function revealTarget(): Promise<void> {
  if (!target) {
    return;
  }
  const doc = await vscode.workspace.openTextDocument(target.uri);
  // A synthetic standard attribute (no node) - show the object start; otherwise the node's line.
  const offset = target.std ? findAttrOffset(doc.getText(), target.std.name) ?? 0 : Math.max(target.offset, 0);
  const pos = doc.positionAt(offset);
  const editor = await vscode.window.showTextDocument(doc, { preview: false });
  editor.selection = new vscode.Selection(pos, pos);
  editor.revealRange(new vscode.Range(pos, pos), vscode.TextEditorRevealType.InCenterIfOutsideViewport);
}

class MetaPropsViewProvider implements vscode.WebviewViewProvider {
  constructor(private readonly context: vscode.ExtensionContext) {}

  resolveWebviewView(v: vscode.WebviewView): void {
    view = v;
    v.webview.options = { enableScripts: true };
    v.webview.html = shell(nonce());
    v.onDidDispose(
      () => {
        view = undefined;
      },
      undefined,
      this.context.subscriptions
    );
    v.webview.onDidReceiveMessage(
      (m) => {
        if (!m) {
          return;
        }
        if (m.type === "setProp" && typeof m.key === "string") {
          void applyProp(m.key, typeof m.value === "string" ? m.value : null);
        } else if (m.type === "reveal") {
          void revealTarget();
        } else if (m.type === "ready") {
          void view?.webview.postMessage({ type: "props", desc: lastDesc });
        }
      },
      undefined,
      this.context.subscriptions
    );
  }
}

async function ensureView(): Promise<void> {
  if (view) {
    // Expand the sidebar section without stealing focus from the tree.
    view.show(true);
    return;
  }
  // The view is not created yet - focusing the section makes VS Code call the provider;
  // the content arrives with the "ready" message from the webview.
  await vscode.commands.executeCommand(`${VIEW_TYPE}.focus`);
}

type PropsNode = { yamlPath?: string; offset?: number; stdKind?: string; stdName?: string };

// The node qualifies as a panel target: an object/field with an offset or a standard attribute.
function setTarget(node: PropsNode): boolean {
  if (!node.yamlPath) {
    return false;
  }
  if (node.stdKind && node.stdName) {
    target = { uri: vscode.Uri.file(node.yamlPath), offset: node.offset ?? -1, std: { kind: node.stdKind, name: node.stdName } };
    return true;
  }
  if (node.offset !== undefined) {
    target = { uri: vscode.Uri.file(node.yamlPath), offset: node.offset };
    return true;
  }
  return false;
}

// Silent update on tree selection change (mouse, arrows, programmatic reveal):
// the panel follows the selection only when already visible - selecting does not
// open files and does not disturb the sidebar.
export function updatePropsFromSelection(node: PropsNode | undefined): void {
  if (!node || !view || !view.visible) {
    return;
  }
  if (setTarget(node)) {
    void render();
  }
}

// Open the properties panel for a tree node (yamlPath + offset). typeCandidates (from the tree
// provider) fills the Тип combobox; without it the Тип field stays a plain text input.
export function registerMetadataProps(
  context: vscode.ExtensionContext,
  typeCandidates?: () => Promise<string[]>
): void {
  typeCandidatesFn = typeCandidates;
  context.subscriptions.push(
    vscode.window.registerWebviewViewProvider(VIEW_TYPE, new MetaPropsViewProvider(context), {
      webviewOptions: { retainContextWhenHidden: true },
    }),
    vscode.commands.registerCommand("xbsl.metadata.props", async (node?: PropsNode) => {
      if (!node || !setTarget(node)) {
        return;
      }
      await ensureView();
      await render();
    })
  );
}
