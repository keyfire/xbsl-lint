// Unit tests for the pure metadata core (src/metadataCore.ts). No test runner and no vscode:
// plain Node asserts, bundled by esbuild. Run with `npm test` from editors/vscode.

import * as assert from "assert";
import { parseDocument } from "yaml";
import {
  describeMetaNode,
  describeStandardAttr,
  insertItemEdit,
  insertTabularAttrEdit,
  newObjectYaml,
  newSubsystemYaml,
  parseInternals,
} from "../src/metadataCore";

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

function apply(text: string, e: { start: number; end: number; newText: string }): string {
  return text.slice(0, e.start) + e.newText + text.slice(e.end);
}

function parses(text: string): boolean {
  return parseDocument(text, { uniqueKeys: false }).errors.length === 0;
}

const CATALOG = `ВидЭлемента: Справочник
Ид: aaa
Имя: Товар
ОбластьВидимости: ВПроекте
Реквизиты:
    -
        Имя: Наименование
        Длина: 250
    -
        Ид: bbb
        Имя: Цена
        Тип: Число
ТабличныеЧасти:
    -
        Ид: ccc
        Имя: Строки
        Реквизиты:
            -
                Ид: ddd
                Имя: Количество
                Тип: Число
`;

const REGISTER = `ВидЭлемента: РегистрСведений
Ид: rrr
Имя: Курсы
Измерения:
    -
        Ид: m1
        Имя: Валюта
        Тип: Строка
Ресурсы:
    -
        Ид: r1
        Имя: Курс
        Тип: Число
`;

const ENUM = `ВидЭлемента: Перечисление
Ид: eee
Имя: Цвет
Элементы:
    -
        Ид: e1
        Имя: Красный
    -
        Ид: e2
        Имя: Зелёный
`;

const HTTP = `ВидЭлемента: HttpСервис
Ид: hhh
Имя: Апи
КорневойUrl: /api
ШаблоныUrl:
    -
        Имя: Пинг
        Шаблон: /ping
        Методы:
            -
                Метод: GET
                Обработчик: Пинг
`;

const CLIENT_PARAMS = `ВидЭлемента: ПараметрыРаботыКлиента
Ид: ppp
Имя: Настройки
Параметры:
    -
        Имя: Адрес
        Тип: Строка
`;

const attr = (uuid: string, name: string): string[] => [`Ид: ${uuid}`, `Имя: ${name}`, `Тип: Строка`];

// --- parseInternals -----------------------------------------------------------------------

test("parseInternals: реквизиты справочника – имена, типы, смещения", () => {
  const it = parseInternals(CATALOG)!;
  assert.deepStrictEqual(it.attributes.map((a) => a.name), ["Наименование", "Цена"]);
  assert.strictEqual(it.attributes[1].type, "Число");
  assert.ok(typeof it.attributes[0].offset === "number");
});

test("parseInternals: табличная часть несёт свои реквизиты", () => {
  const it = parseInternals(CATALOG)!;
  assert.deepStrictEqual(it.tabulars[0].children!.map((c) => c.name), ["Количество"]);
});

test("parseInternals: измерения и ресурсы регистра", () => {
  const it = parseInternals(REGISTER)!;
  assert.deepStrictEqual(it.dimensions.map((d) => d.name), ["Валюта"]);
  assert.deepStrictEqual(it.resources.map((r) => r.name), ["Курс"]);
});

test("parseInternals: значения перечисления (без типа)", () => {
  const it = parseInternals(ENUM)!;
  assert.deepStrictEqual(it.enumValues.map((v) => v.name), ["Красный", "Зелёный"]);
  assert.strictEqual(it.enumValues[0].type, undefined);
});

test("parseInternals: шаблоны URL с методами", () => {
  const it = parseInternals(HTTP)!;
  assert.strictEqual(it.urlTemplates.length, 1);
  assert.strictEqual(it.urlTemplates[0].name, "Пинг");
  assert.strictEqual(it.urlTemplates[0].type, "/ping");
  assert.deepStrictEqual(it.urlTemplates[0].children!.map((m) => `${m.name}->${m.type}`), ["GET->Пинг"]);
});

test("parseInternals: параметры работы клиента", () => {
  const it = parseInternals(CLIENT_PARAMS)!;
  assert.deepStrictEqual(it.clientParams.map((p) => `${p.name}:${p.type}`), ["Адрес:Строка"]);
});

test("parseInternals: поля структуры", () => {
  const struct = `ВидЭлемента: Структура
Ид: sss
Имя: Данные
Окружение: КлиентИСервер
Поля:
    -
        Имя: Категория
        Тип: Строка
    -
        Имя: Сумма
        Тип: Число
`;
  const it = parseInternals(struct)!;
  assert.deepStrictEqual(it.structFields.map((f) => `${f.name}:${f.type}`), ["Категория:Строка", "Сумма:Число"]);
});

