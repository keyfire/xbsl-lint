// Чистая логика навигации (без импорта vscode), чтобы её можно было покрыть модульными тестами
// на обычном Node: модель индекса проекта, который строит линтер, разбор контекста строки
// (регулярные выражения, без полноценного парсера) и поиск по индексу для перехода к определению
// и дополнения.
//
// Схема индекса (зафиксирована): { meta: {root, version}, objects: [...], methods: [...],
// components: [...] }. Все пути – POSIX и относительно meta.root; строки нумеруются с единицы;
// "values" заполняется только у перечислений.

export interface IndexTabular {
  name: string;
  line: number; // нумерация с единицы, внутри yaml объекта
}

export interface IndexLocalType {
  name: string;
  path: string; // POSIX, относительно meta.root
  line: number;
}

export interface IndexValue {
  name: string;
  line: number; // нумерация с единицы, внутри yaml перечисления
}

export interface IndexObject {
  name: string;
  kind: string; // "Справочник" | "Перечисление" | "РегистрСведений" | ...
  path: string; // yaml объекта
  line: number;
  tabular: IndexTabular[];
  local_types: IndexLocalType[];
  family: string[]; // "Ссылка", "Объект", ...
  values: IndexValue[]; // только у перечислений
}

export interface IndexMethod {
  module: string;
  name: string;
  path: string;
  line: number;
  annotations: string[];
}

export interface IndexComponent {
  form: string;
  name: string;
  type: string;
  path: string; // yaml формы
  line: number;
}

export interface IndexReference {
  name: string; // имя используемого символа
  qualifier: string; // идентификатор перед точкой ("" – корень цепочки или голый вызов)
  module: string; // модуль, в котором встречено использование (стем файла)
  path: string; // POSIX, относительно meta.root
  line: number; // нумерация с единицы
  col: number; // нумерация с нуля (для диапазона в редакторе)
}

export interface ProjectIndex {
  meta: { root: string; version?: string };
  objects: IndexObject[];
  methods: IndexMethod[];
  components: IndexComponent[];
  references: IndexReference[];
}

// Точное написание команды индексации в CLI со стороны линтера ещё может измениться.
// Оно задано ТОЛЬКО здесь, упорядоченным списком кандидатов: загрузчик пробует их по очереди,
// и если ни один не дал корректного индекса, навигация просто молчит.
export const INDEX_COMMAND_VARIANTS: ReadonlyArray<(root: string) => string[]> = [
  (root) => ["index", root],
  (root) => ["--index", root],
];

function list(value: unknown): unknown[] {
  return Array.isArray(value) ? value : [];
}

function num(value: unknown): number {
  const n = Number(value);
  return Number.isFinite(n) && n > 0 ? Math.floor(n) : 1;
}

function named(entry: unknown): entry is { name: string } {
  const e = entry as { name?: unknown };
  return !!e && typeof e.name === "string" && e.name.length > 0;
}

