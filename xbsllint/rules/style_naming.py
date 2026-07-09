"""Именование (CODE_STYLE, раздел 2).

- 2.1 UpperCamelCase у имён (кроме констант);
- 2.2 в аббревиатурах заглавная только первая буква (`ТелоJson`, не `ТелоJSON`);
- 2.3 константы – БОЛЬШИМИ_БУКВАМИ_С_ПОДЧЁРКИВАНИЯМИ;
- 2.4 типы исключений – с префиксом "Исключение";
- 2.5 в именах перечислений – "Вид", а не "Тип".

Проверяются только имена, которые объявляет сам модуль (методы и их параметры, знч/пер,
структуры, перечисления, исключения). Обращения к чужим именам не трогаем: аббревиатура
может прийти из stdlib или из чужого кода, и переименовать её мы не вправе.
"""

from __future__ import annotations

import re
from collections.abc import Iterable

from xbsllint.diagnostics import Diagnostic, Severity
from xbsllint.engine import SourceFile, rule
from xbsllint.lexer import Token
from xbsllint.rules._syntax import code_tokens, declarations, signatures

# Две и более подряд заглавные латинские буквы внутри имени – аббревиатура капсом.
_ABBREV_RE = re.compile(r"[A-Z]{2,}")
_LOCAL_TYPE_KEYWORDS = ("STRUCTURE", "ENUMERATION", "EXCEPTION")
_ENUM_BAD_PREFIXES = ("Тип", "Type")
_EXCEPTION_PREFIXES = ("Исключение", "Exception")


def _is_const_name(name: str) -> bool:
    """Имя константы: буква в начале, ни одной строчной буквы (ВЕРСИЯ_СЕРВЕРА, API_URL)."""
    return name[:1].isalpha() and not any(ch.islower() for ch in name)


def _local_type_names(toks: list[Token], canonical: str | None = None) -> list[Token]:
    """Имена структур, перечислений и исключений (или только одного вида)."""
    wanted = (canonical,) if canonical else _LOCAL_TYPE_KEYWORDS
    names: list[Token] = []
    for i, tok in enumerate(toks[:-1]):
        if tok.kind == "KEYWORD" and tok.canonical in wanted and tok.value[:1].islower():
            if toks[i + 1].kind == "IDENT":
                names.append(toks[i + 1])
    return names


def _declared_names(source: SourceFile) -> list[Token]:
    """Имена, объявленные модулем: методы, их параметры, знч/пер, локальные типы."""
    toks = code_tokens(source)
    names: list[Token] = []
    for sig in signatures(toks):
        names.append(sig.name)
        names.extend(p.name for p in sig.params)
    for decl in declarations(toks):
        if decl.keyword.canonical == "CONST":
            continue  # у констант своё правило (2.3)
        names.extend(decl.names)
    names.extend(_local_type_names(toks))
    return names


def _structure_ranges(toks: list[Token]) -> list[tuple[int, int]]:
    """Смещения [начало, конец) тел структур – блок `структура ... ;` (с вложенностью)."""
    from xbsllint.rules.code_structure import _OPENERS

    ranges: list[tuple[int, int]] = []
    stack: list[tuple[bool, Token]] = []  # (это структура, токен-открыватель)
    for tok in toks:
        if tok.kind == "KEYWORD" and tok.canonical in _OPENERS and tok.value[:1].islower():
            stack.append((tok.canonical == "STRUCTURE", tok))
        elif tok.kind == "OP" and tok.value == ";" and stack:
            is_structure, opener = stack.pop()
            if is_structure:
                ranges.append((opener.start, tok.end))
    return ranges


@rule(
    "style/camel-case", "Имя не в UpperCamelCase", "C",
    severity=Severity.INFO, enabled_by_default=False,
)
def camel_case(source: SourceFile) -> Iterable[Diagnostic]:
    """2.1: `ВходящееСообщение`, не `входящееСообщение` и не `Степень_Важности`.

    Поля структур и параметры методов не проверяются: их имена часто диктует внешний
    контракт (ключи JSON Менеджера сервиса – `access_token`, `Ref_Key`, `apptype_id`),
    и переименовать их нельзя – сериализация идёт по именам полей.
    """
    if source.kind != "xbsl":
        return
    toks = code_tokens(source)
    structures = _structure_ranges(toks)

    names: list[Token] = [sig.name for sig in signatures(toks)]
    names.extend(_local_type_names(toks))
    for decl in declarations(toks):
        if decl.keyword.canonical == "CONST":
            continue  # у констант своё правило (2.3)
        if any(start <= decl.keyword.start < end for start, end in structures):
            continue  # поле структуры – имя задано контрактом
        names.extend(decl.names)

    for tok in names:
        name = tok.value
        problem = None
        if "_" in name:
            problem = "подчёркивание в имени"
        elif name[:1].islower():
            problem = "имя со строчной буквы"
        if problem is None:
            continue
        yield Diagnostic(
            source.rel, tok.line, tok.col, "style/camel-case", Severity.INFO,
            f"{problem.capitalize()} – '{name}': имена пишутся в UpperCamelCase.",
        )


