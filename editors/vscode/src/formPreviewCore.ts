// Каркасный предпросмотр формы 1С:Элемент: yaml-описание (КомпонентИнтерфейса) превращается
// в HTML-макет – группы, поля, кнопки, таблицы, вкладки. Это wireframe, а не рендер платформы:
// раскладка и подписи передаются, точные размеры и стили – нет. Модуль чистый (без vscode),
// чтобы рендер проверялся обычными node-тестами; webview-обвязка – в formPreview.ts.
//
// Дерево берётся из Наследует.Содержимое; дочерние узлы живут только в известных свойствах
// (Содержимое, Страницы, Колонки) – остальные вложенные объекты (АбсолютныйЦвет, Источник
// динамического списка и т.п.) являются значениями свойств, а не компонентами.

import { isMap, isScalar, isSeq, parseDocument } from "yaml";
import type { YAMLMap } from "yaml";

export type PreviewResult =
  | { ok: true; html: string; title: string }
  | { ok: false; reason: "parse" | "not-form"; detail?: string };

// -- доступ к yaml-узлам ------------------------------------------------------------------

function get(map: unknown, key: string): unknown {
  if (!isMap(map)) {
    return undefined;
  }
  for (const item of map.items) {
    if (isScalar(item.key) && String(item.key.value) === key) {
      return item.value ?? undefined;
    }
  }
  return undefined;
}

function str(node: unknown): string | undefined {
  if (isScalar(node) && node.value !== null && node.value !== undefined) {
    return String(node.value);
  }
  return undefined;
}

function prop(map: unknown, key: string): string | undefined {
  return str(get(map, key));
}

// Тип компонента без параметров-дженериков: "ПолеВвода<Строка>" -> "ПолеВвода".
function baseType(map: unknown): string | undefined {
  const t = prop(map, "Тип");
  if (!t) {
    return undefined;
  }
  const angle = t.indexOf("<");
  return (angle > 0 ? t.slice(0, angle) : t).trim();
}

// Смещение узла в исходном тексте – для перехода из предпросмотра к yaml.
function offsetOf(map: unknown): number | undefined {
  return isMap(map) && map.range ? map.range[0] : undefined;
}

// -- утилиты HTML ---------------------------------------------------------------------------

export function esc(s: string): string {
  return s.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;");
}

function tagAttrs(node: unknown, cls: string, style?: string): string {
  const off = offsetOf(node);
  const offAttr = off !== undefined ? ` data-off="${off}"` : "";
  const styleAttr = style ? ` style="${esc(style)}"` : "";
  return `class="${cls}"${styleAttr}${offAttr}`;
}

// Значение свойства: биндинг (=Данные.Х) показываем моноширинным чипом, литерал – текстом.
function valueHtml(v: string | undefined, placeholder = ""): string {
  if (v === undefined || v === "") {
    return `<span class="ph">${esc(placeholder)}</span>`;
  }
  if (v.startsWith("=")) {
    return `<code class="chip">${esc(v)}</code>`;
  }
  return esc(v);
}

function isTrue(map: unknown, key: string): boolean {
  return prop(map, key) === "Истина";
}

// -- перевод свойств в стили ----------------------------------------------------------------

function growStyle(node: unknown, horizontalParent: boolean): string {
  const parts: string[] = [];
  const weight = prop(node, "ВесПриРастягивании");
  const growH = isTrue(node, "РастягиватьПоГоризонтали");
  const growV = isTrue(node, "РастягиватьПоВертикали");
  if (horizontalParent ? growH : growV) {
    parts.push(`flex-grow:${weight && /^\d+$/.test(weight) ? weight : 1}`);
  }
  if (horizontalParent ? growV : growH) {
    parts.push("align-self:stretch");
  }
  return parts.join(";");
}

function alignStyle(node: unknown): string {
  const map: Record<string, string> = { Начало: "flex-start", Центр: "center", Конец: "flex-end" };
  const h = prop(node, "ВыравниваниеВГруппеПоГоризонтали");
  const v = prop(node, "ВыравниваниеВГруппеПоВертикали");
  const horizontal = prop(node, "Компоновка") === "Горизонтальная";
  const parts: string[] = [];
  const main = horizontal ? h : v;
  const cross = horizontal ? v : h;
  if (main && map[main]) {
    parts.push(`justify-content:${map[main]}`);
  }
  if (cross && map[cross]) {
    parts.push(`align-items:${map[cross]}`);
  }
  return parts.join(";");
}

