"""Tier D: the top-level properties of a yaml object against the Element metamodel.

The configuration metamodel (xbsl/data/.../metamodel.json, produced by
tools/extract_metamodel.py) describes, for every class, the allowed properties (@PropertyInfo
from .xcore) and the inheritance. The rule checks the TOP-LEVEL keys of a yaml object: a key that
is not in the set of properties of the root class (following inheritance) plus the universal
wrapper keys (common) is an invalid property (a typo or a copy-over from another vid).

Only vetted vids: if `ВидЭлемента` is not in the metamodel vid2class, the object is not checked –
this rules out false positives on the unvetted vids. Only the top level is checked (not the nested
components) – validating those needs resolving the node type by discriminators (a separate stage).
"""

from __future__ import annotations

import re
from collections.abc import Iterable
from functools import lru_cache

from xbsl import dataset, i18n
from xbsl.diagnostics import Diagnostic, Severity
from xbsl.engine import SourceFile, rule
from xbsl.lexer import linemap
from xbsl.rules.yaml_schema import _HAVE_YAML, _is_object, _parsed

MESSAGES = {
    "yaml/unknown-property.title": {
        "ru": "Неизвестное свойство объекта",
        "en": "Unknown object property",
    },
    "yaml/unknown-property.unknown": {
        "ru": "Свойство '{prop}' недопустимо для вида '{vid}'.",
        "en": "Property '{prop}' is not allowed for vid '{vid}'.",
    },
}
i18n.register(MESSAGES)

# A top-level yaml key: a name at the start of the line (no indent) up to the colon.
_TOPKEY_RE = re.compile(r"(?m)^([^\s#:][^:\n]*):")


@lru_cache(maxsize=1)
def _metamodel():
    try:
        return dataset.load_json("metamodel.json")
    except (dataset.DatasetError, KeyError, ValueError):
        return None


@lru_cache(maxsize=None)
def _allowed_for_class(name: str) -> frozenset[str]:
    """The properties of a class following inheritance (transitively over ext)."""
    mm = _metamodel()
    if not mm:
        return frozenset()
    classes = mm["classes"]
    out: set[str] = set()
    seen: set[str] = set()
    stack = [name]
    while stack:
        c = stack.pop()
        if c in seen:
            continue
        seen.add(c)
        node = classes.get(c)
        if not node:
            continue
        out.update(node["props"])
        stack.extend(node["ext"])
    return frozenset(out)


@rule("yaml/unknown-property", "yaml/unknown-property.title", "D", severity=Severity.WARNING)
def unknown_property(source: SourceFile) -> Iterable[Diagnostic]:
    if source.kind != "yaml" or not _HAVE_YAML:
        return []
    mm = _metamodel()
    if not mm:
        return []  # the metamodel is not generated – skip the check
    data, err = _parsed(source)
    if err is not None or not _is_object(data):
        return []
    vid = data.get("ВидЭлемента")
    cls = mm["vid2class"].get(vid)
    if not cls:
        return []  # the vid is not vetted – skip it
    allowed = set(_allowed_for_class(cls)) | set(mm["common"])

    diags: list[Diagnostic] = []
    lm = linemap(source)
    for m in _TOPKEY_RE.finditer(source.text):
        key = m.group(1).strip()
        if key in data and key not in allowed:  # only the real top-level keys
            line, col = lm.linecol(m.start(1))
            diags.append(Diagnostic(
                source.rel, line, col, "yaml/unknown-property", Severity.WARNING,
                i18n.t("yaml/unknown-property.unknown", prop=key, vid=vid),
            ))
    return diags
