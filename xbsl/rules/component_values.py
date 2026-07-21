"""Tier D: enumeration values of component properties against the ui schema.

The yaml/unknown-enum-value rule. A component property whose type is an enumeration accepts
only the elements of that enumeration; anything else is rejected when the build is applied –
`Неизвестный элемент "Анонимный" перечисления "РежимАутентификации"` (a compiler message
recorded on a probe), the class that also covers the alignment gotcha: the horizontal axis
has `Начало|Центр|Конец|ПоШирине` while the vertical one has `Верх|Центр|Низ|ПоБазовойЛинии`,
so a `ВыравниваниеСодержимогоПоВертикали: Конец` copied over from a neighbouring property
does not exist.

The value lists come from the ui schema (uischema.json, `tools/extract_uischema.py`), which
is exactly what the compiler validates against: every property carries its union of types
plus the resolved `enum` list.

Zero-false-positive guards:

- a node is judged only when its `Тип` names a component the schema knows (the generic head
  is taken: `ПолеВвода<Строка>` -> `ПолеВвода`); a project component is skipped, so its own
  properties can never be mistaken for the platform's;
- a property is judged only when EVERY member of its type union is either an enumeration of
  the schema or the literal `Авто` – the only non-enumeration member the schema uses next to
  an `enum` (354 occurrences, no other). One `Строка`/`Булево`/`Число` member and the
  property is skipped: such a value may be anything;
- a binding (`=...`), an interpolation (`%...`), a qualified value
  (`ВыравниваниеПоГоризонтали.Центр` – the enumeration spelled out) and a non-scalar are
  skipped, as is a block scalar (text, not a value).

Corpus survey before the rule was written: 2619 component nodes, 2545 property values judged,
zero findings – deployed code follows the schema, so the rule guards against regressions and
against a value invented from a neighbouring axis.
"""

from __future__ import annotations

import re
from collections.abc import Iterable
from functools import lru_cache

from xbsl import dataset, i18n
from xbsl.diagnostics import Diagnostic, Severity
from xbsl.engine import SourceFile, rule
from xbsl.rules.yaml_schema import (
    _composed,
    _HAVE_YAML,
    _is_object,
    _mapping_nodes,
    _parsed,
    _scalar_entries,
)

if _HAVE_YAML:
    import yaml

MESSAGES = {
    "yaml/unknown-enum-value.title": {
        "ru": "Недопустимое значение свойства",
        "en": "Invalid property value",
    },
    "yaml/unknown-enum-value.unknown": {
        "ru": "Значение '{value}' недопустимо для свойства '{prop}' компонента '{component}' – "
              "применение сборки отвергнет его как неизвестный элемент перечисления. "
              "Допустимые значения: {allowed}.",
        "en": "Value '{value}' is not allowed for property '{prop}' of component "
              "'{component}' – applying the build rejects it as an unknown enumeration "
              "element. Allowed values: {allowed}.",
    },
}
i18n.register(MESSAGES)

#: Union members that are a VALUE rather than a type with an open set of values.
_LITERAL_MEMBERS = frozenset({"Авто"})


def _allowed_values(prop: dict, enums: dict) -> frozenset[str] | None:
    """The value set of a purely enumerated property, or None when it is not one."""
    allowed = set(prop.get("enum") or ())
    if not allowed:
        return None
    for member in prop.get("types") or ():
        name = str(member).strip().rstrip("?")
        if not name:
            continue
        if name in _LITERAL_MEMBERS:
            allowed.add(name)
        elif name in enums:
            allowed.update(enums[name].get("values") or ())
        else:
            return None  # a real type among the members – the value may be anything
    return frozenset(allowed)


@lru_cache(maxsize=1)
def _enumerated_props() -> tuple[dict[str, dict[str, frozenset[str]]], "re.Pattern | None"]:
    """({component: {property: allowed values}}, a key regex), both empty without a schema.

    Built once: resolving the dataset is not free (it walks the installed data plugins), and
    the value sets are the same for every file. The regex is the fast path – composing the
    node graph costs a second, pure-python parse of the file, so it only happens when the
    text carries at least one key the rule could judge.
    """
    schema = dataset.load_ui_schema()
    if not schema:
        return {}, None
    enums = schema.get("enums") or {}
    table: dict[str, dict[str, frozenset[str]]] = {}
    names: set[str] = set()
    for component, rec in (schema.get("components") or {}).items():
        judged = {}
        for prop, info in (rec.get("props") or {}).items():
            allowed = _allowed_values(info, enums)
            if allowed is not None:
                judged[prop] = allowed
                names.add(prop)
        if judged:
            table[component] = judged
    if not names:
        return {}, None
    keys_re = re.compile(
        r"(?m)^[ \t]*(?:-[ \t]+)?(?:%s)[ \t]*:" % "|".join(sorted(map(re.escape, names)))
    )
    return table, keys_re


@rule("yaml/unknown-enum-value", "yaml/unknown-enum-value.title", "D", severity=Severity.ERROR)
def unknown_enum_value(source: SourceFile) -> Iterable[Diagnostic]:
    if source.kind != "yaml" or not _HAVE_YAML:
        return
    table, keys_re = _enumerated_props()
    if keys_re is None or not keys_re.search(source.text):
        return  # no ui schema, or nothing in this file the rule could judge
    data, err = _parsed(source)
    if err is not None or not _is_object(data):
        return
    root = _composed(source)
    if root is None:  # pragma: no cover - _parsed has already vetted the syntax
        return
    for mapping in _mapping_nodes(root):
        entries = _scalar_entries(mapping)
        type_entry = entries.get("Тип")
        if type_entry is None or not isinstance(type_entry[1], yaml.ScalarNode):
            continue
        component = type_entry[1].value.split("<", 1)[0].strip()
        props = table.get(component)
        if props is None:
            continue  # not a platform component (a project one, a data type, a generic)
        for key, (_key_node, value_node) in entries.items():
            allowed = props.get(key)
            if allowed is None or not isinstance(value_node, yaml.ScalarNode):
                continue
            if value_node.style in ("|", ">"):
                continue
            value = value_node.value.strip()
            if not value or value[0] in "=%" or value in allowed:
                continue
            if value.rsplit(".", 1)[-1] in allowed:
                continue  # a qualified value: ВыравниваниеПоГоризонтали.Центр
            yield Diagnostic(
                source.rel,
                value_node.start_mark.line + 1, value_node.start_mark.column + 1,
                "yaml/unknown-enum-value", Severity.ERROR,
                i18n.t(
                    "yaml/unknown-enum-value.unknown",
                    value=value, prop=key, component=component,
                    allowed=", ".join(sorted(allowed)),
                ),
            )