// Цвет {Тип: АбсолютныйЦвет, Значение: RGB(595964)} и шрифт {Размер, Начертание/Насыщенность}.
function textStyle(node: unknown): string {
  const parts: string[] = [];
  const rgb = prop(get(node, "Цвет"), "Значение");
  const hex = rgb && /^RGB\(([0-9A-Fa-f]{6})\)$/.exec(rgb.trim());
  if (hex) {
    parts.push(`color:#${hex[1]}`);
  }
  const font = get(node, "Шрифт");
  const size = prop(font, "Размер");
  if (size && /^\d+$/.test(size)) {
    parts.push(`font-size:${size}px`);
  }
  const face = (prop(font, "Начертание") ?? "") + (prop(font, "Насыщенность") ?? "");
  if (face.includes("Жирн")) {
    parts.push("font-weight:600");
  }
  return parts.join(";");
}

// -- рендер компонентов ---------------------------------------------------------------------

function renderChildren(node: unknown, horizontal: boolean): string {
  if (isSeq(node)) {
    return node.items.map((item) => renderComponent(item, horizontal)).join("");
  }
  return renderComponent(node, horizontal);
}

function nameTag(node: unknown, fallback?: string): string {
  const name = prop(node, "Имя") ?? fallback;
  return name ? `<span class="tag">${esc(name)}</span>` : "";
}

function renderGroup(node: unknown, cls: string, extraStyle = ""): string {
  const horizontal = prop(node, "Компоновка") === "Горизонтальная";
  const style = [extraStyle, alignStyle(node)].filter(Boolean).join(";");
  const inner = renderChildren(get(node, "Содержимое"), horizontal);
  return `<div ${tagAttrs(node, `${cls} ${horizontal ? "row" : "col"}`, style)}>${nameTag(node)}${inner}</div>`;
}

function renderTable(node: unknown): string {
  const cols = get(node, "Колонки");
  const heads: string[] = [];
  if (isSeq(cols)) {
    for (const col of cols.items) {
      heads.push(prop(col, "Заголовок") ?? prop(col, "ПолеЗначения") ?? "");
    }
  }
  if (heads.length === 0) {
    heads.push("", "", "");
  }
  const th = heads.map((h) => `<th>${esc(h) || "&nbsp;"}</th>`).join("");
  const placeholderRow = `<tr>${heads.map(() => "<td>···</td>").join("")}</tr>`;
  return `<table ${tagAttrs(node, "tbl")}><thead><tr>${th}</tr></thead><tbody>${placeholderRow}${placeholderRow}</tbody></table>`;
}

function renderTabs(node: unknown, horizontalParent: boolean): string {
  const pages = get(node, "Страницы");
  if (!isSeq(pages)) {
    return renderUnknown(node, "Страницы");
  }
  const bar: string[] = [];
  const bodies: string[] = [];
  pages.items.forEach((page, i) => {
    const title = prop(page, "Заголовок") ?? prop(page, "Имя") ?? `${i + 1}`;
    const off = offsetOf(page);
    bar.push(`<button class="tabbtn${i === 0 ? " act" : ""}" data-tab="${i}"${off !== undefined ? ` data-off="${off}"` : ""}>${esc(title)}</button>`);
    bodies.push(`<div class="tabpage${i === 0 ? " act" : ""}" data-tab="${i}">${renderChildren(get(page, "Содержимое"), false)}</div>`);
  });
  return `<div ${tagAttrs(node, "tabs", growStyle(node, horizontalParent))}><div class="tabbar">${bar.join("")}</div>${bodies.join("")}</div>`;
}

function renderUnknown(node: unknown, type: string): string {
  const inner = renderChildren(get(node, "Содержимое"), false);
  return `<div ${tagAttrs(node, "unknown col")}><span class="tag">${esc(type)}${prop(node, "Имя") ? " · " + esc(prop(node, "Имя")!) : ""}</span>${inner}</div>`;
}

