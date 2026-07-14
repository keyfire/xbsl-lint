// Разбор внутренней структуры объекта 1С:Элемент (реквизиты, измерения, ресурсы, табличные
// части, значения перечисления, параметры работы клиента, шаблоны URL HTTP-сервиса) и
// генерация точечной вставки нового элемента секции в yaml. Модуль чистый (без vscode), чтобы
// проверяться обычными node-тестами; обвязка дерева/webview – в metadataTree.ts.
//
// Секции – массивы однотипных описаний. Форма описания зависит от секции: реквизит/измерение/
// ресурс – { Ид, Имя, Тип }; значение перечисления – { Ид, Имя }; параметр клиента – { Имя, Тип };
// шаблон URL – { Имя, Шаблон, Методы }. Стандартные реквизиты (Наименование, Код) идут без Ид.

import { isMap, isScalar, isSeq, parseDocument } from "yaml";
import type { Node, YAMLMap } from "yaml";

export interface MetaField {
  name: string;
  type?: string; // Тип / Шаблон / Обработчик – показываем как подпись поля
  offset?: number; // смещение map поля в тексте – для перехода и панели свойств
  children?: MetaField[]; // вложенные (реквизиты табличной части, методы шаблона URL)
}

export interface MetaInternals {
  rootOffset: number;
  attributes: MetaField[]; // Реквизиты
  dimensions: MetaField[]; // Измерения
  resources: MetaField[]; // Ресурсы
  tabulars: MetaField[]; // ТабличныеЧасти (children = реквизиты)
  enumValues: MetaField[]; // Элементы (перечисление)
  clientParams: MetaField[]; // Параметры (ПараметрыРаботыКлиента)
  urlTemplates: MetaField[]; // ШаблоныUrl (children = методы)
  structFields: MetaField[]; // Поля (Структура)
}

export interface TextEdit {
  start: number;
  end: number;
  newText: string;
}

// -- доступ к yaml-узлам ------------------------------------------------------------------

function get(map: unknown, key: string): unknown {
  if (!isMap(map)) {
    return undefined;
  }
  for (const item of (map as YAMLMap).items) {
    if (isScalar(item.key) && String(item.key.value) === key) {
      return item.value ?? undefined;
    }
  }
  return undefined;
}

function prop(map: unknown, key: string): string | undefined {
  const v = get(map, key);
  if (isScalar(v) && v.value !== null && v.value !== undefined) {
    return String(v.value);
  }
  return undefined;
}

function offsetOf(node: unknown): number | undefined {
  const n = node as Node;
  return n && n.range ? n.range[0] : undefined;
}

interface FieldOpts {
  nameKey?: string;
  typeKey?: string;
  childKey?: string;
  childOpts?: FieldOpts;
}

function fieldsOf(seq: unknown, opts: FieldOpts = {}): MetaField[] {
  if (!isSeq(seq)) {
    return [];
  }
  const nameKey = opts.nameKey ?? "Имя";
  const typeKey = opts.typeKey ?? "Тип";
  const out: MetaField[] = [];
  for (const item of seq.items) {
    if (!isMap(item)) {
      continue;
    }
    out.push({
      name: prop(item, nameKey) ?? "?",
      type: prop(item, typeKey),
      offset: offsetOf(item),
      children: opts.childKey ? fieldsOf(get(item, opts.childKey), opts.childOpts ?? {}) : undefined,
    });
  }
  return out;
}

export function parseInternals(text: string): MetaInternals | undefined {
  let root: unknown;
  try {
    root = parseDocument(text, { uniqueKeys: false }).contents ?? undefined;
  } catch {
    return undefined;
  }
  if (!isMap(root)) {
    return undefined;
  }
  return {
    rootOffset: offsetOf(root) ?? 0,
    attributes: fieldsOf(get(root, "Реквизиты")),
    dimensions: fieldsOf(get(root, "Измерения")),
    resources: fieldsOf(get(root, "Ресурсы")),
    tabulars: fieldsOf(get(root, "ТабличныеЧасти"), { childKey: "Реквизиты" }),
    enumValues: fieldsOf(get(root, "Элементы")),
    clientParams: fieldsOf(get(root, "Параметры")),
    urlTemplates: fieldsOf(get(root, "ШаблоныUrl"), {
      typeKey: "Шаблон",
      childKey: "Методы",
      childOpts: { nameKey: "Метод", typeKey: "Обработчик" },
    }),
    structFields: fieldsOf(get(root, "Поля")),
  };
}

