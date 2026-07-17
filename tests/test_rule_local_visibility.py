"""Checks of the code/local-method-cross-component rule (cross-component calls).

The rule needs no stdlib/metamodel catalogs, but the lexer requires language.json - the
module is skipped without the Element data the same way conftest skips the base modules
(this file is not in its list, hence the local guard).
"""

import pytest

from xbsl import dataset, engine
from xbsl.cli import discover

if not dataset.available_versions():
    pytest.skip(
        "нет данных Элемента – сгенерируйте tools/extract_grammar.py",
        allow_module_level=True,
    )

RULE = "code/local-method-cross-component"


def _has(diags, rule_id=RULE):
    return any(d.rule_id == rule_id for d in diags)


def _проект(tmp_path, код_страницы, код_роутера=None, yaml_роутера=None):
    """A mini project: the Страница component + a router that embeds it and calls Загрузить."""
    (tmp_path / "Страница.yaml").write_text(
        "ВидЭлемента: КомпонентИнтерфейса\nИмя: Страница\n", encoding="utf-8"
    )
    (tmp_path / "Страница.xbsl").write_text(код_страницы, encoding="utf-8")
    (tmp_path / "Роутер.yaml").write_text(
        yaml_роутера
        or (
            "ВидЭлемента: КомпонентИнтерфейса\nИмя: Роутер\nСодержимое:\n"
            "    -\n        Тип: Страница\n        Имя: Страница\n"
        ),
        encoding="utf-8",
    )
    (tmp_path / "Роутер.xbsl").write_text(
        код_роутера or "метод Открыть()\n    Компоненты.Страница.Загрузить()\n;\n",
        encoding="utf-8",
    )
    return engine.run(discover([str(tmp_path)]), select={RULE})


_ЛОКАЛЬНЫЙ = "метод Загрузить()\n    возврат\n;\n"
_ВПОДСИСТЕМЕ = "@ВПодсистеме\nметод Загрузить()\n    возврат\n;\n"


# --- Diagnostics ------------------------------------------------------------------


def test_без_аннотации_видимости_ловится(tmp_path):
    d = _проект(tmp_path, _ЛОКАЛЬНЫЙ)
    assert len(d) == 1
    assert d[0].rule_id == RULE
    assert "Загрузить" in d[0].message and "Страница" in d[0].message
    # the position is the call site in the router module
    assert d[0].path.endswith("Роутер.xbsl") and d[0].line == 2


def test_явное_локально_ловится(tmp_path):
    d = _проект(tmp_path, "@Локально\nметод Загрузить()\n    возврат\n;\n")
    assert len(d) == 1


def test_статический_без_видимости_ловится(tmp_path):
    d = _проект(tmp_path, "@НаСервере\nстатический метод Загрузить()\n    возврат\n;\n")
    assert len(d) == 1


# --- Sufficient visibility --------------------------------------------------------


@pytest.mark.parametrize("аннотация", ["ВПодсистеме", "ВПроекте", "ВТипе", "Глобально"])
def test_широкая_видимость_не_ловится(tmp_path, аннотация):
    d = _проект(tmp_path, f"@{аннотация}\nметод Загрузить()\n    возврат\n;\n")
    assert not _has(d)


def test_видимость_среди_других_аннотаций_не_ловится(tmp_path):
    d = _проект(
        tmp_path,
        "@НаСервере @ДоступноСКлиента\n@ВПодсистеме\n"
        "статический метод Загрузить()\n    возврат\n;\n",
    )
    assert not _has(d)


# --- Guards -----------------------------------------------------------------------


def test_встроенный_метод_платформы_не_ловится(tmp_path):
    # ВызватьМетод is not declared in the component module - it is a built-in instance method
    d = _проект(
        tmp_path,
        _ЛОКАЛЬНЫЙ,
        код_роутера="метод Открыть()\n    Компоненты.Страница.ВызватьМетод(\"х\", [])\n;\n",
    )
    assert not _has(d)


