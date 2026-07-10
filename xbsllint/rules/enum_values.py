"""Tier D: enumeration values against the project enum declarations.

The code/unknown-enum-value rule: a member access on a project enumeration –
`ВидСообщения.Важное` in code or `=ВидСообщения.Важное` in a yaml binding – must name a
declared value of that enumeration (yaml `Элементы[].Имя`) or a built-in member of the
generated enum type (Представление, ВСтроку, ПолучитьТип, Индекс). Only enumerations declared
as project objects (`ВидЭлемента: Перечисление`) are checked; module-local `перечисление`
declarations are left alone – their values live in code the compiler already sees locally.

Zero-false-positive guards. In code, an identifier may shadow the enumeration (a local
variable, a parameter, a loop variable – the platform resolves the name to the nearest
binding), so a module where the enum name is ever declared or assigned (`знч/пер/конст/обз/
поймать/для <Имя>`, `<Имя> =`, `<Имя>:`, `<Имя> ->`) is skipped for that name; comments and
`Запрос{...}` blocks are excluded via code_tokens; an access whose root is itself preceded by
`.` is a member of another object, not the enumeration. In yaml only binding values (strings
starting with `=`) are scanned, and a file where the enum name occurs as any `Имя:` (a field,
a property, an attribute of the form data) is skipped for that name. The rule is project-wide:
it needs the enumerations of the whole project.
"""

from __future__ import annotations

import re
from collections.abc import Iterable

from xbsllint import i18n
from xbsllint.diagnostics import Diagnostic, Severity
from xbsllint.engine import SourceFile, rule
from xbsllint.lexer import linemap
from xbsllint.rules._syntax import code_tokens
from xbsllint.rules.yaml_schema import _HAVE_YAML, _parsed

MESSAGES = {
    "code/unknown-enum-value.title": {
        "ru": "Неизвестное значение перечисления",
        "en": "Unknown enumeration value",
    },
    "code/unknown-enum-value.unknown": {
        "ru": "Неизвестное значение перечисления '{name}' – у перечисления '{root}' нет элемента '{seg}'.",
        "en": "Unknown enumeration value '{name}' – enumeration '{root}' has no element '{seg}'.",
    },
}
i18n.register(MESSAGES)

# Built-in members of the generated enum type (stdlib: {ИмяПеречисления}, Стд::Перечисление).
_ENUM_BUILTIN_MEMBERS = frozenset({"Представление", "ВСтроку", "ПолучитьТип", "Индекс"})

# Declaration keywords that bind a name (shadowing the enumeration in the whole module).
_DECL_KW = ("VAL", "VAR", "CONST", "REQ", "CATCH", "FOR")


def _project_enums(sources: list[SourceFile]) -> dict[str, set[str]]:
    """Имя перечисления проекта -> имена его элементов (yaml Элементы[].Имя)."""
    enums: dict[str, set[str]] = {}
    for s in sources:
        if s.kind != "yaml":
            continue
        data, err = _parsed(s)
        if err is not None or not isinstance(data, dict):
            continue
        if data.get("ВидЭлемента") != "Перечисление" or not isinstance(data.get("Имя"), str):
            continue
        values: set[str] = set()
        items = data.get("Элементы")
        if isinstance(items, list):
            for item in items:
                if isinstance(item, dict) and isinstance(item.get("Имя"), str):
                    values.add(item["Имя"])
        enums[data["Имя"]] = values
    return enums


def _shadowed_names(toks: list) -> set[str]:
    """Names bound anywhere in the module: declarations, assignments, annotations, lambdas.

    Wider than necessary on purpose – a shadowed name only makes the rule skip, never report.
    """
    names: set[str] = set()
    n = len(toks)
    for i, t in enumerate(toks):
        if t.kind == "KEYWORD" and t.value[:1].islower() and t.canonical in _DECL_KW:
            for j in range(i + 1, min(i + 3, n)):
                if toks[j].kind == "IDENT":
                    names.add(toks[j].value)
                    break
        elif t.kind == "IDENT" and i + 1 < n and toks[i + 1].kind == "OP":
            # `Объект.Имя = ...` is a member assignment, not a binding of the bare name
            member = i > 0 and toks[i - 1].kind == "OP" and toks[i - 1].value == "."
            if not member and toks[i + 1].value in ("=", ":", "->"):
                names.add(t.value)
    return names