// -- описание узла для панели свойств --------------------------------------------------------
//
// Строки-свойства выбранного узла yaml (объект целиком или его поле). Скалярные свойства
// редактируются панелью через propertyEdit (formPreviewCore) по этому же смещению; Ид и
// ВидЭлемента – только для чтения; сложные значения (Реквизиты, Интерфейс ...) не показываются.

export interface MetaPropRow {
  key: string;
  value: string;
  control: "text" | "select" | "tristate" | "combo";
  options?: string[];
  readonly?: boolean;
}

export interface MetaNodeDescription {
  title: string;
  offset: number;
  rows: MetaPropRow[];
}

function scalarStr(node: unknown): string | undefined {
  if (isScalar(node) && node.value !== null && node.value !== undefined) {
    return String(node.value);
  }
  return undefined;
}

function findMapAt(node: unknown, offset: number): YAMLMap | undefined {
  if (isMap(node)) {
    const m = node as YAMLMap;
    if (m.range && m.range[0] === offset) {
      return m;
    }
    for (const item of m.items) {
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

// Варианты значений известных перечислимых свойств метаданных.
function metaOptionsFor(key: string): string[] | undefined {
  if (key === "ОбластьВидимости") {
    return ["ВПроекте", "ВПодсистеме"];
  }
  if (key === "Окружение") {
    return ["Сервер", "Клиент", "КлиентИСервер"];
  }
  return undefined;
}

const READONLY_KEYS = new Set(["Ид", "ВидЭлемента"]);

// Ключи, значение которых – тип данных: показываем комбобоксом (input + datalist). Кандидатов
// (примитивы + <Объект>.Ссылка? + <Перечисление>?) знает только провайдер дерева, он и подаёт
// их в панель; список открытый – значение можно ввести вручную.
const TYPE_KEYS = new Set(["Тип"]);

// Строкоспецифичные свойства реквизита: показываем только когда Тип – Строка. При смене типа на
// другой панель их убирает из yaml (см. applyProp в metadataProps).
const STRING_ONLY_KEYS = new Set(["Многострочная"]);

export function describeMetaNode(text: string, offset: number): MetaNodeDescription | undefined {
  let root: unknown;
  try {
    root = parseDocument(text, { uniqueKeys: false }).contents ?? undefined;
  } catch {
    return undefined;
  }
  const map = findMapAt(root, offset);
  if (!map) {
    return undefined;
  }
  const title = prop(map, "ВидЭлемента") ?? prop(map, "Имя") ?? "?";
  // Строкоспецифичные свойства показываем только для типа Строка (нет Тип у стандартного реквизита –
  // он строковый по умолчанию).
  const fieldType = prop(map, "Тип");
  const isStringField = fieldType === undefined || fieldType === "Строка" || fieldType === "Строка?";
  const rows: MetaPropRow[] = [];
  for (const item of map.items) {
    const key = isScalar(item.key) ? String(item.key.value) : "";
    if (!key) {
      continue;
    }
    if (STRING_ONLY_KEYS.has(key) && !isStringField) {
      continue; // напр. Многострочная у не-строкового типа не показываем
    }
    // Только скалярные свойства; коллекции (Реквизиты, Интерфейс ...) правятся через дерево.
    if (!(isScalar(item.value) || item.value === null || item.value === undefined)) {
      continue;
    }
    const value = scalarStr(item.value) ?? "";
    const readonly = READONLY_KEYS.has(key);
    const options = readonly ? undefined : metaOptionsFor(key);
    const control: MetaPropRow["control"] = readonly
      ? "text"
      : TYPE_KEYS.has(key)
        ? "combo"
        : value === "Истина" || value === "Ложь"
          ? "tristate"
          : options
            ? "select"
            : "text";
    rows.push({
      key,
      value,
      control,
      options: options && value && !options.includes(value) ? [value, ...options] : options,
      readonly: readonly || undefined,
    });
  }
  return { title, offset: map.range ? map.range[0] : offset, rows };
}

// -- стандартные реквизиты ------------------------------------------------------------------
//
// Стандартные (предопределённые платформой) реквизиты по видам: показываются в дереве всегда, даже
// если в yaml их нет. Набор редактируемых скалярных свойств подтверждён по данным проекта (Наименование:
// Длина/Многострочная; Код: Тип/Длина/Уникальность; Автонумерация вложенная – правится прямо в yaml).
// Пустое (синтетическое) свойство при правке материализуется: в Реквизиты дописывается запись
// { Имя: <стандартное имя>, <ключ>: <значение> } (без Ид – как у стандартного реквизита).

export interface StandardAttrSpec {
  name: string;
  rows: Array<{ key: string; control: MetaPropRow["control"]; options?: string[] }>;
}

const SEL_STR_NUM = ["Строка", "Число"];

export const STANDARD_ATTRS: Record<string, StandardAttrSpec[]> = {
  Справочник: [
    { name: "Наименование", rows: [{ key: "Длина", control: "text" }, { key: "Многострочная", control: "tristate" }] },
    {
      name: "Код",
      rows: [
        { key: "Тип", control: "select", options: SEL_STR_NUM },
        { key: "Длина", control: "text" },
        { key: "Уникальность", control: "tristate" },
      ],
    },
  ],
  Документ: [
    {
      name: "Номер",
      rows: [
        { key: "Тип", control: "select", options: SEL_STR_NUM },
        { key: "Длина", control: "text" },
        { key: "Уникальность", control: "tristate" },
      ],
    },
    { name: "Дата", rows: [{ key: "Тип", control: "select", options: ["Дата", "ДатаВремя", "Время"] }] },
  ],
};

// Имена стандартных реквизитов вида (для дерева).
export function standardAttrNames(kind: string): string[] {
  return (STANDARD_ATTRS[kind] ?? []).map((s) => s.name);
}

// Смещение записи реквизита по Имени в секции Реквизиты (материализованный стандартный реквизит),
// иначе undefined (значения по умолчанию, в yaml нет).
export function findAttrOffset(text: string, name: string): number | undefined {
  return parseInternals(text)?.attributes.find((a) => a.name === name)?.offset;
}

// Описание стандартного реквизита для панели: материализован (есть в Реквизиты) – как обычный узел;
// иначе синтетические строки по спецификации (пустые значения; при правке – материализация).
export function describeStandardAttr(text: string, kind: string, name: string): MetaNodeDescription | undefined {
  const spec = (STANDARD_ATTRS[kind] ?? []).find((s) => s.name === name);
  if (!spec) {
    return undefined;
  }
  const offset = findAttrOffset(text, name);
  if (offset !== undefined) {
    return describeMetaNode(text, offset);
  }
  return {
    title: name,
    offset: -1, // синтетический – узла в yaml нет
    rows: spec.rows.map((r) => ({ key: r.key, value: "", control: r.control, options: r.options })),
  };
}

// -- шаблон нового объекта ------------------------------------------------------------------

// Минимальное валидное описание объекта: Вид + Ид + Имя + ОбластьВидимости, плюс доп. строки по
// виду (напр. Окружение у общего модуля, КорневойUrl у HTTP-сервиса). Дальше объект дополняется.
export function newObjectYaml(kind: string, uuid: string, name: string, extraLines: string[] = []): string {
  return (
    [`ВидЭлемента: ${kind}`, `Ид: ${uuid}`, `Имя: ${name}`, `ОбластьВидимости: ВПроекте`, ...extraLines].join("\n") +
    "\n"
  );
}

// Минимальное описание подсистемы (имя подсистемы = имя папки, в yaml его нет).
export function newSubsystemYaml(name: string): string {
  return `Интерфейс:\n    ВключатьВАвтоИнтерфейс: Истина\n    Представление: ${name}\n`;
}

// -- вставка нового элемента секции ---------------------------------------------------------

function lineEndOf(text: string, offset: number): number {
  const nl = text.indexOf("\n", offset);
  return nl === -1 ? text.length : nl;
}

// Отступы элемента секции по первому существующему "-" в теле; иначе – по отступу заголовка.
function detectIndent(bodySlice: string, headerIndentLen: number): { item: string; field: string } {
  const m = /^([ \t]*)-[ \t]*\r?\n([ \t]*)\S/m.exec(bodySlice);
  if (m) {
    return { item: m[1], field: m[2] };
  }
  return { item: " ".repeat(headerIndentLen + 4), field: " ".repeat(headerIndentLen + 8) };
}

const LINE_INDENT = /^([ \t]*)/;

// Точечная вставка нового элемента (набор строк-полей itemLines, напр. ["Ид: ...","Имя: ...",
// "Тип: Строка"]) в конец секции. Разбор чисто текстовый (надёжнее range-ов yaml для блочных
// списков): по заголовку секции и отступам находим конец её тела. Нет секции – дописываем в
// конец файла. undo-безопасно применяется поверх.
export function insertItemEdit(text: string, section: string, itemLines: string[]): TextEdit {
  const body = (item: string, field: string): string =>
    `${item}-\n` + itemLines.map((l) => `${field}${l}`).join("\n");

  const header = new RegExp(`^([ \\t]*)${section}:[ \\t]*\\r?$`, "m").exec(text);
  if (!header) {
    const nl = text.length === 0 || text.endsWith("\n") ? "" : "\n";
    return { start: text.length, end: text.length, newText: `${nl}${section}:\n${body("    ", "        ")}\n` };
  }

  const headerIndentLen = header[1].length;
  const headerLineEnd = lineEndOf(text, header.index);
  let insertAt = headerLineEnd;
  let bodyEnd = headerLineEnd;
  let pos = headerLineEnd;
  while (pos < text.length) {
    const lineStart = pos + 1;
    const lineEnd = lineEndOf(text, lineStart);
    const line = text.slice(lineStart, lineEnd);
    const indentLen = LINE_INDENT.exec(line)![1].length;
    const blank = line.trim() === "";
    if (!blank && indentLen <= headerIndentLen) {
      break;
    }
    if (!blank) {
      insertAt = lineEnd;
      bodyEnd = lineEnd;
    }
    pos = lineEnd;
  }
  const { item, field } = detectIndent(text.slice(headerLineEnd, bodyEnd), headerIndentLen);
  return { start: insertAt, end: insertAt, newText: `\n${body(item, field)}` };
}

// Вставка нового реквизита во ВЛОЖЕННУЮ секцию Реквизиты табличной части. tabularOffset – смещение
// map табличной части (её первый ключ). Границы блока ТЧ вычисляем сами: до первой непустой строки с
// отступом меньше отступа полей ТЧ (следующая ТЧ или другая секция). Обычно секция Реквизиты у ТЧ уже
// есть (создаётся со стартовым реквизитом) – тогда переиспользуем insertItemEdit на подстроке блока;
// если нет – дописываем секцию вложенной в конец содержимого ТЧ.
export function insertTabularAttrEdit(text: string, tabularOffset: number, itemLines: string[]): TextEdit {
  const lineStart = text.lastIndexOf("\n", tabularOffset - 1) + 1;
  const fieldIndent = tabularOffset - lineStart; // столбец полей ТЧ (напр. 8)
  let blockEnd = text.length;
  let pos = lineEndOf(text, tabularOffset);
  while (pos < text.length) {
    const ls = pos + 1;
    const le = lineEndOf(text, ls);
    const line = text.slice(ls, le);
    if (line.trim() !== "" && LINE_INDENT.exec(line)![1].length < fieldIndent) {
      blockEnd = ls;
      break;
    }
    pos = le;
  }
  const block = text.slice(tabularOffset, blockEnd);
  const hasReq = new RegExp(`^[ \\t]{${fieldIndent}}Реквизиты:[ \\t]*\\r?$`, "m").test(block);
  if (hasReq) {
    // Первая (и единственная в блоке ТЧ) секция Реквизиты – это реквизиты этой ТЧ.
    const sub = insertItemEdit(block, "Реквизиты", itemLines);
    return { start: tabularOffset + sub.start, end: tabularOffset + sub.end, newText: sub.newText };
  }
  // Нет секции Реквизиты – дописываем её вложенной в конец содержимого ТЧ.
  const req = " ".repeat(fieldIndent);
  const item = " ".repeat(fieldIndent + 4);
  const field = " ".repeat(fieldIndent + 8);
  let contentEnd = 0;
  let p = 0;
  while (p < block.length) {
    const nl = block.indexOf("\n", p);
    const end = nl === -1 ? block.length : nl;
    if (block.slice(p, end).trim() !== "") {
      contentEnd = end;
    }
    if (nl === -1) {
      break;
    }
    p = nl + 1;
  }
  const body = itemLines.map((l) => `${field}${l}`).join("\n");
  return { start: tabularOffset + contentEnd, end: tabularOffset + contentEnd, newText: `\n${req}Реквизиты:\n${item}-\n${body}` };
}