// Строги к оболочке (чтобы отчёт линтера или страница ошибки были отвергнуты и вызывающий
// перешёл к следующему варианту команды) и снисходительны к отдельным записям.
export function parseIndex(text: string): ProjectIndex {
  const data = JSON.parse(text) as {
    meta?: { root?: unknown; version?: unknown };
    objects?: unknown;
    methods?: unknown;
    components?: unknown;
  };
  if (!data || typeof data !== "object" || !data.meta || typeof data.meta.root !== "string" || !Array.isArray(data.objects)) {
    throw new Error("нет meta.root или objects – это не индекс проекта");
  }
  const objects: IndexObject[] = (data.objects as unknown[]).filter(named).map((o) => {
    const raw = o as Record<string, unknown>;
    return {
      name: String(raw.name),
      kind: String(raw.kind ?? ""),
      path: String(raw.path ?? ""),
      line: num(raw.line),
      tabular: list(raw.tabular)
        .filter(named)
        .map((t) => ({ name: (t as { name: string }).name, line: num((t as Record<string, unknown>).line) })),
      local_types: list(raw.local_types)
        .filter(named)
        .map((t) => {
          const lt = t as Record<string, unknown>;
          return { name: String(lt.name), path: String(lt.path ?? ""), line: num(lt.line) };
        }),
      family: list(raw.family).map((f) => String(f)),
      values: list(raw.values)
        .filter(named)
        .map((v) => ({ name: (v as { name: string }).name, line: num((v as Record<string, unknown>).line) })),
    };
  });
  const methods: IndexMethod[] = list(data.methods)
    .filter(named)
    .map((m) => {
      const raw = m as Record<string, unknown>;
      return {
        module: String(raw.module ?? ""),
        name: String(raw.name),
        path: String(raw.path ?? ""),
        line: num(raw.line),
        annotations: list(raw.annotations).map((a) => String(a)),
      };
    });
  const components: IndexComponent[] = list(data.components)
    .filter(named)
    .map((c) => {
      const raw = c as Record<string, unknown>;
      return {
        form: String(raw.form ?? ""),
        name: String(raw.name),
        type: String(raw.type ?? ""),
        path: String(raw.path ?? ""),
        line: num(raw.line),
      };
    });
  // references необязательны: старый линтер их не выдаёт – тогда "найти использования" молчит.
  const references: IndexReference[] = list((data as { references?: unknown }).references)
    .filter(named)
    .map((r) => {
      const raw = r as Record<string, unknown>;
      return {
        name: String(raw.name),
        qualifier: String(raw.qualifier ?? ""),
        module: String(raw.module ?? ""),
        path: String(raw.path ?? ""),
        line: num(raw.line),
        col: Math.max(0, Math.trunc(Number(raw.col)) || 0),
      };
    });
  return {
    meta: { root: data.meta.root, version: data.meta.version === undefined ? undefined : String(data.meta.version) },
    objects,
    methods,
    components,
    references,
  };
}

function push<T>(map: Map<string, T[]>, key: string, value: T): void {
  const bucket = map.get(key);
  if (bucket) {
    bucket.push(value);
  } else {
    map.set(key, [value]);
  }
}

// Заранее посчитанные структуры поиска по разобранному индексу.
export class IndexLookup {
  readonly index: ProjectIndex;
  private readonly objectMap = new Map<string, IndexObject>();
  private readonly moduleMethods = new Map<string, IndexMethod[]>();
  private readonly fileMethods = new Map<string, IndexMethod[]>();
  private readonly formComponents = new Map<string, IndexComponent[]>();
  private readonly refsByName = new Map<string, IndexReference[]>();

  constructor(index: ProjectIndex) {
    this.index = index;
    for (const o of index.objects) {
      if (!this.objectMap.has(o.name)) {
        this.objectMap.set(o.name, o);
      }
    }
    for (const m of index.methods) {
      push(this.moduleMethods, m.module, m);
      push(this.fileMethods, m.path, m);
    }
    for (const c of index.components) {
      push(this.formComponents, c.form, c);
    }
    for (const r of index.references) {
      push(this.refsByName, r.name, r);
    }
  }

  objects(): IndexObject[] {
    return this.index.objects;
  }

  objectByName(name: string): IndexObject | undefined {
    return this.objectMap.get(name);
  }

  methodsByModule(module: string): IndexMethod[] {
    return this.moduleMethods.get(module) ?? [];
  }

  method(module: string, name: string): IndexMethod | undefined {
    return this.methodsByModule(module).find((m) => m.name === name);
  }

  // Метод по пути файла модуля (POSIX относительно meta.root) – надёжный способ сказать
  // "в текущем файле", не зависящий от того, как выводится имя модуля.
  methodInFile(path: string, name: string): IndexMethod | undefined {
    return (this.fileMethods.get(path) ?? []).find((m) => m.name === name);
  }

  componentsByForm(form: string): IndexComponent[] {
    return this.formComponents.get(form) ?? [];
  }

  component(form: string, name: string): IndexComponent | undefined {
    return this.componentsByForm(form).find((c) => c.name === name);
  }

