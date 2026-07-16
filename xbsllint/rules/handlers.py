"""Tier D: form handlers reference methods that exist in the module.

In a form's yaml description an event is given by a handler key whose value is a method name
in the paired module (`Name.yaml` ↔ `Name.xbsl`). The rule catches the "renamed a method –
forgot to fix the form" drift (and vice versa) before the server-side compilation on deploy.

The set of handler keys is verified on the real corpus: for all of them the identifier value
always matches a method of the paired module (0 false positives). The set is extended when
needed. A value with a dot (an FQN reference to an external module) and a non-identifier are
not checked. The rule is cross-file: without the paired module handlers are not checked
(nothing to resolve against).
"""

from __future__ import annotations

import re
from collections.abc import Iterable

from xbsllint import i18n
from xbsllint.diagnostics import Diagnostic, Severity
from xbsllint.engine import SourceFile, rule
from xbsllint.lexer import linemap, tokens

MESSAGES = {
    "form/unknown-handler.title": {
        "ru": "Обработчик формы не найден в модуле",
        "en": "Form handler not found in the module",
    },
    "form/unknown-handler.not-found": {
        "ru": "Обработчик '{name}' не найден как метод в модуле формы '{module}'.",
        "en": "Handler '{name}' is not found as a method in the form module '{module}'.",
    },
}
i18n.register(MESSAGES)

_HANDLER_KEYS = (
    "Обработчик", "ПриНажатии", "ПриИзменении", "ПриВыделенииСтроки",
    "ПослеЗагрузкиСодержимого", "ПриСменеСтраницы", "ПриВыбореЭлемента",
)
_HANDLER_RE = re.compile(  # a trailing comment and CRLF are allowed after the value
    r"(?m)^[ \t]*(?:" + "|".join(_HANDLER_KEYS) + r"):[ \t]*([^\s#][^\n#]*?)[ \t]*(?:#.*)?\r?$"
)
_IDENT_RE = re.compile(r"^[^\W\d]\w*$", re.UNICODE)


def _module_methods(source: SourceFile) -> set[str]:
    """Names of the methods and constructors declared in the module."""
    toks = tokens(source)
    names: set[str] = set()
    for i, t in enumerate(toks):
        if t.kind == "KEYWORD" and t.canonical in ("METHOD", "CONSTRUCTOR") and t.value[:1].islower():
            j = i + 1
            while j < len(toks) and toks[j].kind == "COMMENT":
                j += 1
            if j < len(toks) and toks[j].kind == "IDENT":
                names.add(toks[j].value)
    return names


@rule(
    "form/unknown-handler", "form/unknown-handler.title", "D",
    scope="project", severity=Severity.WARNING,
)
def unknown_handler(sources: list[SourceFile]) -> Iterable[Diagnostic]:
    modules = {str(s.path): s for s in sources if s.kind == "xbsl"}

    diags: list[Diagnostic] = []
    for s in sources:
        if s.kind != "yaml":
            continue
        module = modules.get(str(s.path.with_suffix(".xbsl")))
        if module is None:
            continue  # no paired module – nothing to resolve handlers against
        methods = _module_methods(module)
        lm = linemap(s)
        for m in _HANDLER_RE.finditer(s.text):
            name = m.group(1).strip()
            if not _IDENT_RE.match(name):
                continue  # FQN reference to an external module or a non-identifier – skip
            if name not in methods:
                line, col = lm.linecol(m.start(1))
                diags.append(Diagnostic(
                    s.rel, line, col, "form/unknown-handler", Severity.WARNING,
                    i18n.t(
                        "form/unknown-handler.not-found",
                        name=name,
                        module=s.path.with_suffix(".xbsl").name,
                    ),
                ))
    return diags
