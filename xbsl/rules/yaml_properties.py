"""Tier D: the top-level properties of a yaml object against the Element metamodel.

The metamodel (`xbsl/metamodel.py` over the generated metamodel.json) knows the properties of
every configuration element kind. The rule checks the TOP-LEVEL keys of a yaml object: a key that
is not among them is an invalid property (a typo or a copy-over from another vid).

Only vetted vids are judged - the ones whose class has been checked against real sources; for the
rest the rule stays silent, which rules out false positives where the class may be incomplete.
Only the top level is checked (not the nested components) - validating those needs resolving the
node type by discriminators (a separate stage).
"""

from __future__ import annotations

import re
from collections.abc import Iterable

from xbsl import i18n, metamodel
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


@rule("yaml/unknown-property", "yaml/unknown-property.title", "D", severity=Severity.WARNING)
def unknown_property(source: SourceFile) -> Iterable[Diagnostic]:
    if source.kind != "yaml" or not _HAVE_YAML:
        return []
    if not metamodel.available():
        return []  # the metamodel is not generated – skip the check
    data, err = _parsed(source)
    if err is not None or not _is_object(data):
        return []
    vid = data.get("ВидЭлемента")
    if not isinstance(vid, str) or not metamodel.is_vetted(vid):
        return []  # the vid is not vetted – skip it
    allowed = metamodel.allowed_keys(vid)

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
