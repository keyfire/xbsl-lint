// Unit tests for the pure navigation core (src/navCore.ts) against the frozen index
// schema fixture. No test runner and no dependencies: plain Node asserts, bundled by
// esbuild. Run with `npm test` from editors/vscode.

import * as assert from "assert";
import * as fs from "fs";
import * as path from "path";
import {
  chainAt,
  IndexLookup,
  parseIndex,
  resolveCompletions,
  resolveDefinition,
} from "../src/navCore";

let failed = 0;
let passed = 0;

function test(name: string, fn: () => void): void {
  try {
    fn();
    passed++;
    console.log(`ok   ${name}`);
  } catch (e) {
    failed++;
    console.error(`FAIL ${name}`);
    console.error(e instanceof Error ? e.message : e);
  }
}

// The bundle lives in dist/, the fixture next to the test source.
const fixturePath = path.resolve(__dirname, "..", "test", "fixtures", "index.json");
const lookup = new IndexLookup(parseIndex(fs.readFileSync(fixturePath, "utf8")));

// Cursor helper: 0-based column pointing into `word` inside `line`.
function on(line: string, word: string): number {
  const i = line.indexOf(word);
  assert.ok(i >= 0, `слово "${word}" не найдено в строке "${line}"`);
  return i + 1;
}

// --- parseIndex -------------------------------------------------------------

test("parseIndex: отчёт линтера не принимается за индекс", () => {
  assert.throws(() => parseIndex('{"diagnostics": [], "summary": {}}'));
});

test("parseIndex: мусор не принимается", () => {
  assert.throws(() => parseIndex("xbsllint: error: unrecognized arguments"));
});

test("parseIndex: минимальный индекс нормализуется", () => {
  const idx = parseIndex('{"meta": {"root": "/tmp/p"}, "objects": []}');
  assert.strictEqual(idx.meta.root, "/tmp/p");
  assert.deepStrictEqual(idx.methods, []);
  assert.deepStrictEqual(idx.components, []);
});

// --- chainAt ----------------------------------------------------------------

test("chainAt: сегмент цепочки под курсором", () => {
  const line = "Результат = Программа.ПолучитьДанныеСтраницы(Отбор);";
  assert.deepStrictEqual(chainAt(line, on(line, "Программа")), {
    parts: ["Программа", "ПолучитьДанныеСтраницы"],
    at: 0,
  });
  assert.deepStrictEqual(chainAt(line, on(line, "ПолучитьДанныеСтраницы")), {
    parts: ["Программа", "ПолучитьДанныеСтраницы"],
    at: 1,
  });
  assert.strictEqual(chainAt(line, line.indexOf("=")), null);
});

// --- resolveDefinition: xbsl ------------------------------------------------

const inMain = { languageId: "xbsl", fileStem: "ГлавнаяСтраница", filePath: "Сайт/ГлавнаяСтраница.xbsl" };

test("переход: голое имя объекта / корень цепочки -> yaml объекта", () => {
  const line = "пер Ссылка: Программа.Ссылка;";
  assert.deepStrictEqual(
    resolveDefinition(lookup, { ...inMain, lineText: line, character: on(line, "Программа") }),
    { path: "Сайт/Программа/Программа.yaml", line: 1 }
  );
});

test("переход: Объект.ЛокальныйТип -> объявление типа", () => {
  const line = "пер Данные: Программа.ДанныеКарточки;";
  assert.deepStrictEqual(
    resolveDefinition(lookup, { ...inMain, lineText: line, character: on(line, "ДанныеКарточки") }),
    { path: "Сайт/Программа/Программа.xbsl", line: 12 }
  );
});

test("переход: Объект.ТабличнаяЧасть -> строка в yaml объекта", () => {
  const line = "Т = Программа.Возможности;";
  assert.deepStrictEqual(
    resolveDefinition(lookup, { ...inMain, lineText: line, character: on(line, "Возможности") }),
    { path: "Сайт/Программа/Программа.yaml", line: 58 }
  );
});

test("переход: Перечисление.Значение -> строка значения в yaml", () => {
  const line = "Если Категория = КатегорияПрограммы.Зарплата Тогда";
  assert.deepStrictEqual(
    resolveDefinition(lookup, { ...inMain, lineText: line, character: on(line, "Зарплата") }),
    { path: "Сайт/КатегорияПрограммы/КатегорияПрограммы.yaml", line: 12 }
  );
});