function renderComponent(node: unknown, horizontalParent: boolean): string {
  if (isSeq(node)) {
    return renderChildren(node, horizontalParent);
  }
  if (!isMap(node)) {
    return "";
  }
  const type = baseType(node) ?? "";
  const grow = growStyle(node, horizontalParent);
  switch (type) {
    case "ПроизвольныйШаблонФормы":
      return renderChildren(get(node, "Содержимое"), false);
    case "Группа":
      return renderGroup(node, "grp", grow);
    case "СтандартнаяКарточка": {
      const banner = prop(node, "ВидОтображения") === "Баннер";
      return renderGroup(node, banner ? "card banner" : "card", grow);
    }
    case "Надпись": {
      const text = prop(node, "Значение") ?? prop(node, "Заголовок");
      return `<span ${tagAttrs(node, "lbl", [textStyle(node), grow].filter(Boolean).join(";"))}>${valueHtml(text, "Надпись")}</span>`;
    }
    case "ЗаголовокСекции":
      return `<div ${tagAttrs(node, "sechead", grow)}>${valueHtml(prop(node, "Заголовок"), "Секция")}</div>`;
    case "ПолеВвода":
    case "ПолеВыбора":
    case "ВыборЗначения": {
      const cap = prop(node, "Заголовок");
      const suffix = type === "ПолеВвода" ? "" : `<span class="dd">▾</span>`;
      return (
        `<div ${tagAttrs(node, "fld", grow)}>` +
        (cap ? `<div class="fld-cap">${esc(cap)}</div>` : "") +
        `<div class="inp">${valueHtml(prop(node, "Значение"), "…")}${suffix}</div></div>`
      );
    }
    case "Флажок":
      return `<label ${tagAttrs(node, "chk", grow)}>☐ ${valueHtml(prop(node, "Заголовок"), "Флажок")}</label>`;
    case "Кнопка":
    case "КнопкаФормы":
    case "ОбычнаяКоманда":
    case "НавигационнаяКоманда": {
      const kind = prop(node, "Вид");
      const cls = kind === "Основная" ? "btn primary" : kind === "Дополнительная" ? "btn link" : "btn";
      const title = prop(node, "Заголовок") ?? prop(node, "Представление") ?? prop(node, "Имя");
      return `<button ${tagAttrs(node, cls, grow)}>${valueHtml(title, "Кнопка")}</button>`;
    }
    case "Картинка":
      return `<div ${tagAttrs(node, "img", grow)} title="${esc(prop(node, "Имя") ?? "")}">🖼</div>`;
    case "Таблица":
    case "ПроизвольныйСписок":
      return renderTable(node);
    case "Страницы":
      return renderTabs(node, horizontalParent);
    case "КонтейнерHtml":
    case "РедакторHtml":
      return `<div ${tagAttrs(node, "htmlbox", grow)}><span class="tag">HTML${prop(node, "Имя") ? " · " + esc(prop(node, "Имя")!) : ""}</span></div>`;
    default:
      return renderUnknown(node, type || "?");
  }
}

// Панель команд формы: ОсновнаяКоманда + карты именованных команд (КомандыЗаписи и т.п.).
function renderCommandBar(inherit: unknown): string {
  const buttons: string[] = [];
  const push = (cmd: unknown, fallback: string) => {
    if (!isMap(cmd)) {
      return;
    }
    const title = prop(cmd, "Представление") ?? prop(cmd, "Заголовок") ?? fallback;
    buttons.push(`<button ${tagAttrs(cmd, buttons.length === 0 ? "btn primary" : "btn")}>${esc(title)}</button>`);
  };
  push(get(inherit, "ОсновнаяКоманда"), "Основная команда");
  for (const key of ["КомандыЗаписи", "ДополнительныеКоманды", "Команды"]) {
    const cmds = get(inherit, key);
    if (isMap(cmds)) {
      for (const item of (cmds as YAMLMap).items) {
        push(item.value, isScalar(item.key) ? String(item.key.value) : "");
      }
    } else if (isSeq(cmds)) {
      for (const item of cmds.items) {
        push(item, "");
      }
    }
  }
  return buttons.length > 0 ? `<div class="cmdbar">${buttons.join("")}</div>` : "";
}

// -- вход -----------------------------------------------------------------------------------

// -- панель свойств: описание узла и точечные правки yaml ------------------------------------
//
// Выбранный в каркасе компонент описывается набором строк-свойств для панели (как в
// веб-редакторе платформы), а правка значения превращается в точечную текстовую замену
// по диапазонам yaml-узлов – документ не переформатируется, undo работает.

export interface PropRow {
  key: string;
  value: string; // текущее значение ("" – свойство не задано)
  control: "text" | "select" | "tristate";
  options?: string[]; // для select
  complex?: boolean; // значение-объект: показывается, но не редактируется
}

export interface NodeDescription {
  typeName: string;
  offset: number;
  rows: PropRow[];
}

export interface TextEdit {
  start: number;
  end: number;
  newText: string;
}

