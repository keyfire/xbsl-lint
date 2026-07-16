"""Tier C: basic syntax the compiler rejects but the token layer can already see.

The linter has no full parser, so the checks here are deliberately narrow: they fire only on
shapes the platform grammar rules out, never on ones it merely makes unusual. Sources:

- methods (topics/methods-in-built-in-script-language): a parameter is
  `имя-параметра: тип-параметра[ = значение-по-умолчанию]`. The type is not optional in the
  grammar, but real code omits it when a default value is given (the platform infers the type
  from it) – so only a parameter with neither a type nor a default is reported;
- loops (topics/for-in-loop, topics/for-loop): `для значение-элемента из коллекция` or
  `для счетчик = выражение [вниз] по выражение [шаг N]`. A `для` header with neither `из`
  nor `=` after the name cannot compile.

`попытка` deliberately has no rule: per topics/exceptions both `поймать` and `вконце` are
optional, so a bare `попытка ... ;` is not an error.
"""

from __future__ import annotations

from collections.abc import Iterable

from xbsl import i18n
from xbsl.diagnostics import Diagnostic, Severity
from xbsl.engine import SourceFile, rule
from xbsl.rules._syntax import WORD_KINDS, code_tokens, signatures

MESSAGES = {
    "code/param-type-required.title": {
        "ru": "Параметр без типа и без значения по умолчанию",
        "en": "Parameter without a type and without a default value",
    },
    "code/param-type-required.no-type": {
        "ru": "У параметра '{name}' нет типа: параметр пишется как 'Имя: Тип' "
              "(тип можно опустить только при значении по умолчанию – тогда он выводится из него).",
        "en": "Parameter '{name}' has no type: a parameter is written as 'Имя: Тип' "
              "(the type may be omitted only with a default value – it is inferred from it).",
    },
    "code/loop-header.title": {
        "ru": "Неверный заголовок цикла 'для'",
        "en": "Malformed 'для' loop header",
    },
    "code/loop-header.expected": {
        "ru": "После '{name}' ожидается 'из' (обход коллекции) или '=' со счётчиком "
              "('для {name} = 1 по 10'), а не '{found}'.",
        "en": "'{name}' must be followed by 'из' (iterate a collection) or '=' with a counter "
              "('для {name} = 1 по 10'), not '{found}'.",
    },
}
i18n.register(MESSAGES)


@rule("code/param-type-required", "code/param-type-required.title", "C", severity=Severity.ERROR)
def param_type_required(source: SourceFile) -> Iterable[Diagnostic]:
    """A parameter with neither a type annotation nor a default value cannot be typed."""
    if source.kind != "xbsl":
        return
    for sig in signatures(code_tokens(source)):
        for param in sig.params:
            if param.colon is None and not param.has_default:
                yield Diagnostic(
                    source.rel, param.name.line, param.name.col,
                    "code/param-type-required", Severity.ERROR,
                    i18n.t("code/param-type-required.no-type", name=param.name.value),
                )


def _next_word(toks: list, i: int) -> int:
    j = i + 1
    while j < len(toks) and toks[j].kind == "COMMENT":
        j += 1
    return j


@rule("code/loop-header", "code/loop-header.title", "C", severity=Severity.ERROR)
def loop_header(source: SourceFile) -> Iterable[Diagnostic]:
    """`для X` continues with `из` (collection) or `=` (counter) – nothing else compiles."""
    if source.kind != "xbsl":
        return
    toks = code_tokens(source)
    n = len(toks)
    for i, t in enumerate(toks):
        if t.kind != "KEYWORD" or t.canonical != "FOR":
            continue
        j = _next_word(toks, i)
        if j >= n or toks[j].kind not in WORD_KINDS:
            continue  # не заголовок цикла в узнаваемом виде – не гадаем
        name = toks[j]
        k = _next_word(toks, j)
        if k >= n:
            continue
        nxt = toks[k]
        if nxt.kind == "KEYWORD" and nxt.canonical == "IN":
            continue
        if nxt.kind == "OP" and nxt.value == "=":
            continue
        yield Diagnostic(
            source.rel, name.line, name.col, "code/loop-header", Severity.ERROR,
            i18n.t("code/loop-header.expected", name=name.value, found=nxt.value),
        )