// --- insertItemEdit -----------------------------------------------------------------------

test("insertItemEdit: реквизит в конец существующей секции, не залезая в ТЧ", () => {
  const out = apply(CATALOG, insertItemEdit(CATALOG, "Реквизиты", attr("new-uuid", "Скидка")));
  assert.ok(parses(out), "результат должен парситься");
  const it = parseInternals(out)!;
  assert.deepStrictEqual(it.attributes.map((a) => a.name), ["Наименование", "Цена", "Скидка"]);
  assert.strictEqual(it.attributes[2].type, "Строка");
  assert.strictEqual(it.tabulars[0].name, "Строки");
});

test("insertItemEdit: измерение регистра сохраняет отступ 4/8", () => {
  const edit = insertItemEdit(REGISTER, "Измерения", attr("dim-uuid", "Организация"));
  assert.ok(edit.newText.includes("\n    -\n        Ид: dim-uuid"), edit.newText);
  const it = parseInternals(apply(REGISTER, edit))!;
  assert.deepStrictEqual(it.dimensions.map((d) => d.name), ["Валюта", "Организация"]);
});

test("insertItemEdit: значение перечисления (Ид+Имя, без типа)", () => {
  const out = apply(ENUM, insertItemEdit(ENUM, "Элементы", [`Ид: v3`, `Имя: Синий`]));
  assert.ok(parses(out), "результат должен парситься");
  assert.deepStrictEqual(parseInternals(out)!.enumValues.map((v) => v.name), ["Красный", "Зелёный", "Синий"]);
});

test("insertItemEdit: параметр клиента (Имя+Тип, без Ид)", () => {
  const out = apply(CLIENT_PARAMS, insertItemEdit(CLIENT_PARAMS, "Параметры", [`Имя: Порт`, `Тип: Число`]));
  assert.ok(parses(out), "результат должен парситься");
  assert.deepStrictEqual(parseInternals(out)!.clientParams.map((p) => p.name), ["Адрес", "Порт"]);
});

test("insertItemEdit: табличная часть с вложенными реквизитами", () => {
  const lines = ["Ид: t1", "Имя: Комплект", "Реквизиты:", "    -", "        Ид: a1", "        Имя: Кол", "        Тип: Число"];
  const out = apply(CATALOG, insertItemEdit(CATALOG, "ТабличныеЧасти", lines));
  assert.ok(parses(out), "результат должен парситься");
  const it = parseInternals(out)!;
  assert.deepStrictEqual(it.tabulars.map((t) => t.name), ["Строки", "Комплект"]);
  const added = it.tabulars.find((t) => t.name === "Комплект")!;
  assert.deepStrictEqual(added.children!.map((c) => c.name), ["Кол"]);
});

test("insertTabularAttrEdit: реквизит в существующую секцию табличной части", () => {
  const it = parseInternals(CATALOG)!;
  const edit = insertTabularAttrEdit(CATALOG, it.tabulars[0].offset!, ["Ид: q1", "Имя: Цена", "Тип: Число"]);
  const out = apply(CATALOG, edit);
  assert.ok(parses(out), "результат должен парситься");
  const строки = parseInternals(out)!.tabulars.find((t) => t.name === "Строки")!;
  assert.deepStrictEqual(строки.children!.map((c) => c.name), ["Количество", "Цена"]);
});

test("insertTabularAttrEdit: создаёт секцию Реквизиты у табличной части без неё", () => {
  const doc = `ВидЭлемента: Справочник
Ид: a
Имя: Т
ТабличныеЧасти:
    -
        Ид: t1
        Имя: Пустая
`;
  const it = parseInternals(doc)!;
  const out = apply(doc, insertTabularAttrEdit(doc, it.tabulars[0].offset!, ["Ид: r1", "Имя: Первый", "Тип: Строка"]));
  assert.ok(parses(out), "результат должен парситься");
  assert.deepStrictEqual(parseInternals(out)!.tabulars[0].children!.map((c) => c.name), ["Первый"]);
});

test("insertItemEdit: отсутствующая секция дописывается в конец файла", () => {
  const out = apply(REGISTER, insertItemEdit(REGISTER, "Реквизиты", attr("attr-uuid", "Комментарий")));
  assert.ok(parses(out), "результат должен парситься");
  const it = parseInternals(out)!;
  assert.deepStrictEqual(it.attributes.map((a) => a.name), ["Комментарий"]);
  assert.deepStrictEqual(it.dimensions.map((d) => d.name), ["Валюта"]);
  assert.deepStrictEqual(it.resources.map((r) => r.name), ["Курс"]);
});

// --- newObjectYaml ------------------------------------------------------------------------

test("newObjectYaml: минимальный справочник парсится и несёт Вид/Имя", () => {
  const y = newObjectYaml("Справочник", "obj-uuid", "Клиенты");
  assert.ok(parses(y), "результат должен парситься");
  const doc = parseDocument(y).toJS();
  assert.strictEqual(doc.ВидЭлемента, "Справочник");
  assert.strictEqual(doc.Имя, "Клиенты");
  assert.strictEqual(doc.ОбластьВидимости, "ВПроекте");
});

