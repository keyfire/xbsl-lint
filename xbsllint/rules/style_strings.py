"""Коллекции и строки (CODE_STYLE, разделы 4 и 5).

- 4.1 литерал коллекции предпочтительнее ручного наполнения;
- 5.1 полагаться на неявное преобразование, а не на `.ВСтроку()`;
- 5.2 интерполяция предпочтительнее конкатенации.

Все три правила описывают долг существующего кода (сотни мест), поэтому они `info` и
выключены по умолчанию – включаются через `--select`.
"""

from __future__ import annotations

from collections.abc import Iterable

from xbsllint.diagnostics import Diagnostic, Severity
from xbsllint.engine import SourceFile, rule
from xbsllint.lexer import Token
from xbsllint.rules._syntax import code_tokens, declarations, type_expr

# Конструкторы коллекций и методы их наполнения (4.1).
_COLLECTION_FILL = {
    "Массив": ("Добавить",),
    "Множество": ("Добавить",),
    "Соответствие": ("Вставить",),
    "Список": ("Добавить",),
}
_TOSTRING = "ВСтроку"


def _is_op(tok: Token, *values: str) -> bool:
    return tok.kind == "OP" and tok.value in values


@rule("style/collection-literal", "Ручное наполнение коллекции вместо литерала", "C",
      severity=Severity.INFO, enabled_by_default=False)
def collection_literal(source: SourceFile) -> Iterable[Diagnostic]:
    """4.1: `пер Кнопки = [Да, Нет]` вместо конструктора и цепочки `.Добавить()`.

    Сообщаем только когда сразу за объявлением идёт наполнение той же переменной: внутри
    цикла `.Добавить()` уместен, и такие места правило не трогает.
    """
    if source.kind != "xbsl":
        return
    toks = code_tokens(source)
    for decl in declarations(toks):
        if decl.value_start is None or len(decl.names) != 1:
            continue
        value = toks[decl.value_start]
        if not (value.kind == "KEYWORD" and value.canonical == "NEW"):
            continue
        ctor = type_expr(toks, decl.value_start + 1)
        if ctor is None or ctor.toks[0].kind != "IDENT":
            continue
        fill_methods = _COLLECTION_FILL.get(ctor.toks[0].value)
        if fill_methods is None:
            continue
        # конструктор без аргументов: `()` сразу за типом
        k = ctor.end
        if not (k + 1 < len(toks) and _is_op(toks[k], "(") and _is_op(toks[k + 1], ")")):
            continue

        name = decl.names[0].value
        j = k + 2
        if not (
            j + 2 < len(toks)
            and toks[j].kind == "IDENT" and toks[j].value == name
            and _is_op(toks[j + 1], ".")
            and toks[j + 2].kind == "IDENT" and toks[j + 2].value in fill_methods
        ):
            continue

        yield Diagnostic(
            source.rel, decl.keyword.line, decl.keyword.col,
            "style/collection-literal", Severity.INFO,
            f"Коллекция '{name}' наполняется вызовами '{toks[j + 2].value}' сразу после "
            "создания – записать литералом коллекции.",
        )


def _tokens_by_line(toks: list[Token]) -> dict[int, list[Token]]:
    by_line: dict[int, list[Token]] = {}
    for tok in toks:
        by_line.setdefault(tok.line, []).append(tok)
    return by_line


@rule("style/redundant-tostring", "'.ВСтроку()' в конкатенации", "C",
      severity=Severity.INFO, enabled_by_default=False)
def redundant_tostring(source: SourceFile) -> Iterable[Diagnostic]:
    """5.1: `"Итерация №" + Счетчик`, а не `... + Счетчик.ВСтроку()` – преобразование неявное."""
    if source.kind != "xbsl":
        return
    toks = code_tokens(source)
    by_line = _tokens_by_line(toks)

    for i, tok in enumerate(toks[:-2]):
        if not (_is_op(tok, ".") and toks[i + 1].kind == "IDENT" and toks[i + 1].value == _TOSTRING):
            continue
        if not _is_op(toks[i + 2], "("):
            continue
        line_toks = by_line.get(tok.line, [])
        has_plus = any(_is_op(t, "+") for t in line_toks)
        has_string = any(t.kind == "STRING" for t in line_toks)
        if has_plus and has_string:
            yield Diagnostic(
                source.rel, toks[i + 1].line, toks[i + 1].col,
                "style/redundant-tostring", Severity.INFO,
                "'.ВСтроку()' в конкатенации со строкой – преобразование выполняется неявно.",
            )


@rule("style/interpolation", "Конкатенация вместо интерполяции", "C",
      severity=Severity.INFO, enabled_by_default=False)
def interpolation(source: SourceFile) -> Iterable[Diagnostic]:
    """5.2: `"Итерация №%Счетчик"` вместо `"Итерация №" + Счетчик`.

    Сообщаем только про склейку строкового литерала со значением: `"a" + "b"` – это перенос
    длинного текста, а не подстановка, и правило его не касается. На всю цепочку
    конкатенации – одно замечание: `"a" + X + "b" + Y` переписывается одной интерполяцией.
    """
    if source.kind != "xbsl":
        return
    toks = code_tokens(source)
    reported = [False]  # по одному флагу на уровень скобочной глубины

    for i, tok in enumerate(toks):
        if _is_op(tok, "(", "[", "{"):
            reported.append(False)
            continue
        if _is_op(tok, ")", "]", "}"):
            if len(reported) > 1:
                reported.pop()
            continue
        if _is_op(tok, ",", ";", "="):  # новый операнд/инструкция – новая цепочка
            reported[-1] = False
            continue
        if not _is_op(tok, "+") or i == 0 or i + 1 >= len(toks) or reported[-1]:
            continue

        left, right = toks[i - 1], toks[i + 1]
        left_str, right_str = left.kind == "STRING", right.kind == "STRING"
        if left_str == right_str:
            continue  # оба литерала (перенос текста) либо ни одного (не про строки)
        value = right if left_str else left
        if value.kind not in ("IDENT", "NUMBER") and not _is_op(value, ")"):
            continue
        reported[-1] = True
        yield Diagnostic(
            source.rel, tok.line, tok.col, "style/interpolation", Severity.INFO,
            "Конкатенация строки со значением – использовать интерполяцию "
            "('%Имя', '${выражение}').",
        )
