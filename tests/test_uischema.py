"""Runtime ui schema access (xbsl/uischema.py) and its LSP/MCP surfaces.

A tiny uischema.json is written into a temporary data root - no distribution or
generated data needed; the degradation path pins an empty root (no index at all),
imitating a public checkout without data.
"""

import importlib
import json
import sys
import types

import pytest

from xbsl import dataset, uischema

_VER = "9.9.9+0"
_SCHEMA = {
    "meta": {"source": "docs", "element_version": _VER, "tool": "extract_uischema", "count": 2},
    "components": {
        "КарточкаАкме": {
            "package": "Стд::Интерфейс::ОбщиеКомпоненты",
            "container": True,
            "doc": "Карточка с предопределенной структурой.",
            "props": {
                "ВидОтображения": {"types": ["Авто", "ВидВиджета"], "enum": ["Карточка", "Баннер"]},
                # a multi-member union: prop.enum is not resolved, the values come from
                # the per-component enums map of the component() response instead
                "Граница": {"types": ["Авто", "ВидГраницы", "Строка"]},
                "ПриНажатии": {"event": "(КарточкаАкме, СобытиеПриНажатии)->ничто"},
                "Содержимое": {"types": ["Компонент", "Строка"], "slot": True},
                "Ссылка": {"types": ["Url"], "nullable": True},
            },
        },
        "Компонент": {
            "package": "Стд::Интерфейс",
            "abstract": True,
            "doc": "Базовый абстрактный компонент.",
            "props": {"Видимость": {"types": ["Авто", "Булево"]}},
        },
    },
    "enums": {
        "ВидВиджета": {"package": "Стд::Интерфейс", "values": ["Карточка", "Баннер"]},
        "ВидГраницы": {"package": "Стд::Интерфейс", "values": ["Сплошная", "Пунктирная"]},
    },
}


@pytest.fixture
def ui_root(tmp_path):
    """A data root with a tiny uischema.json; the runtime reads it as if it were real."""
    ver_dir = tmp_path / _VER
    ver_dir.mkdir()
    (ver_dir / "uischema.json").write_text(
        json.dumps(_SCHEMA, ensure_ascii=False), encoding="utf-8"
    )
    (tmp_path / "index.json").write_text(
        json.dumps({"available": [_VER], "default": _VER}), encoding="utf-8"
    )
    dataset.set_data_root(tmp_path)
    yield tmp_path
    dataset.set_data_root(None)


@pytest.fixture
def no_data(tmp_path):
    """An empty data root: no index, no versions - the public-checkout degradation."""
    dataset.set_data_root(tmp_path)
    yield
    dataset.set_data_root(None)


# --- the dataset accessor ----------------------------------------------------------------


def test_load_ui_schema(ui_root):
    schema = dataset.load_ui_schema()
    assert schema["meta"]["element_version"] == _VER
    assert "КарточкаАкме" in schema["components"]


def test_load_ui_schema_absent_is_none(no_data):
    assert dataset.load_ui_schema() is None


def test_available(ui_root):
    assert uischema.available() is True


# --- the shared shapes -------------------------------------------------------------------


def test_catalog_strips_props(ui_root):
    got = uischema.catalog()
    assert got["available"] is True
    assert got["version"] == _VER
    card = got["components"]["КарточкаАкме"]
    assert card["package"] == "Стд::Интерфейс::ОбщиеКомпоненты"
    assert "props" not in card
    assert card["container"] is True  # the palette/structure take containers from here
    assert got["components"]["Компонент"]["abstract"] is True
    assert "container" not in got["components"]["Компонент"]


def test_component_full_record(ui_root):
    got = uischema.component("КарточкаАкме")
    assert got["available"] is True
    comp = got["component"]
    assert comp["name"] == "КарточкаАкме"
    assert comp["props"]["ВидОтображения"]["enum"] == ["Карточка", "Баннер"]
    assert comp["props"]["ПриНажатии"]["event"].startswith("(КарточкаАкме")


def test_component_enums_referenced_by_unions(ui_root):
    # Both the single-member and the multi-member union enums ride along the response;
    # a component whose unions reference no enumerations has no "enums" key at all.
    got = uischema.component("КарточкаАкме")
    assert got["enums"] == {
        "ВидВиджета": ["Карточка", "Баннер"],
        "ВидГраницы": ["Сплошная", "Пунктирная"],
    }
    assert "enums" not in uischema.component("Компонент")


def test_component_unknown_gives_close_matches(ui_root):
    got = uischema.component("КарточкаАкм")
    assert got["available"] is True and got["component"] is None
    assert "КарточкаАкме" in got["close_matches"]


def test_component_brief_is_one_line_per_property(ui_root):
    got = uischema.component_brief("КарточкаАкме")
    assert got["available"] is True
    comp = got["component"]
    assert comp["container"] is True and "enums" not in got
    props = comp["props"]
    assert props["ВидОтображения"] == "Авто | ВидВиджета{Карточка|Баннер}"
    assert props["Граница"] == "Авто | ВидГраницы{Сплошная|Пунктирная} | Строка"
    assert props["ПриНажатии"] == "событие (КарточкаАкме, СобытиеПриНажатии)->ничто"
    assert props["Содержимое"] == "Компонент | Строка [slot]"
    assert props["Ссылка"] == "Url?"


