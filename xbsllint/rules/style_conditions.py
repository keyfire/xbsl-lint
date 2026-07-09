"""Условия и проверки (CODE_STYLE, раздел 8).

- 8.1 булевы значения не сравниваются с `Истина` / `Ложь`;
- 8.2 `Неопределено` проверяется через `==` / `!=`, а не через `это`;
- 8.3 оператор `это` отрицается внутри, а не снаружи.
"""

from __future__ import annotations

from collections.abc import Iterable

from xbsllint.diagnostics import Diagnostic, Severity
from xbsllint.engine import SourceFile, rule
from xbsllint.lexer import Token
from xbsllint.rules._syntax import code_tokens

_BOOLEAN_KEYWORDS = {"TRUE": "Истина", "FALSE": "Ложь"}
_COMPARE_OPS = ("==", "!=")


def _is_op(tok: Token, *values: str) -> bool:
    return tok.kind == "OP" and tok.value in values


def _is_kw(tok: Token, *canonicals: str) -> bool:
    return tok.kind == "KEYWORD" and tok.canonical in canonicals


@rule("style/boolean-compare", "Сравнение булева значения с Истина/Ложь", "C",
      severity=Severity.INFO, enabled_by_default=False)
def boolean_compare(source: SourceFile) -> Iterable[Diagnostic]:
    """8.1: `если Переменная`, а не `если Переменная == Истина`.

    Правило касается значений типа `Булево`. Для nullable (`Булево?`) краткая форма
    недопустима и сравнение с `Истина` обязательно – различить эти случаи по токенам
    нельзя, поэтому правило `info` и выключено по умолчанию: каждое место смотрят глазами.
    """
    if source.kind != "xbsl":
        return
    toks = code_tokens(source)
    for i, tok in enumerate(toks[:-1]):
        if not _is_op(tok, *_COMPARE_OPS):
            continue
        literal = None
        if _is_kw(toks[i + 1], *_BOOLEAN_KEYWORDS):
            literal = toks[i + 1]
        elif i > 0 and _is_kw(toks[i - 1], *_BOOLEAN_KEYWORDS):
            literal = toks[i - 1]
        if literal is None:
            continue
        yield Diagnostic(
            source.rel, tok.line, tok.col, "style/boolean-compare", Severity.INFO,
            f"Сравнение с '{_BOOLEAN_KEYWORDS[literal.canonical]}' – булево значение "
            "проверяется без сравнения ('если Значение', 'если не Значение'). "
            "Для nullable (Булево?) сравнение обязательно и нарушением не является.",
        )


@rule("style/undefined-is", "Проверка Неопределено оператором 'это'", "C",
      severity=Severity.WARNING)
def undefined_is(source: SourceFile) -> Iterable[Diagnostic]:
    """8.2: `если Значение == Неопределено`, а не `если Значение это Неопределено`."""
    if source.kind != "xbsl":
        return
    toks = code_tokens(source)
    for i, tok in enumerate(toks):
        if not _is_kw(tok, "IS"):
            continue
        j = i + 1
        negated = j < len(toks) and _is_kw(toks[j], "NOT")
        if negated:
            j += 1
        if j < len(toks) and _is_kw(toks[j], "UNDEFINED"):
            replacement = "!=" if negated else "=="
            yield Diagnostic(
                source.rel, tok.line, tok.col, "style/undefined-is", Severity.WARNING,
                f"'Неопределено' проверяется сравнением – использовать '{replacement} Неопределено'.",
            )


@rule("style/negated-is", "Отрицание оператора 'это' снаружи", "C", severity=Severity.WARNING)
def negated_is(source: SourceFile) -> Iterable[Diagnostic]:
    """8.3: `если Значение это не Строка`, а не `если не (Значение это Строка)`.

    Сообщаем только про простую скобку с единственным `это` внутри: составное отрицание
    (`не (X это Y и ...)`) переписывается не механически и требует разбора вручную.
    Выверено на корпусе: 0 срабатываний (оба тамошних места – составные).
    """
    if source.kind != "xbsl":
        return
    toks = code_tokens(source)
    n = len(toks)
    for i, tok in enumerate(toks):
        if not (_is_kw(tok, "NOT") and i + 1 < n and _is_op(toks[i + 1], "(")):
            continue
        depth, j = 0, i + 1
        is_count = 0
        compound = False
        while j < n:
            t = toks[j]
            if _is_op(t, "("):
                depth += 1
            elif _is_op(t, ")"):
                depth -= 1
                if depth == 0:
                    break
            elif depth == 1:
                if _is_kw(t, "IS"):
                    is_count += 1
                elif _is_kw(t, "AND", "OR"):
                    compound = True
            j += 1
        if is_count == 1 and not compound:
            yield Diagnostic(
                source.rel, tok.line, tok.col, "style/negated-is", Severity.INFO,
                "Отрицание 'это' снаружи скобок – отрицать внутри: 'Значение это не Тип'.",
            )
