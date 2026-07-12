// Тесты каркасного рендера форм: yaml -> HTML. Запуск обычным node (см. npm test).

import { describeNode, propertyEdit, renderFormPreview } from "../src/formPreviewCore";

let failures = 0;

function check(name: string, cond: boolean): void {
  if (cond) {
    console.log(`ok   ${name}`);
  } else {
    failures++;
    console.error(`FAIL ${name}`);
  }
}

const FORM = `
ВидЭлемента: КомпонентИнтерфейса
Ид: 00000000-0000-4000-8000-000000000001
Имя: ТестоваяФорма
Наследует:
    Тип: Форма<Строка?>
    Заголовок: Ввод значения
    ОсновнаяКоманда:
        Тип: ОбычнаяКоманда
        Обработчик: ВыполнитьЗаписать
        Представление: Записать
    Содержимое:
        Тип: ПроизвольныйШаблонФормы
        Содержимое:
            Тип: Группа
            Компоновка: Вертикальная
            Содержимое:
                -
                    Тип: Надпись
                    Значение: "Введите код:"
                    Цвет:
                        Тип: АбсолютныйЦвет
                        Значение: RGB(595964)
                -
                    Тип: ПолеВвода<Строка>
                    Имя: ПолеКод
                    Заголовок: Код
                    Значение: =Код
                -
                    Тип: Страницы
                    Страницы:
                        -
                            Имя: СтраницаОдин
                            Заголовок: Первая
                            Содержимое:
                                Тип: Флажок
                                Заголовок: Включено
                        -
                            Имя: СтраницаДва
                            Заголовок: Вторая
                            Содержимое:
                                Тип: Таблица<Неопределено>
                                Колонки:
                                    -
                                        Тип: СтандартнаяКолонкаТаблицы<Неопределено>
                                        Заголовок: Наименование
                -
                    Тип: Группа
                    Компоновка: Горизонтальная
                    ВыравниваниеВГруппеПоГоризонтали: Конец
                    Содержимое:
                        -
                            Тип: Кнопка
                            Вид: Основная
                            Заголовок: "Активировать"
`;

const result = renderFormPreview(FORM);
check("форма разбирается", result.ok);
if (result.ok) {
  const html = result.html;
  check("заголовок формы", html.includes("Ввод значения"));
  check("команда формы в панели команд", html.includes("Записать"));
  check("надпись с литералом", html.includes("Введите код:"));
  check("цвет надписи из АбсолютныйЦвет", html.includes("color:#595964"));
  check("поле ввода: подпись", html.includes("Код") && html.includes('class="fld'));
  check("биндинг чипом", html.includes("=Код") && html.includes('class="chip"'));
  check("вкладки: две кнопки", (html.match(/class="tabbtn/g) ?? []).length === 2);
  check("вкладки: заголовки", html.includes("Первая") && html.includes("Вторая"));
  check("таблица: колонка", html.includes("<th>Наименование</th>"));
  check("кнопка Основная = primary", html.includes('btn primary'));
  check("горизонтальная группа row", html.includes('grp row'));
  check("выравнивание Конец", html.includes("justify-content:flex-end"));
  check("узлы кликабельны (data-off)", html.includes("data-off="));
  check("нет сырых < из значений", !html.includes("Форма<Строка?>"));
}

const notForm = renderFormPreview("Ид: 1\nИмя: Просто\n");
check("не-форма распознана", !notForm.ok && notForm.reason === "not-form");

const broken = renderFormPreview("Имя: [незакрытый\n  список");
check("битый yaml: аккуратный отказ без исключения", !broken.ok);

// -- панель свойств: описание узла и точечные правки --------------------------------------

const apply = (text: string, edit: { start: number; end: number; newText: string } | undefined): string =>
  edit ? text.slice(0, edit.start) + edit.newText + text.slice(edit.end) : text;

const groupOff = FORM.indexOf("Тип: Группа");
const desc = describeNode(FORM, groupOff);
check("описание узла: тип", !!desc && desc.typeName === "Группа");
const layoutRow = desc?.rows.find((r) => r.key === "Компоновка");
check("описание узла: Компоновка select со значением", layoutRow?.control === "select" && layoutRow?.value === "Вертикальная");
const stretchRow = desc?.rows.find((r) => r.key === "РастягиватьПоГоризонтали");
check("описание узла: Растягивать tristate, не задано", stretchRow?.control === "tristate" && stretchRow?.value === "");

const replaced = apply(FORM, propertyEdit(FORM, groupOff, "Компоновка", "Горизонтальная"));
check("правка: замена значения", replaced.includes("Компоновка: Горизонтальная") && !replaced.includes("Компоновка: Вертикальная"));
check("правка: результат парсится", renderFormPreview(replaced).ok);

const inserted = apply(FORM, propertyEdit(FORM, groupOff, "РастягиватьПоГоризонтали", "Истина"));
check("правка: вставка нового свойства", inserted.includes("РастягиватьПоГоризонтали: Истина"));
const insertedDesc = describeNode(inserted, inserted.indexOf("Тип: Группа"));
check("правка: вставленное свойство читается назад", insertedDesc?.rows.find((r) => r.key === "РастягиватьПоГоризонтали")?.value === "Истина");

const labelOff = FORM.indexOf("Тип: Надпись");
const removed = apply(FORM, propertyEdit(FORM, labelOff, "Значение", null));
check("правка: снятие свойства удаляет строку", !removed.includes("Введите код:"));
check("правка: после снятия парсится", renderFormPreview(removed).ok);

const quoted = apply(FORM, propertyEdit(FORM, labelOff, "Значение", "Текст: с двоеточием"));
check("правка: значение с двоеточием в кавычках", quoted.includes('Значение: "Текст: с двоеточием"'));
check("правка: кавычки парсятся назад", describeNode(quoted, quoted.indexOf("Тип: Надпись"))?.rows.find((r) => r.key === "Значение")?.value === "Текст: с двоеточием");

check("правка: смещение не на узле – undefined", propertyEdit(FORM, 3, "Имя", "Х") === undefined);

if (failures > 0) {
  console.error(`итого: ${failures} FAIL`);
  process.exit(1);
}
console.log("итого: все проверки ok");