def test_component_brief_unknown_and_degradation(ui_root):
    miss = uischema.component_brief("КарточкаАкм")
    assert miss["component"] is None and "КарточкаАкме" in miss["close_matches"]


def test_component_property_full_record(ui_root):
    got = uischema.component_property("КарточкаАкме", "Граница")
    assert got["available"] is True and got["component"] == "КарточкаАкме"
    assert got["property"]["name"] == "Граница"
    assert got["property"]["types"] == ["Авто", "ВидГраницы", "Строка"]
    assert got["enums"] == {"ВидГраницы": ["Сплошная", "Пунктирная"]}


def test_component_property_unknown_gives_close_matches(ui_root):
    miss = uischema.component_property("КарточкаАкме", "Гран")
    assert miss["property"] is None and "Граница" in miss["close_matches"]
    no_comp = uischema.component_property("Нет", "Граница")
    assert no_comp["component"] is None


def test_degradation_without_data(no_data):
    assert uischema.available() is False
    assert uischema.catalog() == {"available": False}
    assert uischema.component("КарточкаАкме") == {"available": False}


# --- MCP ---------------------------------------------------------------------------------


@pytest.fixture()
def mcp_module(monkeypatch):
    class _FakeMCP:
        def __init__(self, name):
            self.name = name
            self.tools = {}

        def tool(self):
            def deco(fn):
                self.tools[fn.__name__] = fn
                return fn

            return deco

    fast = types.ModuleType("mcp.server.fastmcp")
    fast.FastMCP = _FakeMCP
    monkeypatch.setitem(sys.modules, "mcp", types.ModuleType("mcp"))
    monkeypatch.setitem(sys.modules, "mcp.server", types.ModuleType("mcp.server"))
    monkeypatch.setitem(sys.modules, "mcp.server.fastmcp", fast)
    sys.modules.pop("xbsl.mcp_server", None)
    module = importlib.import_module("xbsl.mcp_server")
    yield module
    sys.modules.pop("xbsl.mcp_server", None)


def test_mcp_tool_registered(mcp_module):
    assert "ui_schema" in mcp_module.mcp.tools


def test_mcp_catalog_and_component(mcp_module, ui_root):
    catalog = mcp_module.ui_schema()
    assert catalog["available"] is True and "КарточкаАкме" in catalog["components"]
    assert catalog["components"]["КарточкаАкме"]["container"] is True
    one = mcp_module.ui_schema("КарточкаАкме")
    assert one["component"]["props"]["Содержимое"]["slot"] is True
    assert one["enums"]["ВидГраницы"] == ["Сплошная", "Пунктирная"]


def test_mcp_brief_and_single_property(mcp_module, ui_root):
    brief = mcp_module.ui_schema("КарточкаАкме", brief=True)
    assert brief["component"]["props"]["Содержимое"] == "Компонент | Строка [slot]"
    one = mcp_module.ui_schema("КарточкаАкме", property="Граница")
    assert one["property"]["name"] == "Граница"
    # property overrides brief - one full record, not a line
    both = mcp_module.ui_schema("КарточкаАкме", brief=True, property="Граница")
    assert both["property"]["types"] == ["Авто", "ВидГраницы", "Строка"]


def test_mcp_degrades_without_data(mcp_module, no_data):
    assert mcp_module.ui_schema() == {"available": False}
    assert mcp_module.ui_schema("КарточкаАкме", brief=True) == {"available": False}


# --- LSP ---------------------------------------------------------------------------------

pygls = pytest.importorskip("pygls", reason="LSP-методы проверяются при установленном extra [lsp]")


def _server_features():
    from xbsl import lsp as lsp_module

    server = lsp_module._make_server()
    fm = getattr(server.lsp, "fm", None) or getattr(server.lsp, "_features", None)
    features = getattr(fm, "features", fm)
    return server, features


def test_lsp_ui_schema_registered():
    _, features = _server_features()
    assert "xbsl/uiSchema" in features


def test_lsp_ui_schema_catalog_and_component(ui_root):
    _, features = _server_features()
    catalog = features["xbsl/uiSchema"](None)
    assert catalog["available"] is True
    assert "props" not in catalog["components"]["КарточкаАкме"]
    assert catalog["components"]["КарточкаАкме"]["container"] is True
    one = features["xbsl/uiSchema"]({"component": "Компонент"})
    assert one["component"]["abstract"] is True
    full = features["xbsl/uiSchema"]({"component": "КарточкаАкме"})
    assert full["enums"]["ВидВиджета"] == ["Карточка", "Баннер"]
    miss = features["xbsl/uiSchema"]({"component": "Нет"})
    assert miss["component"] is None and "close_matches" in miss


def test_lsp_ui_schema_degrades_without_data(no_data):
    _, features = _server_features()
    assert features["xbsl/uiSchema"](None) == {"available": False}