def test_свойство_не_вызов_не_ловится(tmp_path):
    d = _проект(
        tmp_path,
        _ЛОКАЛЬНЫЙ,
        код_роутера="метод Открыть()\n    Компоненты.Страница.Видимость = Истина\n;\n",
    )
    assert not _has(d)


def test_затенение_имени_компоненты_пропускает_модуль(tmp_path):
    d = _проект(
        tmp_path,
        _ЛОКАЛЬНЫЙ,
        код_роутера=(
            "метод Открыть(Компоненты: Структура)\n"
            "    Компоненты.Страница.Загрузить()\n;\n"
        ),
    )
    assert not _has(d)


def test_вызов_в_комментарии_не_ловится(tmp_path):
    d = _проект(
        tmp_path,
        _ЛОКАЛЬНЫЙ,
        код_роутера="метод Открыть()\n    // Компоненты.Страница.Загрузить()\n    возврат\n;\n",
    )
    assert not _has(d)


def test_экземпляр_другого_типа_с_тем_же_именем_не_ловится(tmp_path):
    # the 'Страница' instance in the form is NOT the project component Страница
    d = _проект(
        tmp_path,
        _ЛОКАЛЬНЫЙ,
        yaml_роутера=(
            "ВидЭлемента: КомпонентИнтерфейса\nИмя: Роутер\nСодержимое:\n"
            "    -\n        Тип: КонтейнерHtml\n        Имя: Страница\n"
        ),
    )
    assert not _has(d)


def test_компонент_не_встроен_в_форму_не_ловится(tmp_path):
    d = _проект(
        tmp_path,
        _ЛОКАЛЬНЫЙ,
        yaml_роутера="ВидЭлемента: КомпонентИнтерфейса\nИмя: Роутер\n",
    )
    assert not _has(d)


def test_вызывающий_не_компонент_не_ловится(tmp_path):
    # a module without a paired КомпонентИнтерфейса yaml - it has no Компоненты collection
    (tmp_path / "Страница.yaml").write_text(
        "ВидЭлемента: КомпонентИнтерфейса\nИмя: Страница\n", encoding="utf-8"
    )
    (tmp_path / "Страница.xbsl").write_text(_ЛОКАЛЬНЫЙ, encoding="utf-8")
    (tmp_path / "Модуль.xbsl").write_text(
        "метод Открыть()\n    Компоненты.Страница.Загрузить()\n;\n", encoding="utf-8"
    )
    d = engine.run(discover([str(tmp_path)]), select={RULE})
    assert not _has(d)


def test_вызов_в_своём_модуле_не_ловится(tmp_path):
    # the component calls itself (same module - visibility does not restrict)
    (tmp_path / "Страница.yaml").write_text(
        "ВидЭлемента: КомпонентИнтерфейса\nИмя: Страница\nСодержимое:\n"
        "    -\n        Тип: Страница\n        Имя: Страница\n",
        encoding="utf-8",
    )
    (tmp_path / "Страница.xbsl").write_text(
        "метод Загрузить()\n    возврат\n;\n"
        "метод Открыть()\n    Компоненты.Страница.Загрузить()\n;\n",
        encoding="utf-8",
    )
    d = engine.run(discover([str(tmp_path)]), select={RULE})
    assert not _has(d)


def test_вызов_члена_другого_объекта_не_ловится(tmp_path):
    # Что.Компоненты.Страница.Загрузить() - here Компоненты is another object's member
    d = _проект(
        tmp_path,
        _ЛОКАЛЬНЫЙ,
        код_роутера="метод Открыть(Что: Структура)\n    Что.Компоненты.Страница.Загрузить()\n;\n",
    )
    assert not _has(d)


def test_одиночный_буфер_без_yaml_не_ловится(tmp_path):
    # without the project yaml the components are unknown - a standalone buffer gets no diagnostics
    d = engine.run_sources(
        [engine.load_text("Роутер.xbsl", "метод Ф()\n    Компоненты.Страница.Загрузить()\n;\n")],
        select={RULE},
    )
    assert not _has(d)
