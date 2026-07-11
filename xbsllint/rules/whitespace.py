"""Tier B: whitespace, newlines, encoding (over the raw text, without parsing code)."""

from __future__ import annotations

import re
from collections.abc import Iterable

from xbsllint import i18n
from xbsllint.diagnostics import Diagnostic, Severity, TextEdit
from xbsllint.engine import SourceFile, rule
from xbsllint.lexer import linemap

MESSAGES = {
    "whitespace/trailing.title": {
        "ru": "Хвостовые пробелы",
        "en": "Trailing whitespace",
    },
    "whitespace/trailing.msg": {
        "ru": "Хвостовые пробелы в конце строки.",
        "en": "Trailing whitespace at the end of the line.",
    },
    "whitespace/mixed-newline.title": {
        "ru": "Смешанные переводы строк",
        "en": "Mixed newlines",
    },
    "whitespace/mixed-newline.msg": {
        "ru": "В файле смешаны переводы строк (CRLF и LF) – привести к одному виду.",
        "en": "The file mixes newlines (CRLF and LF) – bring them to a single style.",
    },
    "encoding/utf8.title": {
        "ru": "Файл не в UTF-8",
        "en": "File is not UTF-8",
    },
    "encoding/utf8.msg": {
        "ru": "Файл не читается как UTF-8: {error}",
        "en": "File cannot be read as UTF-8: {error}",
    },
}
i18n.register(MESSAGES)

_TRAILING_RE = re.compile(r"[ \t]+(?=\r|\n|$)")


@rule("whitespace/trailing", "whitespace/trailing.title", "B", severity=Severity.WARNING)
def trailing_whitespace(source: SourceFile) -> Iterable[Diagnostic]:
    lm = linemap(source)
    for m in _TRAILING_RE.finditer(source.text):
        line, col = lm.linecol(m.start())
        yield Diagnostic(
            source.rel, line, col, "whitespace/trailing", Severity.WARNING,
            i18n.t("whitespace/trailing.msg"),
            fix=TextEdit(m.start(), m.end(), ""),  # delete the trailing run
        )


@rule("whitespace/mixed-newline", "whitespace/mixed-newline.title", "B", severity=Severity.WARNING)
def mixed_newline(source: SourceFile) -> Iterable[Diagnostic]:
    if source.newline == "mixed":
        # A whole-file fix (normalize every newline to the dominant style), not a span edit –
        # the fixer applies it by rule id, so no TextEdit is attached here.
        yield Diagnostic(
            source.rel, 1, 1, "whitespace/mixed-newline", Severity.WARNING,
            i18n.t("whitespace/mixed-newline.msg"),
        )


@rule("encoding/utf8", "encoding/utf8.title", "B", severity=Severity.ERROR)
def encoding_utf8(source: SourceFile) -> Iterable[Diagnostic]:
    if source.decode_error:
        yield Diagnostic(
            source.rel, 1, 1, "encoding/utf8", Severity.ERROR,
            i18n.t("encoding/utf8.msg", error=source.decode_error),
        )