  referencesByName(name: string): IndexReference[] {
    return this.refsByName.get(name) ?? [];
  }
}

// ---------------------------------------------------------------------------
// Разбор контекста строки
// ---------------------------------------------------------------------------

const IDENT = "[A-Za-zА-Яа-яЁё_][A-Za-z0-9А-Яа-яЁё_]*";
// Символ, который не может непосредственно предшествовать распознаваемой цепочке
// идентификаторов (иначе мы смотрим на середину чего-то большего).
const NOT_BEFORE = "[^.0-9A-Za-zА-Яа-яЁё_]";

export interface ChainHit {
  parts: string[]; // цепочка идентификаторов через точку, покрывающая позицию
  at: number; // номер сегмента под курсором
}

// Находит цепочку идентификаторов через точку, покрывающую `character` (нумерация с нуля), и
// сегмент, на котором стоит курсор. Возвращает null, если позиция не на идентификаторе.
export function chainAt(lineText: string, character: number): ChainHit | null {
  const re = new RegExp(`${IDENT}(?:\\.${IDENT})*`, "g");
  for (let m = re.exec(lineText); m; m = re.exec(lineText)) {
    const start = m.index;
    const end = start + m[0].length;
    if (character < start) {
      break;
    }
    if (character > end) {
      continue;
    }
    const parts = m[0].split(".");
    let offset = start;
    for (let i = 0; i < parts.length; i++) {
      const segmentEnd = offset + parts[i].length;
      if (character <= segmentEnd) {
        return { parts, at: i };
      }
      offset = segmentEnd + 1; // пропускаем точку
    }
    return { parts, at: parts.length - 1 };
  }
  return null;
}

// ---------------------------------------------------------------------------
// Переход к определению
// ---------------------------------------------------------------------------

export interface Target {
  path: string; // POSIX, относительно meta.root
  line: number; // нумерация с единицы
}

export interface DefinitionQuery {
  languageId: string; // "xbsl" | "yaml"
  lineText: string;
  character: number; // колонка курсора, нумерация с нуля
  fileStem: string; // имя файла без расширения ("ФормаСписка")
  filePath?: string; // путь текущего файла (POSIX относительно meta.root), если известен
}

interface HandlerValue {
  name: string;
  start: number;
  end: number;
}

// Строка обработчика в yaml: `Обработчик: ИмяМетода`.
function matchHandlerLine(lineText: string): HandlerValue | null {
  const m = new RegExp(`^(\\s*Обработчик\\s*:\\s*)(${IDENT})\\s*$`).exec(lineText);
  if (!m) {
    return null;
  }
  return { name: m[2], start: m[1].length, end: m[1].length + m[2].length };
}

function pairedModulePath(filePath: string | undefined): string | undefined {
  if (!filePath || !/\.yaml$/i.test(filePath)) {
    return undefined;
  }
  return filePath.replace(/\.yaml$/i, ".xbsl");
}

// Вид разрешённого символа. Использования (resolveReferences) поддержаны для method/object/component.
export type SymbolKind = "object" | "method" | "component" | "tabular" | "localType" | "enumValue";

export interface SymbolDescriptor {
  kind: SymbolKind;
  name: string;
  module: string; // у метода – его модуль, иначе ""
  form: string; // у компонента – его форма, иначе ""
  path: string; // место определения (POSIX относительно meta.root)
  line: number; // нумерация с единицы
}

