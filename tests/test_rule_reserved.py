"""Проверки правил code/reserved-name и yaml/builtin-property-name."""

import pytest

from xbsllint import dataset, engine
from xbsllint.rules import reserved_names


def _lint(name, content, rule_id):
    return [
        d for d in engine.run_sources(
            [engine.load_text(name, content)], select={rule_id},
        )
        if d.rule_id == rule_id
    ]


# --- code/reserved-name: поля структур -------------------------------------------------

def test_structure_field_tip_flagged():
    d = _lint(
        "М.xbsl",
        "структура С\n    пер Тип: Строка\n;\n",
        "code/reserved-name",
    )
    assert len(d) == 1
    assert (d[0].line, d[0].col) == (2, 9)
    assert "поле структуры" in d[0].message


def test_structure_field_type_latin_flagged():
    d = _lint(
        "М.xbsl",
        "структура С\n    пер type: Строка\n;\n",
        "code/reserved-name",
    )
    assert len(d) == 1 and (d[0].line, d[0].col) == (2, 9)


def test_structure_field_req_flagged():
    d = _lint(
        "М.xbsl",
        "структура С\n    обз пер Тип: Строка\n;\n",
        "code/reserved-name",
    )
    assert len(d) == 1 and (d[0].line, d[0].col) == (2, 13)


def test_structure_field_val_in_name_list_flagged():
    d = _lint(
        "М.xbsl",
        "структура С\n    знч А, Тип: Строка\n;\n",
        "code/reserved-name",
    )
    assert len(d) == 1 and (d[0].line, d[0].col) == (2, 12)


def test_structure_ordinary_fields_not_flagged():
    d = _lint(
        "М.xbsl",
        "структура С\n    пер Имя: Строка\n    пер ВидТипа: Строка\n;\n",
        "code/reserved-name",
    )
    assert d == []


def test_tip_as_type_annotation_not_flagged():
    # Тип в позиции ТИПА (а не имени) – не нарушение
    d = _lint(
        "М.xbsl",
        "структура С\n    пер ВидЗначения: Тип\n;\n",
        "code/reserved-name",
    )
    assert d == []


# --- code/reserved-name: параметры методов ---------------------------------------------

def test_method_param_tip_flagged():
    d = _lint(
        "М.xbsl",
        "метод Ф(Тип: Строка): Строка\n    возврат Тип\n;\n",
        "code/reserved-name",
    )
    assert len(d) == 1
    assert (d[0].line, d[0].col) == (1, 9)
    assert "параметр метода" in d[0].message


def test_method_second_param_type_flagged():
    d = _lint(
        "М.xbsl",
        "метод Ф(Имя: Строка, type: Строка)\n;\n",
        "code/reserved-name",
    )
    assert len(d) == 1 and (d[0].line, d[0].col) == (1, 22)


def test_local_var_tip_not_flagged():
    # локальная переменная Тип в теле метода легальна (есть в живом корпусе)
    d = _lint(
        "М.xbsl",
        'метод Ф()\n    пер Тип = ""\n    Тип = "х"\n;\n',
        "code/reserved-name",
    )
    assert d == []


def test_method_after_structure_not_treated_as_field():
    # блок структуры закрыт `;` – объявления в методе после неё не считаются полями
    d = _lint(
        "М.xbsl",
        "структура С\n    пер Имя: Строка\n;\n"
        'метод Ф()\n    пер Тип = ""\n;\n',
        "code/reserved-name",
    )
    assert d == []


# --- yaml/builtin-property-name ---------------------------------------------------------

_КАРТОЧКА = (
    "ВидЭлемента: КомпонентИнтерфейса\n"
    "Ид: 33333333-3333-3333-3333-333333333333\n"
    "Имя: Карточка1\n"
    "Наследует:\n"
    "    Тип: СтандартнаяКарточка\n"
    "Свойства:\n"
    "    -\n"
    "        Имя: {prop}\n"
    "        Тип: Строка\n"
)


def test_builtin_property_zagolovok_flagged():
    d = _lint(
        "Карточка1.yaml", _КАРТОЧКА.format(prop="Заголовок"), "yaml/builtin-property-name",
    )
    assert len(d) == 1
    assert (d[0].line, d[0].col) == (8, 14)
    assert "Заголовок" in d[0].message and "СтандартнаяКарточка" in d[0].message


def test_builtin_property_commented_section_key_positioned():
    # комментарий после `Свойства:` не ломает поиск блока - позиция остаётся на имени
    content = _КАРТОЧКА.format(prop="Заголовок").replace("Свойства:", "Свойства: # собственные")
    d = _lint("Карточка1.yaml", content, "yaml/builtin-property-name")
    assert len(d) == 1
    assert (d[0].line, d[0].col) == (8, 14)


