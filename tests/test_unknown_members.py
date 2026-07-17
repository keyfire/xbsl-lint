"""Tests of the code/unknown-member rule: member access on a variable of a known stdlib type.

First-hop and provable negatives only: entity aggregates (the record protocol is incomplete
in the docs), project and parameterized types, Latin member spellings - all skipped.
"""

from __future__ import annotations

from xbsl.diagnostics import Diagnostic
from xbsl.engine import load_text, run_sources


def _lint(code: str) -> list[Diagnostic]:
    src = load_text("Модуль.xbsl", code)
    return list(run_sources([src], select={"code/unknown-member"}, scopes=("file",)))


def test_typo_in_member_with_hint():
    diags = _lint(
        "метод Тест(Имя: Строка): Число\n"
        "    возврат Имя.ДлинаСтроки()\n"
        ";\n"
    )
    assert len(diags) == 1
    assert "Строка" in diags[0].message and "ДлинаСтроки" in diags[0].message


def test_known_member_passes():
    diags = _lint(
        "метод Тест(Имя: Строка): Число\n"
        "    возврат Имя.Длина()\n"
        ";\n"
    )
    assert diags == [], [d.message for d in diags]


def test_declared_variable_is_checked():
    diags = _lint(
        "метод Тест()\n"
        "    пер Момент: ДатаВремя = ДатаВремя.Сейчас()\n"
        "    Сообщить(Момент.НетТакогоЧлена)\n"
        ";\n"
    )
    assert len(diags) == 1


def test_project_type_is_silent():
    diags = _lint(
        "метод Тест(Запись: МояЗапись)\n"
        "    Сообщить(Запись.ЧтоУгодно)\n"
        ";\n"
    )
    assert diags == []


def test_generic_type_is_silent():
    # parameterized types are not checked (first-hop, no inference)
    diags = _lint(
        "метод Тест(Список: Массив<Строка>)\n"
        "    Список.НетТакого()\n"
        ";\n"
    )
    assert diags == []


def test_redeclared_name_is_silent():
    # a name with two differently typed declarations is poisoned - do not raise false accusations
    diags = _lint(
        "метод А(Значение: Строка)\n"
        "    Значение.НетТакого()\n"
        "    знч Ф = метод (Значение: Число) -> Значение\n"
        "    Ф(1)\n"
        ";\n"
    )
    assert diags == []


def test_entity_members_come_from_facets():
    # entity record and reference members live on the facet pages (Пользователи.Объект);
    # the aggregate name covers the union of the facets
    diags = _lint(
        "метод Тест(Пользователь: Пользователи)\n"
        "    Сообщить(Пользователь.Ид)\n"
        "    Сообщить(Пользователь.РазрешенДоступПоТокену)\n"
        ";\n"
    )
    assert diags == [], [d.message for d in diags]
    diags = _lint(
        "метод Тест(Пользователь: Пользователи)\n"
        "    Сообщить(Пользователь.НетТакогоЧлена)\n"
        ";\n"
    )
    assert len(diags) == 1


def test_facet_name_works_as_nominal_type():
    diags = _lint(
        "метод Тест(Данные: ДвоичныйОбъект.Ссылка)\n"
        "    Данные.Загрузить()\n"
        ";\n"
    )
    assert diags == [], [d.message for d in diags]
    diags = _lint(
        "метод Тест(Данные: ДвоичныйОбъект.Ссылка)\n"
        "    Данные.НетТакого()\n"
        ";\n"
    )
    assert len(diags) == 1