// Свойства, которые панель показывает всегда (по виду компонента), в порядке веб-редактора.
const COMMON_PROPS = ["Имя", "Заголовок"];
const LAYOUT_PROPS = [
  "Компоновка",
  "ВыравниваниеВГруппеПоГоризонтали",
  "ВыравниваниеВГруппеПоВертикали",
  "ИнтервалМеждуЭлементамиПоВертикали",
  "ИнтервалМеждуЭлементамиПоГоризонтали",
  "РастягиватьПоГоризонтали",
  "РастягиватьПоВертикали",
  "ШиринаВКолонках",
];
const CURATED: Record<string, string[]> = {
  Группа: [...COMMON_PROPS, ...LAYOUT_PROPS],
  СтандартнаяКарточка: [...COMMON_PROPS, "ВидОтображения", ...LAYOUT_PROPS],
  Надпись: ["Имя", "Значение", "РастягиватьПоГоризонтали", "РастягиватьПоВертикали"],
  ЗаголовокСекции: ["Имя", "Заголовок"],
  ПолеВвода: ["Имя", "Заголовок", "Значение", "РастягиватьПоГоризонтали"],
  ВыборЗначения: ["Имя", "Заголовок", "Значение", "РастягиватьПоГоризонтали"],
  Флажок: ["Имя", "Заголовок", "Значение"],
  Кнопка: ["Имя", "Заголовок", "Вид", "ПриНажатии"],
  Картинка: ["Имя", "Изображение", "МинимальнаяВысота", "МинимальнаяШирина"],
  Страницы: ["Имя", "РастягиватьПоГоризонтали", "РастягиватьПоВертикали"],
};

// Варианты значений перечислимых свойств. Список не исчерпывающий: текущее значение вне
// списка добавляется в options, так что незнакомый вариант не теряется.
function optionsFor(key: string): string[] | undefined {
  if (key === "Компоновка") {
    return ["Вертикальная", "Горизонтальная"];
  }
  if (key.startsWith("Выравнивание")) {
    return ["Начало", "Центр", "Конец"];
  }
  if (key.startsWith("Интервал")) {
    return ["Нулевой", "Половинный", "Одинарный", "Полуторный", "Двойной"];
  }
  if (key === "ШиринаВКолонках") {
    return ["Одинарная", "Полуторная", "Двойная", "Неограниченная"];
  }
  if (key === "Вид") {
    return ["Основная", "Дополнительная"];
  }
  if (key === "ВидОтображения") {
    return ["Баннер"];
  }
  return undefined;
}

function controlFor(key: string, options: string[] | undefined): PropRow["control"] {
  if (key.startsWith("Растягивать")) {
    return "tristate";
  }
  return options ? "select" : "text";
}

// Ключи, под которыми живут дочерние компоненты, – в панель свойств не выводятся.
const CHILD_KEYS = new Set(["Тип", "Содержимое", "Страницы", "Колонки", "Источник"]);

function findMapAt(node: unknown, offset: number): YAMLMap | undefined {
  if (isMap(node)) {
    if (node.range && node.range[0] === offset) {
      return node;
    }
    for (const item of node.items) {
      const found = findMapAt(item.value, offset);
      if (found) {
        return found;
      }
    }
  } else if (isSeq(node)) {
    for (const item of node.items) {
      const found = findMapAt(item, offset);
      if (found) {
        return found;
      }
    }
  }
  return undefined;
}

function parsedContents(text: string): unknown {
  try {
    const doc = parseDocument(text, { uniqueKeys: false });
    return doc.contents ?? undefined;
  } catch {
    return undefined;
  }
}

export function describeNode(text: string, offset: number): NodeDescription | undefined {
  const node = findMapAt(parsedContents(text), offset);
  if (!node) {
    return undefined;
  }
  const typeName = prop(node, "Тип") ?? "";
  const rows: PropRow[] = [];
  const seen = new Set<string>();
  const pushRow = (key: string, value: string, complex = false) => {
    if (seen.has(key)) {
      return;
    }
    seen.add(key);
    const options = optionsFor(key);
    const control = controlFor(key, options);
    const opts = options && value && !options.includes(value) ? [value, ...options] : options;
    rows.push({ key, value, control, options: opts, complex: complex || undefined });
  };
  for (const key of CURATED[baseType(node) ?? ""] ?? [...COMMON_PROPS, ...LAYOUT_PROPS]) {
    pushRow(key, prop(node, key) ?? "");
  }
  // Остальные свойства из yaml: скаляры редактируются, объекты показываются как есть.
  for (const item of node.items) {
    const key = isScalar(item.key) ? String(item.key.value) : "";
    if (!key || CHILD_KEYS.has(key) || seen.has(key)) {
      continue;
    }
    if (isScalar(item.value) || item.value === null || item.value === undefined) {
      pushRow(key, str(item.value) ?? "");
    } else {
      pushRow(key, "{...}", true);
    }
  }
  return { typeName, offset, rows };
}

