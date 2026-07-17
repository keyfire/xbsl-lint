"""Тесты правила code/statement-no-effect: оператор-выражение обязан иметь эффект.

Ловим опечатки, которые парсер принимает как валидные выражения-операторы
(`возрат 5`, `Х == 5` вместо `Х = 5`); эффектом считаются вызов, создание и бросок,
а также непрозрачные литералы (богатая строка с интерполяцией, Запрос{}, Ресурс{}).
"""

from __future__ import annotations

from xbsl.diagnostics import Diagnostic
from xbsl.engine import load_text, run_sources


def _lint(code: str) -> list[Diagnostic]:
    src = load_text("Модуль.xbsl", code)
    return list(run_sources([src], select={"code/statement-no-effect"}, scopes=("file",)))


def test_catches_keyword_typo():
    diags = _lint(
        "метод Тест(): Число\n"
        "    возрат 5\n"
        ";\n"
    )
    assert len(diags) == 2  # имя `возрат` и отброшенное `5`
    assert all(d.rule_id == "code/statement-no-effect" for d in diags)


def test_catches_dropped_comparison():
    diags = _lint(
        "метод Тест(Х: Число)\n"
        "    Х == 5\n"
        ";\n"
    )
    assert len(diags) == 1


def test_catches_inside_lambda_body():
    diags = _lint(
        "метод Тест()\n"
        "    знч Ф = метод () ->\n"
        "        возрат 1\n"
        "    ;\n"
        ";\n"
    )
    assert len(diags) == 2


def test_calls_creations_throws_are_effects():
    diags = _lint(
        "метод Тест(Спс: Массив<Число>)\n"
        "    Сообщить(\"привет\")\n"
        "    Спс.Добавить(1)\n"
        "    новый ДеньНедели()\n"
        "    Условие() ? Раз() : Два()\n"
        "    выбросить новый Исключение(\"стоп\")\n"
        ";\n"
    )
    assert diags == [], [d.message for d in diags]


def test_interpolated_string_is_an_effect():
    # вызов может прятаться в %{...} - лексер держит богатую строку одним токеном
    diags = _lint(
        "метод Тест(Журнал: Массив<Строка>)\n"
        "    \"%{Журнал.Очистить()}\"\n"
        ";\n"
    )
    assert diags == []


def test_plain_string_statement_is_flagged():
    diags = _lint(
        "метод Тест()\n"
        "    \"забытая строка\"\n"
        ";\n"
    )
    assert len(diags) == 1


def test_broken_file_is_left_to_parse_error():
    diags = _lint(
        "метод Тест()\n"
        "    Ф(1, 2\n"
        ";\n"
    )
    assert diags == []  # там уже работает code/parse-error