def _code_diags(s: SourceFile, enums: dict[str, set[str]]) -> Iterable[Diagnostic]:
    toks = code_tokens(s)
    shadowed = _shadowed_names(toks)
    n = len(toks)
    for i, t in enumerate(toks):
        if t.kind != "IDENT" or t.value not in enums or t.value in shadowed:
            continue
        if i > 0 and toks[i - 1].kind == "OP" and toks[i - 1].value == ".":
            continue  # member of another object, not the enumeration
        if not (i + 2 < n and toks[i + 1].kind == "OP" and toks[i + 1].value == "."
                and toks[i + 2].kind == "IDENT"):
            continue
        seg = toks[i + 2]
        if seg.value in enums[t.value] or seg.value in _ENUM_BUILTIN_MEMBERS:
            continue
        yield Diagnostic(
            s.rel, seg.line, seg.col, "code/unknown-enum-value", Severity.WARNING,
            i18n.t("code/unknown-enum-value.unknown",
                   name=f"{t.value}.{seg.value}", root=t.value, seg=seg.value),
        )


def _binding_values(node) -> Iterable[str]:
    """All binding strings (`=выражение`) in the parsed yaml tree."""
    if isinstance(node, dict):
        for v in node.values():
            yield from _binding_values(v)
    elif isinstance(node, list):
        for item in node:
            yield from _binding_values(item)
    elif isinstance(node, str) and node.startswith("="):
        yield node


def _name_values(node) -> set[str]:
    """All string values of `Имя` keys in the parsed yaml tree (fields, properties...)."""
    names: set[str] = set()
    if isinstance(node, dict):
        for k, v in node.items():
            if k == "Имя" and isinstance(v, str):
                names.add(v)
            names |= _name_values(v)
    elif isinstance(node, list):
        for item in node:
            names |= _name_values(item)
    return names


def _yaml_diags(s: SourceFile, enums: dict[str, set[str]]) -> Iterable[Diagnostic]:
    data, err = _parsed(s)
    if err is not None or not isinstance(data, dict) or not data.get("ВидЭлемента"):
        return
    local_names = _name_values(data)
    bad: set[tuple[str, str]] = set()
    for binding in _binding_values(data):
        for root, seg in re.findall(
            r"(?<![\wА-Яа-яЁё.])([А-ЯЁ][\wА-Яа-яЁё]*)\.([А-Яа-яЁёA-Za-z_][\wА-Яа-яЁё]*)",
            binding,
        ):
            values = enums.get(root)
            if values is None or root in local_names:
                continue
            if seg not in values and seg not in _ENUM_BUILTIN_MEMBERS:
                bad.add((root, seg))
    lm = linemap(s)
    for root, seg in sorted(bad):
        pat = re.compile(r"(?<![\wА-Яа-яЁё.])" + re.escape(f"{root}.{seg}") + r"(?![\wА-Яа-яЁё])")
        positions = [lm.linecol(m.start()) for m in pat.finditer(s.text)] or [(1, 1)]
        for line, col in positions:
            yield Diagnostic(
                s.rel, line, col, "code/unknown-enum-value", Severity.WARNING,
                i18n.t("code/unknown-enum-value.unknown",
                       name=f"{root}.{seg}", root=root, seg=seg),
            )


@rule(
    "code/unknown-enum-value", "code/unknown-enum-value.title", "D",
    scope="project", severity=Severity.WARNING,
)
def unknown_enum_value(sources: list[SourceFile]) -> Iterable[Diagnostic]:
    if not _HAVE_YAML:
        return []
    enums = _project_enums(sources)
    if not enums:
        return []

    diags: list[Diagnostic] = []
    for s in sources:
        if s.kind == "xbsl":
            diags.extend(_code_diags(s, enums))
        elif s.kind == "yaml":
            diags.extend(_yaml_diags(s, enums))
    return diags
