"""Tests of the pure LSP navigation core (a port of the extension's navCore tests)."""

from xbsllint.lsp_nav import IndexLookup, chain_at, resolve_completions, resolve_definition, resolve_hover

INDEX = {
    "meta": {"root": "C:/work/app/e1c/demo", "version": "test"},
    "objects": [
        {
            "name": "Товар",
            "kind": "Справочник",
            "path": "Каталог/Товар.yaml",
            "line": 3,
            "tabular": [{"name": "Цены", "line": 40}],
            "local_types": [{"name": "ДанныеКарточки", "path": "Каталог/Товар.xbsl", "line": 12}],
            "family": ["Ссылка", "Объект"],
            "values": [],
        },
        {
            "name": "ВидТовара",
            "kind": "Перечисление",
            "path": "Каталог/ВидТовара.yaml",
            "line": 2,
            "tabular": [],
            "local_types": [],
            "family": [],
            "values": [{"name": "Весовой", "line": 9}],
        },
    ],
    "methods": [
        {"module": "Товар", "name": "Загрузить", "path": "Каталог/Товар.xbsl", "line": 20, "annotations": ["НаСервере"]},
        {"module": "ГлавнаяФорма", "name": "Обновить", "path": "Каталог/ГлавнаяФорма.xbsl", "line": 5, "annotations": []},
        {"module": "Кнопка", "name": "Нажать", "path": "Каталог/Кнопка.xbsl", "line": 7, "annotations": ["Локально"]},
    ],
    "components": [
        {"form": "ГлавнаяФорма", "name": "Кнопка", "type": "Кнопка", "path": "Каталог/ГлавнаяФорма.yaml", "line": 33},
    ],
}

LOOKUP = IndexLookup(INDEX)


def d(line_text, character, language_id="xbsl", file_stem="ГлавнаяФорма", file_path=None):
    return resolve_definition(
        LOOKUP,
        language_id=language_id,
        line_text=line_text,
        character=character,
        file_stem=file_stem,
        file_path=file_path,
    )


def test_chain_at_segments():
    parts, at = chain_at("знч Х = Товар.Цены", 10)
    assert parts == ["Товар", "Цены"] and at == 0
    parts, at = chain_at("знч Х = Товар.Цены", 16)
    assert parts == ["Товар", "Цены"] and at == 1
    assert chain_at("    ", 2) is None


def test_definition_object_and_members():
    assert d("пер Т: Товар.Ссылка", 8) == ("Каталог/Товар.yaml", 3)
    assert d("знч Ц = Товар.Цены", 15) == ("Каталог/Товар.yaml", 40)
    assert d("пер К: Товар.ДанныеКарточки", 15) == ("Каталог/Товар.xbsl", 12)
    assert d("знч В = ВидТовара.Весовой", 20) == ("Каталог/ВидТовара.yaml", 9)


def test_definition_methods_and_components():
    assert d("Товар.Загрузить()", 8) == ("Каталог/Товар.xbsl", 20)
    assert d("Обновить()", 2) == ("Каталог/ГлавнаяФорма.xbsl", 5)  # свой модуль по file_stem
    assert d("Компоненты.Кнопка.Видимость", 12) == ("Каталог/ГлавнаяФорма.yaml", 33)
    assert d("Компоненты.Кнопка.Нажать()", 20) == ("Каталог/Кнопка.xbsl", 7)


def test_definition_yaml_handler():
    assert d("    Обработчик: Обновить", 20, language_id="yaml",
             file_path="Каталог/ГлавнаяФорма.yaml") == ("Каталог/ГлавнаяФорма.xbsl", 5)
    # вне значения обработчика – молчание
    assert d("    Обработчик: Обновить", 3, language_id="yaml") is None


def test_definition_unknown_contexts():
    assert d("Неведомое.Что", 3) is None
    assert d("А.Б.В.Г", 6) is None  # глубокая цепочка без Компоненты – вне охвата


def c(prefix, language_id="xbsl", file_stem="ГлавнаяФорма"):
    return resolve_completions(LOOKUP, language_id=language_id, line_prefix=prefix, file_stem=file_stem)


def test_completion_object_members():
    labels = {e["label"] for e in c("знч Х = Товар.")}
    assert {"Ссылка", "Объект", "Цены", "ДанныеКарточки", "Загрузить"} <= labels


def test_completion_enum_values():
    entries = c("пер В = ВидТовара.")
    assert [e["label"] for e in entries] == ["Весовой"]
    assert entries[0]["kind"] == "enumMember"


def test_completion_components_and_methods():
    assert [e["label"] for e in c("Компоненты.")] == ["Кнопка"]
    assert [e["label"] for e in c("Компоненты.Кнопка.")] == ["Нажать"]


def test_completion_yaml_type():
    labels = [e["label"] for e in c("    Тип: ", language_id="yaml")]
    assert labels == ["Товар", "ВидТовара"]
    assert c("просто текст") is None


def test_hover_object_method_component():
    h = resolve_hover(LOOKUP, language_id="xbsl", line_text="пер Т: Товар", character=9,
                      file_stem="ГлавнаяФорма")
    assert "Справочник Товар" in h and "Цены" in h
    h = resolve_hover(LOOKUP, language_id="xbsl", line_text="Товар.Загрузить()", character=8,
                      file_stem="ГлавнаяФорма")
    assert "метод Товар.Загрузить" in h and "@НаСервере" in h
    h = resolve_hover(LOOKUP, language_id="xbsl", line_text="Компоненты.Кнопка", character=13,
                      file_stem="ГлавнаяФорма")
    assert "Компонент Кнопка" in h
    assert resolve_hover(LOOKUP, language_id="xbsl", line_text="Неведомое", character=2,
                         file_stem="ГлавнаяФорма") is None