// Разрешает символ под позицией в описатель (что это и где определено) или null, если контекст не
// распознан – лучше промолчать, чем прыгнуть не туда. Общая основа перехода к определению и поиска
// использований.
export function resolveSymbol(lookup: IndexLookup, q: DefinitionQuery): SymbolDescriptor | null {
  // yaml: значение `Обработчик:` – это метод парного модуля .xbsl.
  if (q.languageId === "yaml") {
    const handler = matchHandlerLine(q.lineText);
    if (handler) {
      if (q.character < handler.start || q.character > handler.end) {
        return null;
      }
      const paired = pairedModulePath(q.filePath);
      const method =
        (paired ? lookup.methodInFile(paired, handler.name) : undefined) ?? lookup.method(q.fileStem, handler.name);
      return method
        ? { kind: "method", name: handler.name, module: method.module, form: "", path: method.path, line: method.line }
        : null;
    }
  }

  const hit = chainAt(q.lineText, q.character);
  if (!hit) {
    return null;
  }
  const word = hit.parts[hit.at];

  if (hit.at === 0) {
    // Одиночное слово или корень цепочки, называющий объект проекта -> его yaml.
    const obj = lookup.objectByName(word);
    if (obj) {
      return { kind: "object", name: word, module: "", form: "", path: obj.path, line: obj.line };
    }
    // Одиночное имя метода внутри его же модуля.
    if (hit.parts.length === 1 && q.languageId === "xbsl") {
      const method =
        (q.filePath ? lookup.methodInFile(q.filePath, word) : undefined) ?? lookup.method(q.fileStem, word);
      if (method) {
        return { kind: "method", name: word, module: method.module, form: "", path: method.path, line: method.line };
      }
    }
    return null;
  }

  // Компоненты.X -> узел компонента в yaml текущей формы.
  if (hit.at === 1 && hit.parts[0] === "Компоненты") {
    const component = lookup.component(q.fileStem, word);
    return component
      ? { kind: "component", name: word, module: "", form: q.fileStem, path: component.path, line: component.line }
      : null;
  }
  // Компоненты.X.Метод -> метод модуля X.
  if (hit.at === 2 && hit.parts[0] === "Компоненты") {
    const method = lookup.method(hit.parts[1], word);
    return method
      ? { kind: "method", name: word, module: method.module, form: "", path: method.path, line: method.line }
      : null;
  }
  if (hit.at !== 1) {
    return null; // более глубокие цепочки требуют вывода типов – за рамками этого разбора
  }

  const qualifier = hit.parts[hit.at - 1];
  const obj = lookup.objectByName(qualifier);
  if (obj) {
    const localType = obj.local_types.find((t) => t.name === word);
    if (localType) {
      return { kind: "localType", name: word, module: "", form: "", path: localType.path, line: localType.line };
    }
    const tabular = obj.tabular.find((t) => t.name === word);
    if (tabular) {
      return { kind: "tabular", name: word, module: "", form: "", path: obj.path, line: tabular.line };
    }
    const value = obj.values.find((v) => v.name === word);
    if (value) {
      return { kind: "enumValue", name: word, module: "", form: "", path: obj.path, line: value.line };
    }
  }
  // Модуль.Метод (покрывает модули менеджера, чьё имя совпадает с именем объекта).
  const method = lookup.method(qualifier, word);
  return method
    ? { kind: "method", name: word, module: method.module, form: "", path: method.path, line: method.line }
    : null;
}

// Определяет цель перехода для заданной позиции или возвращает null, если контекст не распознан.
export function resolveDefinition(lookup: IndexLookup, q: DefinitionQuery): Target | null {
  const d = resolveSymbol(lookup, q);
  return d ? { path: d.path, line: d.line } : null;
}

export interface RefLocation {
  path: string; // POSIX, относительно meta.root
  line: number; // нумерация с единицы
  col: number; // нумерация с нуля
  length: number; // длина выделяемого имени (0 – для строки объявления)
}

export interface ReferencesQuery extends DefinitionQuery {
  includeDeclaration?: boolean;
}