@rule(
    "style/const-case", "Константа не БОЛЬШИМИ_БУКВАМИ", "C",
    severity=Severity.WARNING,
)
def const_case(source: SourceFile) -> Iterable[Diagnostic]:
    """2.3: `конст ВЕРСИЯ_СЕРВЕРА`, не `конст ВерсияСервера`."""
    if source.kind != "xbsl":
        return
    for decl in declarations(code_tokens(source)):
        if decl.keyword.canonical != "CONST":
            continue
        for name in decl.names:
            if _is_const_name(name.value):
                continue
            yield Diagnostic(
                source.rel, name.line, name.col, "style/const-case", Severity.WARNING,
                f"Имя константы '{name.value}' – константы пишутся "
                "БОЛЬШИМИ_БУКВАМИ_С_ПОДЧЁРКИВАНИЯМИ.",
            )


@rule("style/exception-prefix", "Имя исключения без префикса \"Исключение\"", "C",
      severity=Severity.WARNING)
def exception_prefix(source: SourceFile) -> Iterable[Diagnostic]:
    """2.4: `исключение ИсключениеЧтенияФайла`, не `исключение ЧтениеФайла`."""
    if source.kind != "xbsl":
        return
    for tok in _local_type_names(code_tokens(source), "EXCEPTION"):
        if tok.value.startswith(_EXCEPTION_PREFIXES):
            continue
        yield Diagnostic(
            source.rel, tok.line, tok.col, "style/exception-prefix", Severity.WARNING,
            f"Имя исключения '{tok.value}' – типы исключений пишутся с префиксом "
            f"'Исключение': 'Исключение{tok.value}'.",
        )


def _suggest(name: str) -> str:
    """Привести аббревиатуры капсом к виду с одной заглавной: ТелоJSON -> ТелоJson."""
    return _ABBREV_RE.sub(lambda m: m.group(0)[0] + m.group(0)[1:].lower(), name)


@rule(
    "style/abbreviation-case", "Аббревиатура заглавными буквами в имени", "C",
    severity=Severity.INFO, enabled_by_default=False,
)
def abbreviation_case(source: SourceFile) -> Iterable[Diagnostic]:
    """2.2: в аббревиатурах заглавная только первая буква (как в `Url`, `КлиентHttp`)."""
    if source.kind != "xbsl":
        return
    for tok in _declared_names(source):
        if not _ABBREV_RE.search(tok.value):
            continue
        yield Diagnostic(
            source.rel, tok.line, tok.col, "style/abbreviation-case", Severity.INFO,
            f"Аббревиатура заглавными в имени '{tok.value}' – "
            f"заглавной остаётся только первая буква: '{_suggest(tok.value)}'.",
        )


@rule("style/enum-name-vid", "Имя перечисления начинается с \"Тип\"", "C", severity=Severity.WARNING)
def enum_name_vid(source: SourceFile) -> Iterable[Diagnostic]:
    """2.5: в именах перечислений – "Вид", а не "Тип" (`ВидКнопки`, не `ТипКнопки`)."""
    if source.kind != "xbsl":
        return
    toks = code_tokens(source)
    for i, tok in enumerate(toks[:-1]):
        if not (tok.kind == "KEYWORD" and tok.canonical == "ENUMERATION" and tok.value[:1].islower()):
            continue
        name = toks[i + 1]
        if name.kind != "IDENT":
            continue
        for prefix in _ENUM_BAD_PREFIXES:
            rest = name.value[len(prefix):]
            if name.value.startswith(prefix) and rest[:1].isupper():
                yield Diagnostic(
                    source.rel, name.line, name.col, "style/enum-name-vid", Severity.WARNING,
                    f"Имя перечисления '{name.value}' начинается с '{prefix}' – "
                    f"в именах перечислений используется 'Вид': 'Вид{rest}'.",
                )
                break
