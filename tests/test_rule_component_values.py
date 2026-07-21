"""Checks of the yaml/unknown-enum-value rule (a component property value vs the ui schema).

The schema is written into a temporary data root, so the tests need no generated Element
data and run in a public checkout as well.
"""

import json

import pytest

from xbsl import dataset, engine
from xbsl.cli import discover
from xbsl.rules import component_values

_RULE = "yaml/unknown-enum-value"
_VER = "9.9.9+0"
_SCHEMA = {
    "meta": {"source": "docs", "element_version": _VER, "tool": "extract_uischema", "count": 2},
    "components": {
        "КарточкаАкме": {
            "package": "Стд::Интерфейс::ОбщиеКомпоненты",
            "props": {
                # purely enumerated: every union member is an enumeration or the literal Авто
                "ВидОтображения": {"types": ["Авто", "ВидВиджета"], "enum": ["Карточка", "Баннер"]},
                # a real type among the members - the value may be anything
                "Заголовок": {
                    "types": ["Авто", "ВидВиджета", "Строка"], "enum": ["Карточка", "Баннер"],
                },
                "ПриНажатии": {"event": "(КарточкаАкме, СобытиеПриНажатии)->ничто"},
            },
        },
        "ГруппаАкме": {
            "package": "Стд::Интерфейс",
            "props": {
                "Выравнивание": {
                    "types": ["Авто", "ВидГраницы"], "enum": ["Сплошная", "Пунктирная"],
                },
            },
        },
    },
    "enums": {
        "ВидВиджета": {"package": "Стд::Интерфейс", "values": ["Карточка", "Баннер"]},
        "ВидГраницы": {"package": "Стд::Интерфейс", "values": ["Сплошная", "Пунктирная"]},
    },
}


@pytest.fixture
def ui_root(tmp_path):
    """A data root holding the schema above; the rule reads it as if it were real."""
    root = tmp_path / "data"
    ver_dir = root / _VER
    ver_dir.mkdir(parents=True)
    (ver_dir / "uischema.json").write_text(
        json.dumps(_SCHEMA, ensure_ascii=False), encoding="utf-8"
    )
    (root / "index.json").write_text(
        json.dumps({"available": [_VER], "default": _VER}), encoding="utf-8"
    )
    dataset.set_data_root(root)
    component_values._enumerated_props.cache_clear()
    yield root
    dataset.set_data_root(None)
    component_values._enumerated_props.cache_clear()


@pytest.fixture
def no_data(tmp_path):
    """An empty data root: no ui schema - the public-checkout degradation."""
    root = tmp_path / "empty"
    root.mkdir()
    dataset.set_data_root(root)
    component_values._enumerated_props.cache_clear()
    yield
    dataset.set_data_root(None)
    component_values._enumerated_props.cache_clear()


def _run(tmp_path, text, name="Ф.yaml"):
    src = tmp_path / "src"
    src.mkdir(exist_ok=True)
    (src / name).write_text(text, encoding="utf-8")
    return engine.run(discover([str(src)]), select={_RULE})


def _has(diags):
    return any(d.rule_id == _RULE for d in diags)


def _form(body):
    return "ВидЭлемента: КомпонентИнтерфейса\nИмя: Ф\nСодержимое:\n    -\n" + body


def test_value_outside_the_enumeration_flagged(tmp_path, ui_root):
    d = _run(tmp_path, _form("        Тип: КарточкаАкме\n        ВидОтображения: Плитка\n"))
    assert len(d) == 1 and d[0].rule_id == _RULE
    assert d[0].severity.name == "ERROR"
    assert "Плитка" in d[0].message and "Баннер, Карточка" in d[0].message
    assert (d[0].line, d[0].col) == (6, 25)


def test_value_from_the_enumeration_not_flagged(tmp_path, ui_root):
    d = _run(tmp_path, _form("        Тип: КарточкаАкме\n        ВидОтображения: Баннер\n"))
    assert not _has(d)


def test_literal_auto_not_flagged(tmp_path, ui_root):
    d = _run(tmp_path, _form("        Тип: КарточкаАкме\n        ВидОтображения: Авто\n"))
    assert not _has(d)


def test_property_with_a_real_type_member_not_flagged(tmp_path, ui_root):
    # Заголовок accepts Строка too - any value is legal
    d = _run(tmp_path, _form("        Тип: КарточкаАкме\n        Заголовок: Что угодно\n"))
    assert not _has(d)


def test_binding_not_flagged(tmp_path, ui_root):
    d = _run(
        tmp_path,
        _form("        Тип: КарточкаАкме\n        ВидОтображения: =ЭтоМобильный()?1:2\n"),
    )
    assert not _has(d)


def test_qualified_value_not_flagged(tmp_path, ui_root):
    # the enumeration spelled out: ВидВиджета.Баннер
    d = _run(
        tmp_path, _form("        Тип: КарточкаАкме\n        ВидОтображения: ВидВиджета.Баннер\n")
    )
    assert not _has(d)


def test_unknown_component_not_judged(tmp_path, ui_root):
    # a project component of the same shape: its properties are its own
    d = _run(tmp_path, _form("        Тип: МояКарточка\n        ВидОтображения: Плитка\n"))
    assert not _has(d)


def test_generic_component_head_is_used(tmp_path, ui_root):
    d = _run(
        tmp_path, _form("        Тип: КарточкаАкме<Строка>\n        ВидОтображения: Плитка\n")
    )
    assert len(d) == 1


def test_event_property_not_judged(tmp_path, ui_root):
    d = _run(tmp_path, _form("        Тип: КарточкаАкме\n        ПриНажатии: МойОбработчик\n"))
    assert not _has(d)


def test_block_scalar_not_scanned(tmp_path, ui_root):
    d = _run(
        tmp_path,
        "ВидЭлемента: КомпонентИнтерфейса\nИмя: Ф\nОписание: |\n"
        "    Тип: КарточкаАкме\n    ВидОтображения: Плитка\n",
    )
    assert not _has(d)


def test_structural_file_not_scanned(tmp_path, ui_root):
    d = _run(
        tmp_path, "Имя: Проект\nТип: КарточкаАкме\nВидОтображения: Плитка\n", name="Проект.yaml"
    )
    assert not _has(d)


def test_two_nodes_told_apart(tmp_path, ui_root):
    d = _run(
        tmp_path,
        "ВидЭлемента: КомпонентИнтерфейса\nИмя: Ф\nСодержимое:\n"
        "    -\n        Тип: КарточкаАкме\n        ВидОтображения: Баннер\n"
        "    -\n        Тип: КарточкаАкме\n        ВидОтображения: Плитка\n",
    )
    assert len(d) == 1 and d[0].line == 9


def test_different_components_have_own_value_sets(tmp_path, ui_root):
    # Сплошная is legal for ГруппаАкме.Выравнивание and unknown to КарточкаАкме.ВидОтображения
    d = _run(
        tmp_path,
        "ВидЭлемента: КомпонентИнтерфейса\nИмя: Ф\nСодержимое:\n"
        "    -\n        Тип: ГруппаАкме\n        Выравнивание: Сплошная\n"
        "    -\n        Тип: КарточкаАкме\n        ВидОтображения: Сплошная\n",
    )
    assert len(d) == 1 and d[0].line == 9


def test_without_ui_schema_silent(tmp_path, no_data):
    d = _run(tmp_path, _form("        Тип: КарточкаАкме\n        ВидОтображения: Плитка\n"))
    assert not _has(d)
