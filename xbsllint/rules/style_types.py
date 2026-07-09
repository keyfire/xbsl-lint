"""Типы, инициализация и сигнатуры (CODE_STYLE, разделы 3 и 7).

- 3.1 тип отделяется двоеточием и пробелом после него;
- 3.2 в составном типе вокруг `|` пробелов нет;
- 3.3 `Неопределено` в типе записывается сокращением `?`;
- 3.4 при инициализации литералом или конструктором тип не указывается;
- 7.1 необязательные параметры – после обязательных.
"""

from __future__ import annotations

from collections.abc import Iterable

from xbsllint.diagnostics import Diagnostic, Severity
from xbsllint.engine import SourceFile, rule
from xbsllint.lexer import Token
from xbsllint.rules._syntax import (
    TypeExpr,
    code_tokens,
    declarations,
    signatures,
    type_expr,
)

# Литерал -> тип, который выводится из него без аннотации (3.4).
_LITERAL_TYPE = {"STRING": "Строка", "NUMBER": "Число"}
_BOOLEAN_KEYWORDS = ("TRUE", "FALSE")


def _type_positions(toks: list[Token]) -> list[tuple[Token, int]]:
    """Пары (двоеточие, индекс первого токена типа) во всех типовых позициях модуля."""
    out: list[tuple[Token, int]] = []
    for decl in declarations(toks):
        if decl.colon is not None and decl.type_start is not None:
            out.append((decl.colon, decl.type_start))
    for sig in signatures(toks):
        for param in sig.params:
            if param.colon is not None and param.type_start is not None:
                out.append((param.colon, param.type_start))
        if sig.return_colon is not None and sig.return_type_start is not None:
            out.append((sig.return_colon, sig.return_type_start))
    return out


def _type_exprs(toks: list[Token]) -> Iterable[TypeExpr]:
    for _colon, start in _type_positions(toks):
        te = type_expr(toks, start)
        if te is not None:
            yield te


def _text(source: SourceFile, toks: list[Token]) -> str:
    return source.text[toks[0].start: toks[-1].end]


@rule("style/type-colon-space", "Пробелы вокруг двоеточия типа", "C", severity=Severity.WARNING)
def type_colon_space(source: SourceFile) -> Iterable[Diagnostic]:
    """3.1: `пер Переменная: Строка` – без пробела перед `:` и с пробелом после."""
    if source.kind != "xbsl":
        return
    text = source.text
    for colon, _start in _type_positions(code_tokens(source)):
        before = text[colon.start - 1] if colon.start > 0 else ""
        after = text[colon.end] if colon.end < len(text) else ""
        if before in (" ", "\t"):
            yield Diagnostic(
                source.rel, colon.line, colon.col, "style/type-colon-space", Severity.WARNING,
                "Пробел перед двоеточием типа – тип отделяется двоеточием сразу после имени.",
            )
        if after not in (" ", "\r", "\n", ""):
            yield Diagnostic(
                source.rel, colon.line, colon.col, "style/type-colon-space", Severity.WARNING,
                "Нет пробела после двоеточия типа.",
            )


@rule("style/union-spaces", "Пробелы вокруг '|' в составном типе", "C",
      severity=Severity.WARNING)
def union_spaces(source: SourceFile) -> Iterable[Diagnostic]:
    """3.2: `Строка|Число|Булево`, не `Строка | Число | Булево`."""
    if source.kind != "xbsl":
        return
    text = source.text
    for te in _type_exprs(code_tokens(source)):
        for tok in te.toks:
            if not (tok.kind == "OP" and tok.value == "|"):
                continue
            before = text[tok.start - 1] if tok.start > 0 else ""
            after = text[tok.end] if tok.end < len(text) else ""
            if before in (" ", "\t") or after in (" ", "\t"):
                yield Diagnostic(
                    source.rel, tok.line, tok.col, "style/union-spaces", Severity.WARNING,
                    "Пробелы вокруг '|' в составном типе – писать слитно: 'Строка|Число'.",
                )


@rule("style/nullable-shorthand", "Неопределено в типе без сокращения '?'", "C",
      severity=Severity.WARNING)
