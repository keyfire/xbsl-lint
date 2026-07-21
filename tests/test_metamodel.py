"""Runtime access to the configuration metamodel (xbsl/metamodel.py) and its LSP surface.

A tiny metamodel.json is written into a temporary data root - no distribution or generated data
needed, so these run in a public checkout too; the degradation path pins an empty root.
"""

import importlib
import json
import sys
import types

import pytest

from xbsl import dataset, metamodel

_VER = "9.9.9+0"
_MM = {
    "meta": {"element_version": _VER, "props": "typed"},
    "classes": {
        "AcmeCatalogDescriptor": {
            "props": {
                "Иерархический": {"kind": "boolean", "type": "boolean", "default": "false",
                                  "priority": 9550},
                "Представление": {"kind": "string", "type": "AttributeName", "priority": 9900},
                "Реквизиты": {"kind": "list", "item": "IAcmeAttribute",
                              "impl": "AcmeRegularAttribute"},
            },
            "ext": ["AcmeElementBase"],
            "inline": ["AcmeStringLimits"],
        },
        "AcmeElementBase": {
            "props": {
                "Поставщик": {"kind": "string", "type": "String", "alias": ["Разработчик"]},
                "ОбластьВидимости": {"kind": "enum", "enum": "VisibilityScopeEnum",
                                     "type": "VisibilityScopeEnum"},
            },
            "ext": [],
        },
        "AcmeStringLimits": {
            "props": {"МаксимальнаяДлина": {"kind": "number", "type": "int"}},
            "ext": [],
        },
        "AcmeDocDescriptor": {"props": {"Проведение": {"kind": "boolean"}}, "ext": []},
    },
    "enums": {"VisibilityScopeEnum": ["ВПодсистеме", "ВПроекте", "Глобально"]},
    "vid2class": {"Справочник": "AcmeCatalogDescriptor", "Документ": "AcmeDocDescriptor"},
    "vetted": ["Справочник"],
    "common": ["ВидЭлемента", "Ид", "Имя"],
}
#: The pre-typing shape: a class holds a plain list of property names and there is no `vetted`.
_MM_LEGACY = {
    "meta": {"element_version": _VER},
    "classes": {"AcmeCatalogDescriptor": {"props": ["Иерархический", "Представление"], "ext": []}},
    "vid2class": {"Справочник": "AcmeCatalogDescriptor"},
    "common": ["ВидЭлемента", "Имя"],
}


def _root(tmp_path, data):
    ver_dir = tmp_path / _VER
    ver_dir.mkdir()
    (ver_dir / "metamodel.json").write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    (tmp_path / "index.json").write_text(
        json.dumps({"available": [_VER], "default": _VER}), encoding="utf-8"
    )
    dataset.set_data_root(tmp_path)
    return tmp_path


@pytest.fixture
def mm_root(tmp_path):
    yield _root(tmp_path, _MM)
    dataset.set_data_root(None)


@pytest.fixture
def legacy_root(tmp_path):
    yield _root(tmp_path, _MM_LEGACY)
    dataset.set_data_root(None)


@pytest.fixture
def no_data(tmp_path):
    dataset.set_data_root(tmp_path)
    yield
    dataset.set_data_root(None)


# --- the runtime accessor ----------------------------------------------------------------


def test_properties_follow_inheritance_and_inline(mm_root):
    props = metamodel.properties("Справочник")
    assert props["Иерархический"]["kind"] == "boolean"
    assert props["Поставщик"]["kind"] == "string"  # from the base class
    assert props["МаксимальнаяДлина"]["kind"] == "number"  # spliced in by `inline`
    for key in ("ВидЭлемента", "Ид", "Имя"):
        assert key in props  # envelope keys apply to every kind


def test_properties_ordered_like_the_designer(mm_root):
    keys = list(metamodel.properties("Справочник"))
    assert keys[:2] == ["Представление", "Иерархический"]  # by IDE priority, highest first
    rest = keys[2:]
    assert rest == sorted(rest, key=lambda k: k)  # then alphabetically


