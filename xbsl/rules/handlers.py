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

from xbsl import i18n
from xbsl.diagnostics import Diagnostic, Severity
from xbsl.engine import SourceFile, rule
from xbsl.lexer import linemap, tokens

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


def _handler_pair_stem(rel: str) -> str:
    slash = rel.replace("\\", "/")
    return slash[: slash.rfind(".")] if "." in slash.rsplit("/", 1)[-1] else slash


def _handler_mapper(source: SourceFile) -> dict | None:
    """The map phase: a yaml contributes its handler references with positions, a module
    the set of its method names - the reduce joins the pair."""
    if source.kind == "xbsl":
        # Even an empty method set matters: a paired module WITHOUT the referenced
        # method is exactly what the rule flags.
        methods = _module_methods(source)
        return {"k": "x", "stem": _handler_pair_stem(source.rel), "methods": sorted(methods)}
    if source.kind != "yaml":
        return None
    refs: list[tuple[str, int, int]] = []
    lm = None
    for m in _HANDLER_RE.finditer(source.text):
        name = m.group(1).strip()
        if not _IDENT_RE.match(name):
            continue  # FQN reference to an external module or a non-identifier – skip
        if lm is None:
            lm = linemap(source)
        line, col = lm.linecol(m.start(1))
        refs.append((name, line, col))
    if not refs:
        return None
    return {
        "k": "y",
        "stem": _handler_pair_stem(source.rel),
        "module_file": source.path.with_suffix(".xbsl").name,
        "refs": refs,
    }


@rule(
    "form/unknown-handler", "form/unknown-handler.title", "D",
    scope="project", severity=Severity.WARNING, mapper=_handler_mapper,
)
def unknown_handler(facts: dict[str, dict]) -> Iterable[Diagnostic]:
    methods_by_stem: dict[str, set[str]] = {}
    for fact in facts.values():
        if fact["k"] == "x":
            methods_by_stem[fact["stem"]] = set(fact["methods"])
    for rel, fact in facts.items():
        if fact["k"] != "y":
            continue
        methods = methods_by_stem.get(fact["stem"])
        if methods is None:
            continue  # no paired module – nothing to resolve handlers against
        for name, line, col in fact["refs"]:
            if name not in methods:
                yield Diagnostic(
                    rel, line, col, "form/unknown-handler", Severity.WARNING,
                    i18n.t(
                        "form/unknown-handler.not-found",
                        name=name, module=fact["module_file"],
                    ),
                )
