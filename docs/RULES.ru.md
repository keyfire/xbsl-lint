# Правила линтера xbsl

[English](https://github.com/keyfire/xbsl/blob/main/docs/RULES.md) · **Русский**

Полный перечень проверок линтера. Файл дополняется при добавлении правил; актуальный
список в рантайме – `xbsl list-rules` (или MCP `list_rules`). Сейчас правил: 78.

## Граница: линтер дополняет компилятор, но не заменяет его

Линтер работает по тексту и модели проекта, без вывода типов. Он ловит то, что компилятор
Элемента не проверяет или сообщает невнятно (соглашения, типографику, структуру, ссылки на
несуществующие типы и объекты), но НЕ ловит того, что требует вывода типов: избыточное
приведение, незакрытый ресурс, несовпадение типа возврата. Проверка корректности кода –
серверная компиляция при деплое; линтер идёт перед ней и снимает частые ошибки заранее.

## Как читать таблицу

- **Правило** – идентификатор `группа/имя`. Группа (часть до `/`) позволяет включать и
  выключать правила пачкой.
- **Severity** – `error` (сборка/CI должны падать), `warning` (нарушение соглашения),
  `info` (подсказка, обычно выключена).
- **Умолч.** – входит ли правило в набор по умолчанию (`вкл`) или включается явно (`выкл`).
- **Область** – `файл` (правило видит один файл) или `проект` (нужен индекс всего проекта:
  дубли Ид, неизвестные типы, кросс-модульные вызовы).
- **Документация** – ссылка на раздел документации платформы, стоящий за правилом. В VS Code
  код такого правила в панели "Проблемы" открывает этот раздел прямо в редакторе.

## Тиры

Правила разбиты на тиры A–D по тому, на что они опираются. Тир – это и есть быстрый фильтр
для `--select`/`--ignore` (наряду с группой и идентификатором): `--select A,B` гоняет только
структуру и текст, `--ignore D` убирает семантику над stdlib.

### Тир A – структура и YAML

Файл существует, парсится, у объекта есть уникальный UUID, имя совпадает с файлом.

| Правило | Severity | Умолч. | Область | Что проверяет | Документация |
|---|---|---|---|---|---|
| `yaml/valid` | error | вкл | файл | YAML не парсится | – |
| `yaml/id-uuid` | error | вкл | файл | Ид не является UUID | – |
| `yaml/id-required` | warning | вкл | файл | У объекта нет Ид | – |
| `yaml/name-matches-file` | warning | вкл | файл | Имя не совпадает с именем файла | – |
| `yaml/id-unique` | error | вкл | проект | Дубли Ид в проекте | – |
| `project/identifier` | warning | вкл | файл | Имя или поставщик проекта не идентификатор | [доки](https://1cmycloud.com/docs/help/topics/project-properties-standard/) |
| `project/presentation` | warning | вкл | файл | Представление проекта не заполнено | [доки](https://1cmycloud.com/docs/help/topics/project-properties-standard/) |
| `project/version` | warning | вкл | файл | Версия проекта не A.B.C | [доки](https://1cmycloud.com/docs/help/topics/project-properties-standard/) |
| `structure/xbsl-pair` | warning | вкл | файл | Модуль .xbsl без парного .yaml | – |

### Тир B – текст и соглашения

Кодировка, переводы строк, пробелы, типографика (тире, кавычки, многоточие), длина строки.

| Правило | Severity | Умолч. | Область | Что проверяет | Документация |
|---|---|---|---|---|---|
| `typography/em-dash` | info | выкл | файл | Длинное тире в комментарии | – |
| `typography/ellipsis` | warning | вкл | файл | Символ многоточия в комментарии | – |
| `typography/curly-quotes` | warning | вкл | файл | Кудрявые кавычки | – |
| `typography/guillemets-comment` | info | выкл | файл | Ёлочки в комментарии | – |
| `whitespace/trailing` | warning | вкл | файл | Хвостовые пробелы | – |
| `whitespace/mixed-newline` | warning | вкл | файл | Смешанные переводы строк | – |
| `encoding/utf8` | error | вкл | файл | Файл не в UTF-8 | – |
| `style/tab-indent` | warning | вкл | файл | Табуляция в отступе | [доки](https://1cmycloud.com/docs/help/topics/general-design/) |
| `style/line-length` | info | выкл | файл | Строка длиннее 120 символов | [доки](https://1cmycloud.com/docs/help/topics/general-design/) |

### Тир C – структура кода, базовый синтаксис и соглашения по написанию

Баланс блоков и скобок, заголовки циклов и методов, локальные переменные и группа `style/` –
соглашения из раздела документации "Рекомендации по написанию кода". Часть правил `style/`
выключена по умолчанию (накопленный долг, `info`): включаются `--select style` для замера.

| Правило | Severity | Умолч. | Область | Что проверяет | Документация |
|---|---|---|---|---|---|
| `code/brackets` | error | вкл | файл | Дисбаланс скобок () [] {} | – |
| `code/blocks` | error | вкл | файл | Дисбаланс блоков и ';' | [доки](https://1cmycloud.com/docs/help/topics/general-design/) |
| `code/ternary-and-or` | error | вкл | файл | Составное условие тернарного оператора без скобок | [доки](https://1cmycloud.com/docs/help/topics/question-mark-operation/) |
| `code/param-type-required` | error | вкл | файл | Параметр без типа и без значения по умолчанию | [доки](https://1cmycloud.com/docs/help/topics/methods-in-built-in-script-language/) |
| `code/loop-header` | error | вкл | файл | Неверный заголовок цикла 'для' | [доки](https://1cmycloud.com/docs/help/topics/for-in-loop/) |
| `code/unused-local` | warning | вкл | файл | Неиспользуемая локальная переменная | – |
| `code/unused-loop-var` | warning | вкл | файл | Неиспользуемая переменная цикла | – |
| `code/ref-field-needs-req` | error | вкл | файл | Поле-ссылка структуры без 'обз' | [доки](https://1cmycloud.com/docs/help/topics/structure/) |
| `style/boolean-compare` | info | выкл | файл | Сравнение булева значения с Истина/Ложь | [доки](https://1cmycloud.com/docs/help/topics/check-logical-values/) |
| `style/undefined-is` | warning | вкл | файл | Проверка Неопределено оператором 'это' | [доки](https://1cmycloud.com/docs/help/topics/check-if-undefined/) |
| `style/negated-is` | warning | вкл | файл | Отрицание оператора 'это' снаружи | [доки](https://1cmycloud.com/docs/help/topics/is-operator/) |
| `style/semicolon-line` | warning | вкл | файл | ';' не на отдельной строке | [доки](https://1cmycloud.com/docs/help/topics/general-design/) |
| `style/wrap-operator` | warning | вкл | файл | Операция в конце перенесённой строки | [доки](https://1cmycloud.com/docs/help/topics/split-expressions/) |
| `style/wrap-comma` | warning | вкл | файл | Запятая в начале перенесённой строки | [доки](https://1cmycloud.com/docs/help/topics/split-expressions/) |
| `style/camel-case` | info | выкл | файл | Имя не в UpperCamelCase | [доки](https://1cmycloud.com/docs/help/topics/naming-convention/) |
| `style/const-case` | warning | вкл | файл | Константа не БОЛЬШИМИ_БУКВАМИ | [доки](https://1cmycloud.com/docs/help/topics/naming-convention/) |
| `style/exception-prefix` | warning | вкл | файл | Имя исключения без префикса "Исключение" | [доки](https://1cmycloud.com/docs/help/topics/naming-convention/) |
| `style/abbreviation-case` | info | выкл | файл | Аббревиатура заглавными буквами в имени | [доки](https://1cmycloud.com/docs/help/topics/naming-convention/) |
| `style/enum-name-vid` | warning | вкл | файл | Имя перечисления начинается с "Тип" | [доки](https://1cmycloud.com/docs/help/topics/naming-convention/) |
| `style/collection-literal` | info | выкл | файл | Ручное наполнение коллекции вместо литерала | [доки](https://1cmycloud.com/docs/help/topics/collection-literals-usage/) |
| `style/redundant-tostring` | info | выкл | файл | '.ВСтроку()' в конкатенации | [доки](https://1cmycloud.com/docs/help/topics/string-concatenation/) |
| `style/interpolation` | info | выкл | файл | Конкатенация вместо интерполяции | [доки](https://1cmycloud.com/docs/help/topics/string-concatenation/) |
| `style/type-colon-space` | warning | вкл | файл | Пробелы вокруг двоеточия типа | [доки](https://1cmycloud.com/docs/help/topics/type-description-and-initialization/) |
| `style/union-spaces` | warning | вкл | файл | Пробелы вокруг '\|' в составном типе | [доки](https://1cmycloud.com/docs/help/topics/type-description-and-initialization/) |
| `style/nullable-shorthand` | warning | вкл | файл | Неопределено в типе без сокращения '?' | [доки](https://1cmycloud.com/docs/help/topics/type-description-and-initialization/) |
| `style/redundant-type` | warning | вкл | файл | Избыточная аннотация типа при инициализации | [доки](https://1cmycloud.com/docs/help/topics/type-description-and-initialization/) |
| `style/optional-params-last` | warning | вкл | файл | Необязательный параметр перед обязательным | [доки](https://1cmycloud.com/docs/help/topics/method-declarations/) |

### Тир D – семантика над stdlib, формы и метамодель

Требует индекс проекта и данные платформы: неизвестные типы и объекты, значения перечислений,
модель выполнения (клиент/сервер), обработчики форм, свойства и запросы.

| Правило | Severity | Умолч. | Область | Что проверяет | Документация |
|---|---|---|---|---|---|
| `yaml/choice-needs-static-list` | warning | вкл | файл | ВыборЗначения без статичного СпискаВыбора | [доки](https://1cmycloud.com/docs/help/stdlib/element/xbsl/Std/Interface/CommonComponents/ValueChoice_ru/) |
| `code/unknown-type` | warning | вкл | проект | Неизвестный тип | – |
| `code/unknown-object-type` | warning | вкл | проект | Неизвестный тип объекта проекта | – |
| `yaml/unknown-type` | warning | вкл | проект | Неизвестный тип в yaml | – |
| `yaml/dynlist-missing-field` | warning | вкл | проект | Нет поля динамического списка | [доки](https://1cmycloud.com/docs/help/topics/dynamic-list/) |
| `code/unknown-enum-value` | warning | вкл | проект | Неизвестное значение перечисления | [доки](https://1cmycloud.com/docs/help/topics/enumeration-properties/) |
| `yaml/enum-needs-nullable` | warning | вкл | проект | Перечисление без nullable | [доки](https://1cmycloud.com/docs/help/topics/enumeration-properties/) |
| `form/unknown-handler` | warning | вкл | проект | Обработчик формы не найден в модуле | [доки](https://1cmycloud.com/docs/help/topics/form-component/) |
| `code/server-call-from-handler` | warning | вкл | проект | Серверный метод недоступен клиентскому обработчику | [доки](https://1cmycloud.com/docs/help/topics/module-execution/) |
| `code/client-annotation-in-server-module` | warning | вкл | проект | Клиентская аннотация в серверном общем модуле | [доки](https://1cmycloud.com/docs/help/topics/module-execution/) |
| `code/client-module-in-http-service` | warning | вкл | проект | Клиентский общий модуль в HTTP-сервисе | [доки](https://1cmycloud.com/docs/help/topics/module-execution/) |
| `code/local-method-cross-component` | warning | вкл | проект | Кросс-компонентный вызов локального метода | [доки](https://1cmycloud.com/docs/help/topics/modular-development/) |
| `naming/yo` | warning | вкл | файл | Буква "ё" в имени | [доки](https://1cmycloud.com/docs/help/topics/project-element-names-standard/) |
| `naming/underscore` | warning | вкл | файл | Подчёркивание в имени | [доки](https://1cmycloud.com/docs/help/topics/project-element-names-standard/) |
| `naming/abbreviation` | warning | вкл | файл | Аббревиатура заглавными буквами в имени | [доки](https://1cmycloud.com/docs/help/topics/project-element-names-standard/) |
| `naming/latin-term` | warning | вкл | файл | Англоязычный термин записан русскими буквами | [доки](https://1cmycloud.com/docs/help/topics/project-element-names-standard/) |
| `naming/enum-vid` | warning | вкл | файл | Имя перечисления со словом "Тип" | [доки](https://1cmycloud.com/docs/help/topics/project-element-names-standard/) |
| `naming/kind-in-name` | warning | вкл | файл | Вид элемента в его имени | [доки](https://1cmycloud.com/docs/help/topics/project-element-names-standard/) |
| `naming/filler-word` | warning | вкл | файл | Слово-пустышка в имени | [доки](https://1cmycloud.com/docs/help/topics/project-element-names-standard/) |
| `naming/module-suffix` | warning | вкл | файл | Постфикс окружения в имени общего модуля | [доки](https://1cmycloud.com/docs/help/topics/project-element-names-standard/) |
| `naming/number` | warning | вкл | файл | Число имени не по виду элемента | [доки](https://1cmycloud.com/docs/help/topics/project-element-names-standard/) |
| `naming/boolean-name` | warning | вкл | файл | Имя булева реквизита | [доки](https://1cmycloud.com/docs/help/topics/project-element-names-standard/) |
| `naming/presentation` | warning | вкл | файл | Представление элемента | [доки](https://1cmycloud.com/docs/help/topics/project-element-names-standard/) |
| `naming/prefix-by-kind` | warning | вкл | файл | Имя вида без обязательного префикса | [доки](https://1cmycloud.com/docs/help/topics/project-element-names-standard/) |
| `code/unknown-ns-object` | warning | вкл | проект | Неизвестный объект в пространстве имён вида | – |
| `query/unknown-table` | warning | вкл | проект | Неизвестная таблица в запросе | [доки](https://1cmycloud.com/docs/help/topics/select-from/) |
| `query/in-subquery-composite` | warning | вкл | проект | 'В' с подзапросом по составному типу | [доки](https://1cmycloud.com/docs/help/topics/in-expression/) |
| `yaml/unknown-property` | warning | вкл | файл | Неизвестное свойство объекта | – |
| `code/reserved-name` | warning | вкл | файл | Зарезервированное имя | – |
| `yaml/builtin-property-name` | warning | вкл | файл | Совпадение со встроенным свойством | – |
| `yaml/size-needs-no-stretch` | info | выкл | файл | Размер без отключения растягивания | [доки](https://1cmycloud.com/docs/help/topics/arrange-components-on-screen/) |
| `code/unused-method` | warning | выкл | проект | Метод нигде не используется | – |
| `yaml/missing-import` | warning | вкл | проект | Нет импорта подсистемы в yaml | [доки](https://1cmycloud.com/docs/help/topics/modular-development/) |

## Включение и выключение

`--select` и `--ignore` принимают идентификатор правила, группу (часть до `/`, напр. `style`)
или букву тира `A`/`B`/`C`/`D`. Плагин может переопределить severity правила (группа
entry-points `xbsl.severity`); `XBSL_NO_PLUGINS=1` отключает плагины и возвращает встроенные
значения из этой таблицы.