// Скаляр в yaml-текст: простые значения без кавычек, остальные – двойные кавычки (JSON-эскейп
// корректен для YAML). Биндинги (=Данные.Х) остаются без кавычек.
function encodeScalar(value: string): string {
  if (/^[=A-Za-zА-Яа-яЁё0-9_][A-Za-zА-Яа-яЁё0-9_.,() =\/-]*$/.test(value) && !/\s$/.test(value)) {
    return value;
  }
  return JSON.stringify(value);
}

function lineStartOf(text: string, offset: number): number {
  return text.lastIndexOf("\n", offset - 1) + 1;
}

function lineEndOf(text: string, offset: number): number {
  const nl = text.indexOf("\n", offset);
  return nl === -1 ? text.length : nl;
}

// Правка свойства компонента: value = null снимает свойство (строка удаляется),
// существующий скаляр заменяется по своему диапазону, новое свойство вписывается
// строкой после "Тип" с тем же отступом, что и остальные ключи узла.
export function propertyEdit(text: string, nodeOffset: number, key: string, value: string | null): TextEdit | undefined {
  const node = findMapAt(parsedContents(text), nodeOffset);
  if (!node) {
    return undefined;
  }
  const pair = node.items.find((item) => isScalar(item.key) && String(item.key.value) === key);
  if (value === null) {
    if (!pair || !isScalar(pair.key) || !pair.key.range) {
      return undefined;
    }
    const valueEnd = isScalar(pair.value) && pair.value.range ? pair.value.range[1] : pair.key.range[1];
    const start = lineStartOf(text, pair.key.range[0]);
    const end = Math.min(lineEndOf(text, valueEnd) + 1, text.length);
    return { start, end, newText: "" };
  }
  if (pair) {
    if (isScalar(pair.value) && pair.value.range) {
      return { start: pair.value.range[0], end: pair.value.range[1], newText: encodeScalar(value) };
    }
    if ((pair.value === null || pair.value === undefined) && isScalar(pair.key) && pair.key.range) {
      // "Ключ:" без значения – дописать значение после двоеточия.
      const end = lineEndOf(text, pair.key.range[1]);
      return { start: end, end, newText: " " + encodeScalar(value) };
    }
    return undefined; // значение-объект панелью не правится
  }
  // Свойства нет – вписать после строки с "Тип" (или первой строки узла).
  const anchor = node.items.find((item) => isScalar(item.key) && String(item.key.value) === "Тип") ?? node.items[0];
  if (!anchor || !isScalar(anchor.key) || !anchor.key.range) {
    return undefined;
  }
  const anchorKeyStart = anchor.key.range[0];
  const indent = anchorKeyStart - lineStartOf(text, anchorKeyStart);
  const anchorValueEnd = isScalar(anchor.value) && anchor.value.range ? anchor.value.range[1] : anchor.key.range[1];
  const insertAt = lineEndOf(text, anchorValueEnd);
  return { start: insertAt, end: insertAt, newText: `\n${" ".repeat(indent)}${key}: ${encodeScalar(value)}` };
}

export function renderFormPreview(text: string): PreviewResult {
  let doc;
  try {
    doc = parseDocument(text, { uniqueKeys: false });
  } catch (e) {
    return { ok: false, reason: "parse", detail: e instanceof Error ? e.message : String(e) };
  }
  if (doc.errors.length > 0 && !doc.contents) {
    return { ok: false, reason: "parse", detail: doc.errors[0].message };
  }
  const root = doc.contents;
  const inherit = get(root, "Наследует");
  const content = get(inherit, "Содержимое");
  if (!content) {
    return { ok: false, reason: "not-form" };
  }
  const rawTitle = prop(inherit, "Заголовок");
  const name = prop(root, "Имя") ?? "";
  const baseTypeName = prop(inherit, "Тип") ?? "";
  const titleHtml =
    `<div class="form-head"><span class="form-title">${valueHtml(rawTitle, name)}</span>` +
    `<span class="form-type">${esc(baseTypeName)}</span></div>`;
  const body = titleHtml + renderCommandBar(inherit) + `<div class="form-body col">${renderComponent(content, false)}</div>`;
  return { ok: true, html: body, title: name || rawTitle || "форма" };
}