def test_allowed_keys_accept_alternate_spellings(mm_root):
    keys = metamodel.allowed_keys("Справочник")
    assert "Поставщик" in keys and "Разработчик" in keys  # the legacy spelling is still valid
    assert "ВидЭлемента" in keys
    assert "НетТакого" not in keys


def test_vetted_is_narrower_than_the_mapping(mm_root):
    assert metamodel.is_vetted("Справочник")
    assert not metamodel.is_vetted("Документ")  # known to the panel, not judged by the rule
    assert metamodel.kinds() == ("Документ", "Справочник")
    assert metamodel.class_for_kind("Документ") == "AcmeDocDescriptor"


def test_enum_values_and_class_lookup(mm_root):
    assert metamodel.enum_values("VisibilityScopeEnum") == ("ВПодсистеме", "ВПроекте", "Глобально")
    assert metamodel.enum_values("Нет") == ()
    assert metamodel.has_class("AcmeStringLimits")
    assert metamodel.class_property_names("AcmeCatalogDescriptor") >= {"Иерархический", "Поставщик"}


def test_legacy_data_reads_as_untyped_properties(legacy_root):
    props = metamodel.properties("Справочник")
    assert props["Иерархический"] == {}  # names only - the panel falls back to text editors
    assert metamodel.is_vetted("Справочник")  # without `vetted` the mapping itself is the list
    assert metamodel.allowed_keys("Справочник") == frozenset(
        {"Иерархический", "Представление", "ВидЭлемента", "Имя"}
    )


def test_degrades_without_data(no_data):
    assert not metamodel.available()
    assert metamodel.properties("Справочник") == {}
    assert metamodel.allowed_keys("Справочник") == frozenset()
    assert not metamodel.is_vetted("Справочник")


def test_localized_keeps_names_without_term_pairs(mm_root):
    props = metamodel.properties("Справочник")
    assert metamodel.localized(props, "ru") is props
    assert set(metamodel.localized(props, "en")) == set(props)  # no terms.json - Russian stays


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


def test_mcp_metadata_schema(mcp_module, mm_root):
    assert "metadata_schema" in mcp_module.mcp.tools
    kinds = mcp_module.metadata_schema()
    assert kinds["kinds"] == ["Документ", "Справочник"]
    one = mcp_module.metadata_schema("Справочник")
    assert one["props"]["Иерархический"]["kind"] == "boolean"
    assert one["enums"]["VisibilityScopeEnum"] == ["ВПодсистеме", "ВПроекте", "Глобально"]


def test_mcp_metadata_schema_degrades_without_data(mcp_module, no_data):
    assert mcp_module.metadata_schema() == {"available": False}


# --- LSP ---------------------------------------------------------------------------------

pygls = pytest.importorskip("pygls", reason="LSP-методы проверяются при установленном extra [lsp]")


def _server_features():
    from xbsl import lsp as lsp_module

    server = lsp_module._make_server()
    fm = getattr(server.lsp, "fm", None) or getattr(server.lsp, "_features", None)
    return getattr(fm, "features", fm)


def test_lsp_metadata_schema_registered():
    assert "xbsl/metadataSchema" in _server_features()


def test_lsp_metadata_schema_kinds_and_properties(mm_root):
    features = _server_features()
    kinds = features["xbsl/metadataSchema"](None)
    assert kinds["available"] is True and kinds["kinds"] == ["Документ", "Справочник"]
    one = features["xbsl/metadataSchema"]({"kind": "Справочник"})
    assert one["class"] == "AcmeCatalogDescriptor"
    assert one["props"]["Иерархический"]["default"] == "false"
    assert one["enums"]["VisibilityScopeEnum"] == ["ВПодсистеме", "ВПроекте", "Глобально"]
    unknown = features["xbsl/metadataSchema"]({"kind": "НетТакого"})
    assert unknown["props"] == {}


def test_lsp_metadata_schema_degrades_without_data(no_data):
    assert _server_features()["xbsl/metadataSchema"](None) == {"available": False}