def test_builtin_inherited_property_flagged():
    # Видимость унаследована от Компонент – тоже встроенное имя
    d = _lint(
        "Карточка1.yaml", _КАРТОЧКА.format(prop="Видимость"), "yaml/builtin-property-name",
    )
    assert len(d) == 1 and (d[0].line, d[0].col) == (8, 14)


def test_custom_property_not_flagged():
    d = _lint(
        "Карточка1.yaml", _КАРТОЧКА.format(prop="КрупныйЗаголовок"), "yaml/builtin-property-name",
    )
    assert d == []


def test_container_html_zagolovok_not_flagged():
    # у КонтейнерHtml в документированном наборе нет свойства Заголовок; в живом корпусе
    # наследник КонтейнерHtml легально объявляет такое свойство – проверка строго по типу
    content = _КАРТОЧКА.replace("СтандартнаяКарточка", "КонтейнерHtml").format(prop="Заголовок")
    d = _lint("Карточка1.yaml", content, "yaml/builtin-property-name")
    assert d == []


def test_unknown_base_type_skipped():
    # база, которой нет ни в метамодели, ни в каталоге, ни в страховочной таблице
    # (например, собственный компонент проекта) – пропуск, не гадаем
    content = _КАРТОЧКА.replace(
        "СтандартнаяКарточка", "НикакойБазовыйКомпонент",
    ).format(prop="Заголовок")
    d = _lint("Карточка1.yaml", content, "yaml/builtin-property-name")
    assert d == []


def _catalog_or_skip() -> dict:
    catalog = reserved_names._catalog_component_props()
    if not catalog:
        pytest.skip("в данных нет component_props (старые данные)")
    return catalog


def test_catalog_base_group_flagged():
    # база из каталога дистрибутива (за пределами страховочной таблицы)
    assert "Группа" in _catalog_or_skip()
    content = _КАРТОЧКА.replace("СтандартнаяКарточка", "Группа").format(prop="Компоновка")
    d = _lint("Карточка1.yaml", content, "yaml/builtin-property-name")
    assert len(d) == 1
    assert "Компоновка" in d[0].message and "Группа" in d[0].message


def test_generic_base_root_resolved_via_catalog():
    # корень дженерик-базы (ФормаОбъекта<...>) резолвится по каталогу свойств компонентов
    assert "ФормаОбъекта" in _catalog_or_skip()
    content = _КАРТОЧКА.replace(
        "СтандартнаяКарточка", "ФормаОбъекта<Товары.Объект>",
    ).format(prop="Заголовок")
    d = _lint("Карточка1.yaml", content, "yaml/builtin-property-name")
    assert len(d) == 1 and "ФормаОбъекта" in d[0].message


def test_catalog_wiring_reads_component_props(monkeypatch):
    # каталог доезжает до правила через dataset.load_json("stdlib.json").component_props
    fake = {"component_props": {"ОсобаяБаза": ["Заголовок", "Видимость"]}}
    monkeypatch.setattr(dataset, "load_json", lambda name, version=None: fake)
    reserved_names._catalog_component_props.cache_clear()
    try:
        content = _КАРТОЧКА.replace("СтандартнаяКарточка", "ОсобаяБаза").format(prop="Заголовок")
        d = _lint("Карточка1.yaml", content, "yaml/builtin-property-name")
        assert len(d) == 1 and "ОсобаяБаза" in d[0].message
    finally:
        reserved_names._catalog_component_props.cache_clear()


def test_event_with_builtin_name_not_flagged():
    # Имя вне блока Свойства (событие) не проверяется и не даёт ложной позиции
    content = (
        "ВидЭлемента: КомпонентИнтерфейса\n"
        "Ид: 33333333-3333-3333-3333-333333333333\n"
        "Имя: Карточка1\n"
        "Наследует:\n"
        "    Тип: СтандартнаяКарточка\n"
        "События:\n"
        "    -\n"
        "        Имя: Заголовок\n"
        "Свойства:\n"
        "    -\n"
        "        Имя: Титул\n"
        "        Тип: Строка\n"
    )
    d = _lint("Карточка1.yaml", content, "yaml/builtin-property-name")
    assert d == []


def test_non_component_yaml_skipped():
    content = (
        "ВидЭлемента: Справочник\n"
        "Ид: 33333333-3333-3333-3333-333333333333\n"
        "Имя: Товары\n"
    )
    d = _lint("Товары.yaml", content, "yaml/builtin-property-name")
    assert d == []


def test_crlf_positions_stable():
    content = _КАРТОЧКА.format(prop="Заголовок").replace("\n", "\r\n")
    d = _lint("Карточка1.yaml", content, "yaml/builtin-property-name")
    assert len(d) == 1 and (d[0].line, d[0].col) == (8, 14)