test("newObjectYaml: доп. строки вида (Окружение общего модуля)", () => {
  const y = newObjectYaml("ОбщийМодуль", "m-uuid", "Утилиты", ["Окружение: Сервер"]);
  assert.ok(parses(y));
  assert.strictEqual(parseDocument(y).toJS().Окружение, "Сервер");
});

test("newObjectYaml: общая форма – вложенный Наследует парсится", () => {
  const y = newObjectYaml("КомпонентИнтерфейса", "f-uuid", "МояФорма", [
    "Наследует:",
    "    Тип: Форма",
    "    Содержимое:",
    "        Тип: Группа",
    "        Компоновка: Вертикальная",
  ]);
  assert.ok(parses(y), "результат должен парситься");
  const doc = parseDocument(y).toJS();
  assert.strictEqual(doc.Наследует.Тип, "Форма");
  assert.strictEqual(doc.Наследует.Содержимое.Тип, "Группа");
});

test("describeMetaNode: объект – заголовок, Ид/Вид только чтение, ОбластьВидимости = select", () => {
  const it = parseInternals(CATALOG)!;
  const d = describeMetaNode(CATALOG, it.rootOffset)!;
  assert.strictEqual(d.title, "Справочник");
  const byKey = Object.fromEntries(d.rows.map((r) => [r.key, r]));
  assert.strictEqual(byKey["Имя"].value, "Товар");
  assert.ok(!byKey["Имя"].readonly);
  assert.ok(byKey["Ид"].readonly);
  assert.ok(byKey["ВидЭлемента"].readonly);
  assert.strictEqual(byKey["ОбластьВидимости"].control, "select");
  assert.ok(!byKey["Реквизиты"], "коллекции не попадают в строки");
});

test("describeMetaNode: поле реквизита – Имя и Тип", () => {
  const it = parseInternals(CATALOG)!;
  const d = describeMetaNode(CATALOG, it.attributes[1].offset!)!;
  assert.strictEqual(d.title, "Цена");
  const keys = d.rows.map((r) => r.key);
  assert.ok(keys.includes("Имя") && keys.includes("Тип"));
});

test("describeMetaNode: Тип поля – комбобокс, Имя – текст", () => {
  const it = parseInternals(CATALOG)!;
  const d = describeMetaNode(CATALOG, it.attributes[1].offset!)!;
  const byKey = Object.fromEntries(d.rows.map((r) => [r.key, r]));
  assert.strictEqual(byKey["Тип"].control, "combo");
  assert.strictEqual(byKey["Тип"].value, "Число");
  assert.strictEqual(byKey["Имя"].control, "text");
});

test("describeMetaNode: Многострочная видна у Строки и скрыта у другого типа", () => {
  const doc = `ВидЭлемента: Справочник
Ид: a
Имя: Т
Реквизиты:
    -
        Ид: b
        Имя: Описание
        Тип: Строка
        Многострочная: Истина
    -
        Ид: c
        Имя: Сумма
        Тип: Число
        Многострочная: Истина
`;
  const it = parseInternals(doc)!;
  const strKeys = describeMetaNode(doc, it.attributes[0].offset!)!.rows.map((r) => r.key);
  assert.ok(strKeys.includes("Многострочная"), "у Строки Многострочная показывается");
  const numKeys = describeMetaNode(doc, it.attributes[1].offset!)!.rows.map((r) => r.key);
  assert.ok(!numKeys.includes("Многострочная"), "у Числа Многострочная скрыта");
});

test("describeStandardAttr: синтетический (нет в yaml) даёт строки спецификации", () => {
  const d = describeStandardAttr(CATALOG, "Справочник", "Код")!;
  assert.strictEqual(d.offset, -1);
  assert.deepStrictEqual(d.rows.map((r) => r.key), ["Тип", "Длина", "Уникальность"]);
  assert.ok(d.rows.every((r) => r.value === ""));
});

test("describeStandardAttr: материализованный берёт свойства из yaml", () => {
  const d = describeStandardAttr(CATALOG, "Справочник", "Наименование")!;
  assert.ok(d.offset >= 0, "материализован – реальное смещение узла");
  const byKey = Object.fromEntries(d.rows.map((r) => [r.key, r]));
  assert.strictEqual(byKey["Длина"].value, "250");
});

test("newSubsystemYaml: парсится, несёт Представление", () => {
  const y = newSubsystemYaml("Продажи");
  assert.ok(parses(y));
  assert.strictEqual(parseDocument(y).toJS().Интерфейс.Представление, "Продажи");
});

// -----------------------------------------------------------------------------

console.log(`\nитого: ${passed} ok, ${failed} fail`);
if (failed > 0) {
  process.exit(1);
}
