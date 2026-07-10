"""Extension points: external packages add rules and data via entry points.

The "xbsllint.rules" group – the value points to a module whose import registers rules with
the @rule decorator (see xbsllint/engine.py). The "xbsllint.data" group – the value points to
a data root: a path (Path/str) or a zero-argument callable returning a path.

Declaration in a third-party package's pyproject.toml:

    [project.entry-points."xbsllint.rules"]
    package-name = "my_package.rules"

    [project.entry-points."xbsllint.data"]
    package-name = "my_package:data_root"

The XBSLLINT_NO_PLUGINS=1 environment variable disables both groups – a run with the built-in
rules and data only.

A failing entry point is an error, not a warning: a linter that silently drops a rule stays
green in CI and stops guaranteeing anything.
"""

from __future__ import annotations

import os
from importlib.metadata import EntryPoint, entry_points
from pathlib import Path

RULES_GROUP = "xbsllint.rules"
DATA_GROUP = "xbsllint.data"
ENV_DISABLE = "XBSLLINT_NO_PLUGINS"

_FALSY = {"", "0", "false", "no"}


class PluginError(RuntimeError):
    pass


def disabled() -> bool:
    return os.environ.get(ENV_DISABLE, "").strip().lower() not in _FALSY


def _points(group: str) -> list[EntryPoint]:
    if disabled():
        return []
    return sorted(entry_points(group=group), key=lambda ep: ep.name)


def _load(ep: EntryPoint):
    try:
        return ep.load()
    except Exception as exc:
        raise PluginError(
            f"Точка расширения '{ep.name}' группы {ep.group} не загрузилась "
            f"({ep.value}): {exc}"
        ) from exc


def load_rules() -> list[str]:
    """Import external packages' rule modules; return the names of the loaded entry points."""
    loaded: list[str] = []
    for ep in _points(RULES_GROUP):
        _load(ep)
        loaded.append(ep.name)
    return loaded


def data_roots() -> list[Path]:
    """Data roots declared by external packages (ordered by entry-point name)."""
    roots: list[Path] = []
    for ep in _points(DATA_GROUP):
        target = _load(ep)
        if callable(target):
            target = target()
        roots.append(Path(target))
    return roots
