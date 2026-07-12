// Тесты каркасного рендера форм: yaml -> HTML. Запуск обычным node (см. npm test).

import { renderFormPreview } from "../src/formPreviewCore";

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

if (failures > 0) {
  console.error(`итого: ${failures} FAIL`);
  process.exit(1);
}
console.log("итого: все проверки ok");
