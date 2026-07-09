"""Оформление кода (CODE_STYLE, разделы 1 и 6).

- 1.1 отступ – 4 пробела, табуляция запрещена;
- 1.2 максимальная длина строки – 120 символов (кроме строковых литералов);
- 1.3 составные инструкции закрываются `;` на отдельной строке;
- 6.1 операции переносятся в начало строки (исключение – `+` при конкатенации);
- 6.2 запятые при переносе параметров остаются в конце строк.

Блоки `Запрос{ ... }` – отдельный DSL, кодовые правила их не касаются.
"""

from __future__ import annotations

import re
from collections.abc import Iterable

from xbsllint.diagnostics import Diagnostic, Severity
from xbsllint.engine import SourceFile, rule
from xbsllint.rules._syntax import (
    code_tokens,
    in_query,
    inside,
    line_span,
    lines,
    spans_of,
)

MAX_LINE = 120

_INDENT_RE = re.compile(r"^[ \t]*")

# Операции, которые при переносе выражения должны стоять в начале новой строки.
# `+` исключён: документация прямо разрешает конец строки при конкатенации строк.
_WRAP_OPS = frozenset({"==", "!=", "<=", ">=", "*", "/", "%", "??", "**"})
_WRAP_KEYWORDS = frozenset({"AND", "OR", "NOT"})


@rule("style/tab-indent", "Табуляция в отступе", "B", severity=Severity.WARNING)
def tab_indent(source: SourceFile) -> Iterable[Diagnostic]:
    """1.1: отступ – 4 пробела, табуляция запрещена."""
    if source.kind != "xbsl":
        return
    strings = spans_of(source, ("STRING",))
    for num, text in enumerate(lines(source), start=1):
        indent = _INDENT_RE.match(text).group(0)
        pos = indent.find("\t")
        if pos < 0:
            continue
        start, _ = line_span(source, num)
        if inside(strings, start):  # строка внутри многострочного литерала
            continue
        yield Diagnostic(
            source.rel, num, pos + 1, "style/tab-indent", Severity.WARNING,
            "Табуляция в отступе – отступ задаётся четырьмя пробелами.",
        )


@rule(
    "style/line-length", "Строка длиннее 120 символов", "B",
    severity=Severity.INFO, enabled_by_default=False,
)
def line_length(source: SourceFile) -> Iterable[Diagnostic]:
    """1.2: максимальная длина строки – 120 символов.

    Строковые литералы исключены: документация разрешает длинные строки, когда разбиение
    снижает читаемость, а в проекте это HTML/CSS/SVG во вставках. Признак – символ на
    121-й позиции лежит внутри строкового литерала.
    """
    if source.kind != "xbsl":
        return
    strings = spans_of(source, ("STRING",))
    for num, text in enumerate(lines(source), start=1):
        if len(text) <= MAX_LINE:
            continue
        start, _ = line_span(source, num)
        overflow = start + MAX_LINE
        if inside(strings, overflow) or in_query(source, overflow):
            continue
        yield Diagnostic(
            source.rel, num, MAX_LINE + 1, "style/line-length", Severity.INFO,
            f"Длина строки {len(text)} > {MAX_LINE} символов – перенести выражение.",
        )


@rule("style/semicolon-line", "';' не на отдельной строке", "C", severity=Severity.WARNING)
def semicolon_own_line(source: SourceFile) -> Iterable[Diagnostic]:
    """1.3: `;` закрывает составную инструкцию и пишется на отдельной строке."""
    if source.kind != "xbsl":
        return
    for tok in code_tokens(source):
        if not (tok.kind == "OP" and tok.value == ";"):
            continue
        before = lines(source)[tok.line - 1][: tok.col - 1]
        if before.strip():
            yield Diagnostic(
                source.rel, tok.line, tok.col, "style/semicolon-line", Severity.WARNING,
                "';' закрывает составную инструкцию и пишется на отдельной строке "
                "с отступом самой инструкции.",
            )


@rule("style/wrap-operator", "Операция в конце перенесённой строки", "C", severity=Severity.WARNING)
def wrap_operator(source: SourceFile) -> Iterable[Diagnostic]:
    """6.1: при переносе выражения операция пишется в начале новой строки (кроме `+`)."""
    if source.kind != "xbsl":
        return
    toks = code_tokens(source)
    for i, tok in enumerate(toks[:-1]):
        if toks[i + 1].line == tok.end_line:
            continue  # не последний токен строки
        is_op = tok.kind == "OP" and tok.value in _WRAP_OPS
        is_kw = tok.kind == "KEYWORD" and tok.canonical in _WRAP_KEYWORDS
        if is_op or is_kw:
            yield Diagnostic(
                source.rel, tok.line, tok.col, "style/wrap-operator", Severity.WARNING,
                f"Операция '{tok.value}' в конце перенесённой строки – "
                "переносить операцию в начало следующей строки.",
            )


@rule("style/wrap-comma", "Запятая в начале перенесённой строки", "C", severity=Severity.WARNING)
def wrap_comma(source: SourceFile) -> Iterable[Diagnostic]:
    """6.2: при переносе списка параметров запятые остаются в конце строк."""
    if source.kind != "xbsl":
        return
    toks = code_tokens(source)
    for i, tok in enumerate(toks):
        if not (tok.kind == "OP" and tok.value == ","):
            continue
        if i > 0 and toks[i - 1].end_line == tok.line:
            continue  # запятая продолжает строку – всё верно
        yield Diagnostic(
            source.rel, tok.line, tok.col, "style/wrap-comma", Severity.WARNING,
            "Запятая в начале перенесённой строки – запятые остаются в конце строк.",
        )