// Все использования символа под позицией. Поддержаны методы (вызовы в своём модуле, `Модуль.Метод`,
// `Компоненты.Модуль.Метод`, yaml-обработчики), объекты (корень цепочки) и компоненты
// (`Компоненты.Имя`). Сайт объявления исключается; при includeDeclaration добавляется отдельно.
export function resolveReferences(lookup: IndexLookup, q: ReferencesQuery): RefLocation[] {
  const d = resolveSymbol(lookup, q);
  if (!d) {
    return [];
  }
  const length = d.name.length;
  const hits: RefLocation[] = [];
  const add = (r: IndexReference): void => {
    hits.push({ path: r.path, line: r.line, col: r.col, length });
  };
  const refs = lookup.referencesByName(d.name);
  if (d.kind === "method") {
    for (const r of refs) {
      if (r.qualifier === d.module || (r.qualifier === "" && r.module === d.module)) {
        add(r);
      }
    }
  } else if (d.kind === "object") {
    for (const r of refs) {
      if (r.qualifier === "") {
        add(r);
      }
    }
  } else if (d.kind === "component") {
    for (const r of refs) {
      if (r.qualifier === "Компоненты" && r.module === d.form) {
        add(r);
      }
    }
  } else {
    return [];
  }

  // Исключаем сайт объявления из использований; при необходимости добавляем его отдельной записью.
  let out = hits.filter((h) => !(h.path === d.path && h.line === d.line));
  if (q.includeDeclaration) {
    out.push({ path: d.path, line: d.line, col: 0, length: 0 });
  }
  // Уникализируем и упорядочиваем по (path, line, col).
  const seen = new Set<string>();
  const uniq: RefLocation[] = [];
  for (const h of out.sort((a, b) => a.path.localeCompare(b.path) || a.line - b.line || a.col - b.col)) {
    const key = `${h.path}:${h.line}:${h.col}`;
    if (!seen.has(key)) {
      seen.add(key);
      uniq.push(h);
    }
  }
  return uniq;
}

// ---------------------------------------------------------------------------
// Дополнение
// ---------------------------------------------------------------------------

export type CompletionKind =
  | "object"
  | "enum"
  | "family"
  | "field"
  | "tabular"
  | "localType"
  | "enumMember"
  | "method"
  | "component";

export interface CompletionEntry {
  label: string;
  kind: CompletionKind;
  detail?: string;
}

export interface CompletionQuery {
  languageId: string; // "xbsl" | "yaml"
  linePrefix: string; // текст строки до курсора
  fileStem: string;
  textBefore?: string; // текст документа до курсора – для распознавания контекста запроса
  attributesOf?: (objectName: string) => string[] | undefined; // реквизиты объекта из yaml (инъекция)
}

// Стандартные (выбираемые в запросе) поля по виду объекта; реквизиты и табличные части добавляются
// отдельно (реквизиты знает вызывающий – через attributesOf, они не входят в индекс).
const STANDARD_QUERY_FIELDS: Record<string, string[]> = {
  Справочник: ["Ссылка", "Код", "Наименование", "ПометкаУдаления", "Предопределённый"],
  Документ: ["Ссылка", "Номер", "Дата", "Проведён", "ПометкаУдаления"],
};