test("переход: Модуль.Метод -> объявление метода", () => {
  const line = "Адрес = ОбщееКлиент.АбсолютныйАдресAPI(Путь);";
  assert.deepStrictEqual(
    resolveDefinition(lookup, { ...inMain, lineText: line, character: on(line, "АбсолютныйАдресAPI") }),
    { path: "Сайт/ОбщееКлиент.xbsl", line: 5 }
  );
});

test("переход: метод менеджера объекта (модуль = имя объекта)", () => {
  const line = "Данные = Программа.ПолучитьДанныеСтраницы(Отбор);";
  assert.deepStrictEqual(
    resolveDefinition(lookup, { ...inMain, lineText: line, character: on(line, "ПолучитьДанныеСтраницы") }),
    { path: "Сайт/Программа/Программа.xbsl", line: 40 }
  );
});

test("переход: голое имя метода в своём модуле", () => {
  const line = "    ОбновитьСписокПрограмм();";
  assert.deepStrictEqual(
    resolveDefinition(lookup, { ...inMain, lineText: line, character: on(line, "ОбновитьСписокПрограмм") }),
    { path: "Сайт/ГлавнаяСтраница.xbsl", line: 27 }
  );
});

test("переход: Компоненты.X -> узел компонента в yaml формы", () => {
  const line = "Компоненты.КнопкаПодробнее.Видимость = Ложь;";
  assert.deepStrictEqual(
    resolveDefinition(lookup, { ...inMain, lineText: line, character: on(line, "КнопкаПодробнее") }),
    { path: "Сайт/ГлавнаяСтраница.yaml", line: 61 }
  );
});

test("переход: Компоненты.X.Метод -> метод модуля X", () => {
  const line = "Компоненты.КарточкаПрограммы.ПриНажатииНазад();";
  assert.deepStrictEqual(
    resolveDefinition(lookup, { ...inMain, lineText: line, character: on(line, "ПриНажатииНазад") }),
    { path: "Сайт/КарточкаПрограммы.xbsl", line: 15 }
  );
});

test("переход: неизвестное имя -> null (молчание)", () => {
  const line = "НеизвестноеИмя = Программа.НетТакогоЧлена;";
  assert.strictEqual(resolveDefinition(lookup, { ...inMain, lineText: line, character: on(line, "НеизвестноеИмя") }), null);
  assert.strictEqual(resolveDefinition(lookup, { ...inMain, lineText: line, character: on(line, "НетТакогоЧлена") }), null);
});

test("переход: член семейства (Ссылка) не имеет определения -> null", () => {
  const line = "пер С: Программа.Ссылка;";
  assert.strictEqual(resolveDefinition(lookup, { ...inMain, lineText: line, character: on(line, "Ссылка;") }), null);
});

test("переход: глубокая цепочка без вывода типов -> null", () => {
  const line = "Имя = Элемент.Программа.Наименование;";
  assert.strictEqual(resolveDefinition(lookup, { ...inMain, lineText: line, character: on(line, "Наименование") }), null);
});

// --- resolveDefinition: yaml ------------------------------------------------

const inMainYaml = { languageId: "yaml", fileStem: "ГлавнаяСтраница", filePath: "Сайт/ГлавнаяСтраница.yaml" };

test("переход yaml: Обработчик: Имя -> метод в парном .xbsl", () => {
  const line = "      Обработчик: ПослеСоздания";
  assert.deepStrictEqual(
    resolveDefinition(lookup, { ...inMainYaml, lineText: line, character: on(line, "ПослеСоздания") }),
    { path: "Сайт/ГлавнаяСтраница.xbsl", line: 3 }
  );
});

test("переход yaml: Обработчик с неизвестным методом -> null, без фоллбека", () => {
  const line = "      Обработчик: Программа";
  assert.strictEqual(
    resolveDefinition(lookup, { ...inMainYaml, lineText: line, character: on(line, "Программа") }),
    null
  );
});

test("переход yaml: Тип: Объект.Ссылка -> yaml объекта (корень цепочки)", () => {
  const line = "    Тип: КэшДанныхСервиса.НаборЗаписей";
  assert.deepStrictEqual(
    resolveDefinition(lookup, { ...inMainYaml, lineText: line, character: on(line, "КэшДанныхСервиса") }),
    { path: "Сайт/КэшДанныхСервиса/КэшДанныхСервиса.yaml", line: 1 }
  );
});

