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