// Курсор внутри блока запроса? Берём последнее ключевое слово запроса до курсора и считаем баланс
// скобок после него. Ключевое слово двуязычно (Запрос / Query); это эвристика для обычного режима
// (без лексера) – в LSP-режиме контекст запроса определяет лексер линтера (canonical QUERY).
export function isInQuery(textBefore: string): boolean {
  const re = /(?:Запрос|Query)\s*\{/g;
  let open = -1;
  let m: RegExpExecArray | null;
  while ((m = re.exec(textBefore))) {
    open = m.index + m[0].length;
  }
  if (open < 0) {
    return false;
  }
  let depth = 1;
  for (let i = open; i < textBefore.length; i++) {
    if (textBefore[i] === "{") {
      depth++;
    } else if (textBefore[i] === "}") {
      depth--;
      if (depth === 0) {
        return false;
      }
    }
  }
  return true;
}

// Поля таблицы для дополнения в запросе: стандартные поля вида + реквизиты + табличные части.
// Дубли по имени убираем (реквизит может дублировать стандартное имя, напр. Наименование).
export function queryFieldEntries(kind: string, attributes: string[], tabular: string[]): CompletionEntry[] {
  const seen = new Set<string>();
  const entries: CompletionEntry[] = [];
  const add = (label: string, detail: string): void => {
    if (label && !seen.has(label)) {
      seen.add(label);
      entries.push({ label, kind: "field", detail });
    }
  };
  for (const f of STANDARD_QUERY_FIELDS[kind] ?? []) {
    add(f, "стандартное поле");
  }
  for (const a of attributes) {
    add(a, "реквизит");
  }
  for (const t of tabular) {
    add(t, "табличная часть");
  }
  return entries;
}

function matchEnd(prefix: string, pattern: string): RegExpExecArray | null {
  return new RegExp(`(?:^|${NOT_BEFORE})${pattern}$`).exec(prefix);
}

function methodEntry(m: IndexMethod): CompletionEntry {
  return {
    label: m.name,
    kind: "method",
    detail: m.annotations.length > 0 ? m.annotations.join(", ") : "метод",
  };
}

function objectMemberEntries(lookup: IndexLookup, name: string): CompletionEntry[] | null {
  const obj = lookup.objectByName(name);
  const methods = lookup.methodsByModule(name);
  if (!obj && methods.length === 0) {
    return null;
  }
  const entries: CompletionEntry[] = [];
  if (obj) {
    if (obj.kind === "Перечисление") {
      for (const v of obj.values) {
        entries.push({ label: v.name, kind: "enumMember", detail: "значение перечисления" });
      }
    } else {
      for (const f of obj.family) {
        entries.push({ label: f, kind: "family", detail: "тип" });
      }
      for (const t of obj.tabular) {
        entries.push({ label: t.name, kind: "tabular", detail: "табличная часть" });
      }
      for (const t of obj.local_types) {
        entries.push({ label: t.name, kind: "localType", detail: "локальный тип" });
      }
    }
  }
  for (const m of methods) {
    entries.push(methodEntry(m));
  }
  return entries;
}

// Возвращает варианты дополнения для распознанного контекста или null, если позиция нам
// непонятна (тогда работают встроенные подсказки по словам).
export function resolveCompletions(lookup: IndexLookup, q: CompletionQuery): CompletionEntry[] | null {
  const prefix = q.linePrefix;

  // Компоненты.X.<...> -> методы модуля X.
  let m = matchEnd(prefix, `Компоненты\\.(${IDENT})\\.(?:${IDENT})?`);
  if (m) {
    return lookup.methodsByModule(m[1]).map(methodEntry);
  }
  // Компоненты.<...> -> компоненты текущей формы.
  m = matchEnd(prefix, `Компоненты\\.(?:${IDENT})?`);
  if (m) {
    return lookup.componentsByForm(q.fileStem).map((c) => ({
      label: c.name,
      kind: "component" as const,
      detail: c.type,
    }));
  }
  // <Объект>.<...> / <Модуль>.<...> -> семейство типов + табличные части + локальные типы
  // (+ методы модуля); для перечисления – его значения.
  m = matchEnd(prefix, `(${IDENT})\\.(?:${IDENT})?`);
  if (m) {
    // В блоке Запрос{...} после <Таблица>. – поля таблицы (стандартные + реквизиты + ТЧ), а не члены
    // объекта/менеджера. Реквизиты подаёт вызывающий (attributesOf), их нет в индексе.
    if (q.textBefore && isInQuery(q.textBefore)) {
      const table = lookup.objectByName(m[1]);
      if (!table) {
        return null; // неизвестная таблица – молчим (не показываем члены объекта)
      }
      return queryFieldEntries(table.kind, q.attributesOf?.(m[1]) ?? [], table.tabular.map((t) => t.name));
    }
    return objectMemberEntries(lookup, m[1]);
  }
  // yaml: `Тип: <...>` -> имена объектов проекта.
  if (q.languageId === "yaml" && new RegExp(`(?:^|\\s)Тип\\s*:\\s*(?:${IDENT})?$`).test(prefix)) {
    return lookup.objects().map((o) => ({
      label: o.name,
      kind: o.kind === "Перечисление" ? ("enum" as const) : ("object" as const),
      detail: o.kind,
    }));
  }
  return null;
}
