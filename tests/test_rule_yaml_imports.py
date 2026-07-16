"""Проверки правила yaml/missing-import (импорт чужой подсистемы в yaml)."""

import pytest

from xbsl import dataset, engine
from xbsl.rules import semantics

RULE = "yaml/missing-import"

# Раскладка мини-проекта: подсистема А использует справочник Товары из подсистемы Б.
SUB_A = "Использование:\n    - Б\n"
SUB_B = "Интерфейс:\n    ВключатьВАвтоИнтерфейс: Ложь\n"
GOODS = (
    "ВидЭлемента: Справочник\n"
    "Имя: Товары\n"
    "ОбластьВидимости: ВПроекте\n"
)
FORM_HEAD = (
    "ВидЭлемента: КомпонентИнтерфейса\n"
    "Имя: Форма\n"
)
FORM_BODY = (
    "Наследует:\n"
    "    Тип: Группа\n"
    "Реквизиты:\n"
    "    -\n"
    "        Имя: Товар\n"
    "        Тип: Товары.Ссылка?\n"
)


def _lint(files):
    sources = [engine.load_text(name, content) for name, content in files.items()]
    return engine.run_sources(sources, select={RULE})


def _project(form_yaml, **extra):
    files = {
        "А/Подсистема.yaml": SUB_A,
        "Б/Подсистема.yaml": SUB_B,
        "Б/Товары.yaml": GOODS,
        "А/Форма.yaml": form_yaml,
    }
    files.update(extra)
    return files


def test_rule_registered_project_scope():
    info = next(r for r in engine.active_rules() if r.id == RULE)
    assert info.tier == "D" and info.scope == "project" and info.enabled_by_default


def test_cross_subsystem_with_import_ok():
    form = FORM_HEAD + "Импорт:\n    - Б\n" + FORM_BODY
    assert _lint(_project(form)) == []


def test_cross_subsystem_without_import_flagged():
    diags = _lint(_project(FORM_HEAD + FORM_BODY))
    assert len(diags) == 1
    d = diags[0]
    assert d.rule_id == RULE
    assert "Товары.Ссылка" in d.message and "'Б'" in d.message
    assert d.line == 8  # строка "        Тип: Товары.Ссылка?"


def test_empty_import_section_flagged():
    form = FORM_HEAD + "Импорт:\n" + FORM_BODY  # секция есть, но пустая
    assert len(_lint(_project(form))) == 1


def test_import_of_other_subsystem_does_not_cover():
    form = FORM_HEAD + "Импорт:\n    - В\n" + FORM_BODY
    files = _project(form)
    files["В/Подсистема.yaml"] = ""
    assert len(_lint(files)) == 1


def test_generic_argument_flagged():
    form = (
        FORM_HEAD
        + "Наследует:\n"
        + "    Тип: Группа\n"
        + "Свойства:\n"
        + "    -\n"
        + "        Имя: Отбор\n"
        + "        Тип: Массив<Товары.Ссылка>\n"
    )
    diags = _lint(_project(form))
    assert len(diags) == 1 and "Товары" in diags[0].message


def test_two_usages_one_diagnostic():
    form = (
        FORM_HEAD
        + FORM_BODY
        + "    -\n"
        + "        Имя: Аналог\n"
        + "        Тип: Товары.Ссылка\n"
    )
    assert len(_lint(_project(form))) == 1


def test_same_subsystem_no_import_ok():
    form = FORM_HEAD + FORM_BODY
    files = {
        "Б/Подсистема.yaml": SUB_B,
        "Б/Товары.yaml": GOODS,
        "Б/Форма.yaml": form,
    }
    assert _lint(files) == []


def test_private_target_skipped():
    # ВПодсистеме (и по умолчанию) объект снаружи невидим – это не пропавший импорт.
    private = "ВидЭлемента: Справочник\nИмя: Товары\nОбластьВидимости: ВПодсистеме\n"
    files = _project(FORM_HEAD + FORM_BODY)
    files["Б/Товары.yaml"] = private
    assert _lint(files) == []

    default = "ВидЭлемента: Справочник\nИмя: Товары\n"
    files["Б/Товары.yaml"] = default
    assert _lint(files) == []


def test_xbsl_import_does_not_cover_yaml():
    # Грабля: импорт в парном модуле есть, а в yaml – нет.
    files = _project(FORM_HEAD + FORM_BODY)
    files["А/Форма.xbsl"] = "импорт Б\n"
    assert len(_lint(files)) == 1


def test_own_subsystem_name_wins():
    # Имя есть и в своей подсистеме – короткое имя разрешается локально, импорт не нужен.
    files = _project(FORM_HEAD + FORM_BODY)
    files["А/Товары.yaml"] = "ВидЭлемента: Справочник\nИмя: Товары\n"
    assert _lint(files) == []


def test_stdlib_collision_skipped(monkeypatch):
    # Имя совпадает с типом stdlib – без импорта оно разрешится в стандартное пространство.
    monkeypatch.setattr(semantics, "_stdlib_names", lambda: frozenset({"Товары"}))
    assert _lint(_project(FORM_HEAD + FORM_BODY)) == []


@pytest.mark.skipif(
    not dataset.available_versions(),
    reason="нет данных Элемента – токенизация модулей недоступна",
)
def test_local_type_collision_skipped():
    # Имя совпадает со структурой, объявленной в модуле, – ссылку в yaml не трогаем.
    files = _project(FORM_HEAD + FORM_BODY)
    files["А/Общий.xbsl"] = "структура Товары\n    поле Ссылка: Строка\n;\n"
    files["А/Общий.yaml"] = "ВидЭлемента: ОбщийМодуль\nИмя: Общий\n"
    assert _lint(files) == []


def test_two_foreign_candidates_listed_and_any_import_ok():
    dup = "ВидЭлемента: Справочник\nИмя: Товары\nОбластьВидимости: ВПроекте\n"
    files = _project(FORM_HEAD + FORM_BODY)
    files["В/Подсистема.yaml"] = ""
    files["В/Товары.yaml"] = dup
    diags = _lint(files)
    assert len(diags) == 1 and "'Б/В'" in diags[0].message

    files["А/Форма.yaml"] = FORM_HEAD + "Импорт:\n    - В\n" + FORM_BODY
    assert _lint(files) == []


def test_no_subsystem_layout_skipped():
    files = {
        "Товары.yaml": GOODS,
        "Форма.yaml": FORM_HEAD + FORM_BODY,
    }
    assert _lint(files) == []


def test_qualified_and_binding_values_skipped():
    form = (
        FORM_HEAD
        + "Наследует:\n"
        + "    Тип: Группа\n"
        + "Реквизиты:\n"
        + "    -\n"
        + "        Имя: Товар\n"
        + "        Тип: Б::Товары.Ссылка?\n"
        + "    -\n"
        + "        Имя: Значение\n"
        + "        Тип: =ВычислитьТип()\n"
    )
    assert _lint(_project(form)) == []
