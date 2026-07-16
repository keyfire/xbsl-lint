"""Tier A: structural file checks (no code parsing)."""

from __future__ import annotations

from collections.abc import Iterable

from xbsl import i18n
from xbsl.diagnostics import Diagnostic, Severity
from xbsl.engine import SourceFile, rule

MESSAGES = {
    "structure/xbsl-pair.title": {
        "ru": "Модуль .xbsl без парного .yaml",
        "en": "Module .xbsl without a paired .yaml",
    },
    "structure/xbsl-pair.missing": {
        "ru": "Нет парного описания {name} для модуля.",
        "en": "No paired descriptor {name} for the module.",
    },
}
i18n.register(MESSAGES)

# An object module is written as a separate file `Имя.Объект.xbsl` (record event handlers)
# and has no .yaml of its own – it is described by `Имя.yaml`.
_MODULE_SUFFIXES = ("Объект", "Object")


def _owner_yaml(source: SourceFile):
    """The descriptor file that owns the module: for `Имя.Объект.xbsl` it is `Имя.yaml`."""
    stem = source.path.stem  # 'Полезное.Объект' or 'Полезное'
    base, _, suffix = stem.rpartition(".")
    if base and suffix in _MODULE_SUFFIXES:
        return source.path.with_name(base + ".yaml")
    return source.path.with_suffix(".yaml")


@rule("structure/xbsl-pair", "structure/xbsl-pair.title", "A", severity=Severity.WARNING)
def xbsl_pair(source: SourceFile) -> Iterable[Diagnostic]:
    # A module (.xbsl) is the code of an element described by a paired .yaml – a lone .xbsl is orphaned.
    # This checks files on disk: for in-memory content (lint_source) we do not check the pairing.
    if source.kind != "xbsl" or not source.path.exists():
        return
    yaml_path = _owner_yaml(source)
    if not yaml_path.exists():
        yield Diagnostic(
            source.rel, 1, 1, "structure/xbsl-pair", Severity.WARNING,
            i18n.t("structure/xbsl-pair.missing", name=yaml_path.name),
        )