def nullable_shorthand(source: SourceFile) -> Iterable[Diagnostic]:
    """3.3: два типа – слитно (`Строка?`), три и более – через `|` (`Строка|Число|?`)."""
    if source.kind != "xbsl":
        return
    for te in _type_exprs(code_tokens(source)):
        alts = te.alternatives
        if len(alts) < 2:
            continue

        for alt in alts:
            if len(alt) == 1 and alt[0].kind == "KEYWORD" and alt[0].canonical == "UNDEFINED":
                yield Diagnostic(
                    source.rel, alt[0].line, alt[0].col, "style/nullable-shorthand", Severity.WARNING,
                    "'Неопределено' в составном типе – записывается сокращением '?'.",
                )

        last = alts[-1]
        first_of_last = last[0]
        if len(alts) == 2 and len(last) == 1 and last[0].kind == "OP" and last[0].value == "?":
            yield Diagnostic(
                source.rel, first_of_last.line, first_of_last.col,
                "style/nullable-shorthand", Severity.WARNING,
                f"Два типа – '?' пишется слитно: '{_text(source, alts[0])}?', не '...|?'.",
            )
        elif len(last) > 1 and last[-1].kind == "OP" and last[-1].value == "?":
            yield Diagnostic(
                source.rel, last[-1].line, last[-1].col,
                "style/nullable-shorthand", Severity.WARNING,
                "Три и более типов – 'Неопределено' отделяется: '...|?', не '...Тип?'.",
            )


@rule("style/redundant-type", "Избыточная аннотация типа при инициализации", "C",
      severity=Severity.WARNING)
def redundant_type(source: SourceFile) -> Iterable[Diagnostic]:
    """3.4: при инициализации литералом или конструктором тип выводится и не пишется.

    Сообщаем только когда аннотация заведомо совпадает с выводимым типом: строковый или
    числовой литерал при типе `Строка`/`Число`, `Истина`/`Ложь` при типе `Булево`,
    конструктор `новый Т(...)` при том же `Т`. Пустые литералы `[]`/`{}` не трогаем –
    для них вывод типа невозможен и аннотация обязательна.
    """
    if source.kind != "xbsl":
        return
    toks = code_tokens(source)
    for decl in declarations(toks):
        if decl.type_start is None or decl.value_start is None:
            continue
        te = type_expr(toks, decl.type_start)
        if te is None or len(te.alternatives) != 1:
            continue
        annotation = _text(source, te.toks)
        if annotation.endswith("?"):  # nullable шире выводимого типа – аннотация нужна
            continue

        value = toks[decl.value_start]
        inferred: str | None = None
        if value.kind in _LITERAL_TYPE:
            inferred = _LITERAL_TYPE[value.kind]
        elif value.kind == "KEYWORD" and value.canonical in _BOOLEAN_KEYWORDS:
            inferred = "Булево"
        elif value.kind == "KEYWORD" and value.canonical == "NEW":
            ctor = type_expr(toks, decl.value_start + 1)
            inferred = _text(source, ctor.toks) if ctor is not None else None

        if inferred is None:
            continue
        if annotation.replace(" ", "") != inferred.replace(" ", ""):
            continue
        yield Diagnostic(
            source.rel, decl.colon.line, decl.colon.col, "style/redundant-type", Severity.WARNING,
            f"Тип '{annotation}' выводится из инициализации – аннотацию не писать.",
        )


@rule("style/optional-params-last", "Необязательный параметр перед обязательным", "C",
      severity=Severity.WARNING)
def optional_params_last(source: SourceFile) -> Iterable[Diagnostic]:
    """7.1: параметры со значением по умолчанию идут после обязательных."""
    if source.kind != "xbsl":
        return
    for sig in signatures(code_tokens(source)):
        seen_default = False
        for param in sig.params:
            if param.has_default:
                seen_default = True
            elif seen_default:
                yield Diagnostic(
                    source.rel, param.name.line, param.name.col,
                    "style/optional-params-last", Severity.WARNING,
                    f"Обязательный параметр '{param.name.value}' после необязательного – "
                    "необязательные параметры пишутся последними.",
                )
