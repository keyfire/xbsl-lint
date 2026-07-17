"""Tier D: project enumerations in yaml type positions must be nullable.

The yaml/enum-needs-nullable rule: a `Тип` value naming a project enumeration without the
nullable marker – an object attribute, a tabular-section attribute, a component property or
a parameter `Тип: ВидПолезного`, or an input field `Тип: ПолеВвода<ВидПолезного>` – does not
compile on the server: an enumeration has no implicit default value, so the platform demands
one ('...cannot be initialized with a default value'; the fix is `ВидПолезного?` /
`ПолеВвода<ВидПолезного?>`).

Legal non-nullable forms (per the platform docs) are skipped:
- an enumeration where one of `Элементы` carries `ПоУмолчанию: Истина` has a default value
  of its own (topics/enumeration-properties), so its bare uses are never flagged;
- a node that sets `ЗначениеПоУмолчанию` next to `Тип` provides the default explicitly
  (topics/catalog-properties, topics/component-example) and is skipped; positions are found
  by a text search, so when the same value string occurs in one file both with and without
  the guard, the whole value is skipped in that file (a false negative, never a false
  positive).

Narrowing (deliberate, to keep the zero-false-positive bar): only the two exact shapes are
flagged – a value that is the bare enumeration name, and `ПолеВвода<Имя>` with the bare name
as the only argument. Unions (`ВидПолезного|Строка`), other generics (`Массив<ВидПолезного>`)
and qualified names are left alone – whether the compiler demands a default there is not
certain. Only yaml files with `ВидЭлемента` are checked; the values are taken from the parsed
yaml tree, so a `Тип: ...` line inside a literal block scalar cannot false-match. The rule is
project-wide – it needs the enumerations of the whole project (it does not run in single-file
mode).
"""

from __future__ import annotations

import re
from collections.abc import Iterable

from xbsl import i18n
from xbsl.diagnostics import Diagnostic, Severity
from xbsl.engine import SourceFile, rule
from xbsl.rules.yaml_schema import _HAVE_YAML, _parsed
from xbsl.rules.yaml_types import _value_positions

MESSAGES = {
    "yaml/enum-needs-nullable.title": {
        "ru": "Перечисление без nullable",
        "en": "Enumeration without nullable",
    },
    "yaml/enum-needs-nullable.bare": {
        "ru": "Тип '{name}' – перечисление без '?': значения по умолчанию нет, серверная "
              "компиляция упадёт. Укажите '{name}?' либо задайте значение по умолчанию "
              "(ЗначениеПоУмолчанию рядом с Тип или ПоУмолчанию: Истина у элемента перечисления).",
        "en": "Type '{name}' – an enumeration without '?': there is no default value, the "
              "server-side compilation will fail. Use '{name}?' or provide a default "
              "(ЗначениеПоУмолчанию next to Тип or ПоУмолчанию: Истина on an enumeration element).",
    },
    "yaml/enum-needs-nullable.input": {
        "ru": "Тип 'ПолеВвода<{name}>' – аргумент-перечисление без '?': значения по умолчанию "
              "нет, серверная компиляция упадёт. Укажите 'ПолеВвода<{name}?>'.",
        "en": "Type 'ПолеВвода<{name}>' – an enumeration argument without '?': there is no "
              "default value, the server-side compilation will fail. Use 'ПолеВвода<{name}?>'.",
    },
}
i18n.register(MESSAGES)

# `ПолеВвода<Имя>` with a single bare-name argument (no '?', no union, no FQN).
_INPUT_FIELD_RE = re.compile(
    r"^\s*ПолеВвода\s*<\s*([A-Za-zА-Яа-яЁё_][A-Za-zА-Яа-яЁё_0-9]*)\s*>\s*$"
)


def _typed_nodes(node) -> Iterable[dict]:
    """All dict nodes of the parsed yaml tree that carry a string `Тип` key."""
    if isinstance(node, dict):
        if isinstance(node.get("Тип"), str):
            yield node
        for v in node.values():
            yield from _typed_nodes(v)
    elif isinstance(node, list):
        for item in node:
            yield from _typed_nodes(item)


def _enum_nullable_mapper(source: SourceFile) -> dict | None:
    """The map phase: an enumeration yaml contributes (name, has-default); every object
    yaml contributes its plain-shape Тип candidates - (potential enum name, message key,
    guarded flag, positions). Which names are project enumerations is the reduce's call."""
    if not _HAVE_YAML or source.kind != "yaml":
        return None
    data, err = _parsed(source)
    if err is not None or not isinstance(data, dict):
        return None
    fact: dict = {}
    if data.get("ВидЭлемента") == "Перечисление" and isinstance(data.get("Имя"), str):
        items = data.get("Элементы")
        has_default = isinstance(items, list) and any(
            isinstance(item, dict) and item.get("ПоУмолчанию") in (True, "Истина")
            for item in items
        )
        fact["enum"] = (data["Имя"], has_default)
    if data.get("ВидЭлемента"):
        # a Тип value -> candidate; guarded - values with an explicit default
        candidates: dict[str, tuple[str, int, str]] = {}
        guarded: set[str] = set()
        for node in _typed_nodes(data):
            value = node["Тип"]
            hit = _plain_enum_shape(value)
            if hit is None:
                continue
            if "ЗначениеПоУмолчанию" in node:
                guarded.add(value)
            else:
                candidates[value] = hit
        cands = []
        for value, (name, off, msg_key) in candidates.items():
            if value in guarded:
                continue  # positions are textual - a same-name guarded value is indistinguishable
            positions = _value_positions(source, value)
            positions = [(line, col + off) for line, col in positions] or [(1, 1)]
            cands.append((name, msg_key, positions))
        if cands:
            fact["cands"] = cands
    if not fact:
        return None
    fact["k"] = "y"
    return fact


def _plain_enum_shape(value: str) -> tuple[str, int, str] | None:
    """(potential enumeration name, offset within the value, message key) or None.

    Catches exactly two shapes: a bare name and ПолеВвода<Имя> with a bare argument.
    """
    stripped = value.strip()
    if stripped and re.match(r"^[A-Za-zА-Яа-яЁё_][A-Za-zА-Яа-яЁё_0-9]*$", stripped):
        return stripped, value.index(stripped), "yaml/enum-needs-nullable.bare"
    m = _INPUT_FIELD_RE.match(value)
    if m:
        return m.group(1), m.start(1), "yaml/enum-needs-nullable.input"
    return None


@rule(
    "yaml/enum-needs-nullable", "yaml/enum-needs-nullable.title", "D",
    scope="project", severity=Severity.WARNING, mapper=_enum_nullable_mapper,
)
def enum_needs_nullable(facts: dict[str, dict]) -> Iterable[Diagnostic]:
    enums: set[str] = set()
    with_default: set[str] = set()
    for fact in facts.values():
        if "enum" in fact:
            name, has_default = fact["enum"]
            enums.add(name)
            if has_default:
                with_default.add(name)
    enums -= with_default
    if not enums:
        return
    for rel, fact in facts.items():
        for name, msg_key, positions in fact.get("cands", ()):
            if name not in enums:
                continue
            for line, col in positions:
                yield Diagnostic(
                    rel, line, col, "yaml/enum-needs-nullable", Severity.WARNING,
                    i18n.t(msg_key, name=name),
                )