test("переход yaml: голое имя метода не резолвится (только в xbsl)", () => {
  const line = "  Значение: ОбновитьСписокПрограмм";
  assert.strictEqual(
    resolveDefinition(lookup, { ...inMainYaml, lineText: line, character: on(line, "ОбновитьСписокПрограмм") }),
    null
  );
});

// --- resolveCompletions -----------------------------------------------------

function labels(entries: { label: string }[] | null): string[] {
  assert.ok(entries, "ожидался список дополнений, получен null");
  return entries.map((e) => e.label).sort();
}

test("дополнение: после Объект. -> семейство + ТЧ + локальные типы + методы менеджера", () => {
  const entries = resolveCompletions(lookup, { ...inMain, linePrefix: "Данные = Программа." });
  assert.deepStrictEqual(labels(entries), [
    "Возможности",
    "Выборка",
    "ДанныеКарточки",
    "Объект",
    "ПолучитьДанныеСтраницы",
    "Ссылка",
    "Тарифы",
  ]);
  const kinds = new Map(entries!.map((e) => [e.label, e.kind]));
  assert.strictEqual(kinds.get("Ссылка"), "family");
  assert.strictEqual(kinds.get("Возможности"), "tabular");
  assert.strictEqual(kinds.get("ДанныеКарточки"), "localType");
  assert.strictEqual(kinds.get("ПолучитьДанныеСтраницы"), "method");
});

test("дополнение: частично набранный член после точки не меняет список", () => {
  const entries = resolveCompletions(lookup, { ...inMain, linePrefix: "Данные = Программа.Пол" });
  assert.ok(labels(entries).includes("ПолучитьДанныеСтраницы"));
});

test("дополнение: после Перечисление. -> значения", () => {
  const entries = resolveCompletions(lookup, { ...inMain, linePrefix: "Категория = КатегорияПрограммы." });
  assert.deepStrictEqual(labels(entries), ["Бухгалтерия", "Зарплата", "Отраслевые"]);
  assert.ok(entries!.every((e) => e.kind === "enumMember"));
});

test("дополнение: после Компоненты. -> компоненты текущей формы", () => {
  const entries = resolveCompletions(lookup, { ...inMain, linePrefix: "Компоненты." });
  assert.deepStrictEqual(labels(entries), ["КнопкаПодробнее", "СписокПрограмм"]);
  assert.strictEqual(entries![0].kind, "component");
});

test("дополнение: после Компоненты.X. -> методы модуля X", () => {
  const entries = resolveCompletions(lookup, { ...inMain, linePrefix: "Компоненты.КарточкаПрограммы." });
  assert.deepStrictEqual(labels(entries), ["ПриНажатииНазад"]);
  assert.strictEqual(entries![0].kind, "method");
});

test("дополнение yaml: после Тип: -> имена объектов проекта с видом", () => {
  const entries = resolveCompletions(lookup, { ...inMainYaml, linePrefix: "    Тип: " });
  assert.deepStrictEqual(labels(entries), ["ВидПолезного", "КатегорияПрограммы", "КэшДанныхСервиса", "Программа"]);
  const byLabel = new Map(entries!.map((e) => [e.label, e]));
  assert.strictEqual(byLabel.get("КатегорияПрограммы")!.kind, "enum");
  assert.strictEqual(byLabel.get("Программа")!.detail, "Справочник");
});

test("дополнение: Тип: в xbsl не срабатывает", () => {
  assert.strictEqual(resolveCompletions(lookup, { ...inMain, linePrefix: "    Тип: " }), null);
});

test("дополнение: неизвестный контекст -> null (не мешаем словарному)", () => {
  assert.strictEqual(resolveCompletions(lookup, { ...inMain, linePrefix: "Результат = " }), null);
  assert.strictEqual(resolveCompletions(lookup, { ...inMain, linePrefix: "Значение = Переменная." }), null);
  assert.strictEqual(resolveCompletions(lookup, { ...inMain, linePrefix: "А.Б." }), null);
});

// -----------------------------------------------------------------------------

console.log(`\nитого: ${passed} ok, ${failed} fail`);
if (failed > 0) {
  process.exit(1);
}
