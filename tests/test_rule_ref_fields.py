"""Правило code/ref-field-needs-req: поле-ссылка структуры без 'обз', '?' и инициализатора.

Проверяются и срабатывание на "плохих" примерах (реальная грабля: apply падает с
"cannot be initialized with a default value"), и молчание на всех правильных формах и
осознанных сужениях (союзы, дженерики, локальные переменные методов).

Правило токеновое, но лексеру нужны данные языка (language.json) – без сгенерированных
данных модуль пропускается, как и остальные токеновые тесты (см. conftest.py).
"""

import pytest

from xbsllint import dataset, engine

pytestmark = pytest.mark.skipif(
    not dataset.available_versions(),
    reason="нет данных Элемента – сгенерируйте tools/extract_grammar.py + extract_stdlib.py",
)

RULE = "code/ref-field-needs-req"


def _lint(content, name="М.xbsl"):
    return engine.run_sources([engine.load_text(name, content)], select={RULE})


def _clean(content, name="М.xbsl"):
    return _lint(content, name) == []


# --- Срабатывания ----------------------------------------------------------------------

def test_ref_field_without_req_flagged():
    d = _lint("структура Шапка\n    пер Ссылка: Программа.Ссылка\n;\n")
    assert len(d) == 1
    assert d[0].line == 2 and d[0].col == 9
    assert d[0].severity.value == "error"
    assert "обз пер Ссылка: Программа.Ссылка" in d[0].message


def test_val_ref_field_flagged():
    d = _lint("структура Шапка\n    знч Владелец: Абоненты.Ссылка\n;\n")
    assert len(d) == 1 and "обз знч Владелец: Абоненты.Ссылка" in d[0].message


def test_ns_qualified_ref_flagged():
    # тип с NS-префиксом – тоже прямое поле-ссылка
    d = _lint("структура Шапка\n    пер Товар: Справочник.Товары.Ссылка\n;\n")
    assert len(d) == 1 and "Справочник.Товары.Ссылка" in d[0].message


def test_two_names_shared_type_flagged_each():
    d = _lint("структура Шапка\n    пер Первый, Второй: Программа.Ссылка\n;\n")
    assert [x.message.split("'")[1] for x in d] == ["Первый", "Второй"]


def test_second_structure_after_method_with_query_flagged():
    # ';' внутри Запрос{} не ломает баланс блоков – поле после метода находится
    content = (
        "структура А\n"
        "    пер Имя: Строка\n"
        "\n"
        "    метод Ф(): Число\n"
        "        знч Р = Запрос{\n"
        "            ВЫБРАТЬ 1; ВЫБРАТЬ 2\n"
        "        }.Выполнить()\n"
        "        если Р.Пусто()\n"
        "            возврат 0\n"
        "        иначе если Истина\n"
        "            возврат 1\n"
        "        ;\n"
        "        возврат 2\n"
        "    ;\n"
        "\n"
        "    пер Ссылка: Программа.Ссылка\n"
        ";\n"
    )
    d = _lint(content)
    assert len(d) == 1 and d[0].line == 16


# --- Правильные формы – молчание -------------------------------------------------------

def test_req_field_ok():
    assert _clean("структура Шапка\n    обз пер Ссылка: Программа.Ссылка\n;\n")


def test_req_val_field_ok():
    assert _clean("структура Шапка\n    обз знч Ссылка: Программа.Ссылка\n;\n")


def test_nullable_field_ok():
    assert _clean("структура Шапка\n    пер Ссылка: Программа.Ссылка? = Неопределено\n;\n")


def test_nullable_without_initializer_ok():
    assert _clean("структура Шапка\n    пер Ссылка: Программа.Ссылка?\n;\n")


def test_initializer_ok():
    assert _clean("структура Шапка\n    пер Ссылка: Программа.Ссылка = НайтиПрограмму()\n;\n")


def test_non_ref_fields_ok():
    assert _clean(
        "структура Шапка\n"
        "    пер Название: Строка\n"
        "    пер Объект: Программа.Объект\n"
        ";\n"
    )


# --- Сужения и не-поля – молчание ------------------------------------------------------

def test_union_type_skipped():
    assert _clean("структура Шапка\n    пер Ссылка: Программа.Ссылка|Акция.Ссылка\n;\n")


def test_union_with_nullable_skipped():
    assert _clean("структура Шапка\n    пер Ссылка: Программа.Ссылка|?\n;\n")


def test_generic_skipped():
    assert _clean("структура Шапка\n    пер Ссылки: Массив<Программа.Ссылка>\n;\n")


def test_bare_link_name_skipped():
    # односегментная 'Ссылка' – локальное имя типа, не ссылка объекта проекта
    assert _clean("структура Шапка\n    пер Ссылка: Ссылка\n;\n")


def test_local_variable_in_method_ok():
    # переменная метода – не поле структуры, даже с тем же типом
    assert _clean(
        "метод Ф()\n"
        "    пер Ссылка: Программа.Ссылка = НайтиПрограмму()\n"
        "    пер Другая: Программа.Ссылка\n"
        ";\n"
    )


def test_field_in_structure_method_ok():
    # переменная внутри метода структуры – тоже не поле
    assert _clean(
        "структура Шапка\n"
        "    пер Имя: Строка\n"
        "    метод Ф()\n"
        "        пер Ссылка: Программа.Ссылка\n"
        "    ;\n"
        ";\n"
    )


def test_yaml_source_ok():
    assert engine.run_sources(
        [engine.load_text("Ф.yaml", "Имя: Ф\n")], select={RULE},
    ) == []
