"""Tier D: cross-subsystem project types in yaml against the element's Импорт section.

The yaml/missing-import rule: a yaml element (a form, an object...) that uses, in a type
position (the string values of `Тип` keys, generic arguments included), a type generated
by a project object from ANOTHER subsystem must list that subsystem in its own `Импорт:`
section. The namespace import in the paired `.xbsl` module does not cover the yaml – such
a project deploys, but the component initialization fails at runtime.

An element's subsystem is determined by the source layout: a directory with a
`Подсистема.yaml` is a subsystem root (the subsystem name is the directory name, or the
file's `Имя` when present), and every element under it belongs to that subsystem
(packages included – within one subsystem all packages see each other, so only the
subsystem boundary matters).

Narrowings for zero false positives (verified on a real project corpus):

- only foreign objects with `ОбластьВидимости: ВПроекте`/`Глобально` are reported: a
  non-public foreign object is inaccessible regardless of imports – that is a visibility
  error, not a missing import, and the platform semantics of it are not this rule's;
- a name that also belongs to an element of the file's own subsystem resolves locally
  and is skipped;
- a name that is also a stdlib symbol is skipped: without an import the foreign project
  namespace is not in scope and the name resolves to the standard namespace (the guard
  is active when the type catalog is generated);
- a name that is also a module-declared local type (structure, enumeration, exception)
  anywhere in the project is skipped – the yaml may legitimately reference a type of a
  module of its own subsystem (without the language data this guard degrades to a skip
  of nothing);
- qualified names (`Подсистема::Тип`) rely on the subsystem's `Использование`, not on
  the element's import – they do not parse as short chains and are skipped;
- a file outside any subsystem (no `Подсистема.yaml` up the path) is skipped, as is the
  whole check when the project has no subsystem files at all.

One diagnostic is reported per missing subsystem per file (the fix is a single import
line), anchored at the first offending type value. When several foreign public
subsystems declare the same name and none of them is imported, the candidates are listed
together ('Б/В') – importing any of them resolves the name.

The rule is project-wide: it needs the layout of the whole project (like
yaml/unknown-type, it does not run in single-file mode).
"""

from __future__ import annotations

from collections.abc import Iterable
from pathlib import Path

from xbsl import i18n
from xbsl.dataset import DatasetError
from xbsl.diagnostics import Diagnostic, Severity
from xbsl.engine import SourceFile, rule
from xbsl.rules import semantics
from xbsl.rules.yaml_schema import _HAVE_YAML, _parsed
from xbsl.rules.yaml_types import _parse_type_string, _type_values, _value_positions

MESSAGES = {
    "yaml/missing-import.title": {
        "ru": "Нет импорта подсистемы в yaml",
        "en": "Missing subsystem import in yaml",
    },
    "yaml/missing-import.missing": {
        "ru": "Тип '{name}' – из подсистемы '{sub}', а в секции Импорт её нет: "
              "инициализация компонента упадёт в рантайме "
              "(импорт в парном .xbsl yaml не покрывает).",
        "en": "Type '{name}' comes from subsystem '{sub}' which the Импорт section does "
              "not list: the component initialization fails at runtime "
              "(an import in the paired .xbsl does not cover the yaml).",
    },
}
i18n.register(MESSAGES)

_SUBSYSTEM_FILE = "Подсистема.yaml"
_PUBLIC_SCOPES = frozenset({"ВПроекте", "Глобально"})


def _subsystem_roots(sources: list[SourceFile]) -> dict[Path, str]:
    """Directories that are subsystem roots, mapped to the subsystem name."""
    roots: dict[Path, str] = {}
    for s in sources:
        if s.kind != "yaml" or s.path.name != _SUBSYSTEM_FILE:
            continue
        data, err = _parsed(s)
        name = data.get("Имя") if err is None and isinstance(data, dict) else None
        roots[s.path.parent] = name if isinstance(name, str) else s.path.parent.name
    return roots


def _subsystem_of(path: Path, roots: dict[Path, str]) -> str | None:
    """The subsystem of a source path – the nearest ancestor subsystem root."""
    for parent in path.parents:
        if parent in roots:
            return roots[parent]
    return None


def _yaml_import_mapper(source: SourceFile) -> dict | None:
    """The map phase: a subsystem yaml contributes its root directory, an object yaml its
    placement slice (name, visibility, imports) and its candidate type roots (stdlib
    settles here), a module its local types (the collision guard)."""
    if not _HAVE_YAML:
        return None
    if source.kind == "xbsl":
        try:
            local = semantics._file_local_types(source)
        except DatasetError:
            return None  # no language data – the collision guard has nothing to skip
        if not local:
            return None
        return {"k": "x", "local_types": sorted(local)}
    if source.kind != "yaml":
        return None
    if source.path.name == _SUBSYSTEM_FILE:
        data, err = _parsed(source)
        name = data.get("Имя") if err is None and isinstance(data, dict) else None
        return {
            "k": "sub",
            "dir": str(source.path.parent),
            "name": name if isinstance(name, str) else source.path.parent.name,
        }
    data, err = _parsed(source)
    if err is not None or not isinstance(data, dict) or not data.get("ВидЭлемента"):
        return None
    stdlib = semantics._stdlib_names()
    raw = data.get("Импорт")
    imports = [e for e in raw if isinstance(e, str)] if isinstance(raw, list) else []
    cands: list[tuple[str, str, int, int]] = []
    for value in dict.fromkeys(_type_values(data)):  # unique, in document order
        chains = _parse_type_string(value)
        if not chains:
            continue
        position: tuple[int, int] | None = None
        for chain in chains:
            root = chain[0]
            if root in stdlib:
                continue
            if position is None:
                position = (_value_positions(source, value) or [(1, 1)])[0]
            cands.append((root, ".".join(chain), position[0], position[1]))
    nm = data.get("Имя")
    return {
        "k": "el",
        "path": str(source.path),
        "name": nm if isinstance(nm, str) else None,
        "vis": data.get("ОбластьВидимости"),
        "imports": imports,
        "cands": cands,
    }


@rule(
    "yaml/missing-import", "yaml/missing-import.title", "D",
    scope="project", severity=Severity.WARNING, mapper=_yaml_import_mapper,
)
def missing_yaml_import(facts: dict[str, dict]) -> Iterable[Diagnostic]:
    # Subsystem roots and the placement model from the facts.
    roots: dict[Path, str] = {}
    for fact in facts.values():
        if fact["k"] == "sub":
            roots[Path(fact["dir"])] = fact["name"]
    if not roots:
        return
    local_types: set[str] = set()
    for fact in facts.values():
        if fact["k"] == "x":
            local_types.update(fact["local_types"])
    placement: dict[str, dict[str, object]] = {}
    elements: list[tuple[str, dict, str]] = []
    for rel, fact in facts.items():
        if fact["k"] != "el":
            continue
        sub = _subsystem_of(Path(fact["path"]), roots)
        if sub is None:
            continue
        elements.append((rel, fact, sub))
        if fact["name"]:
            placement.setdefault(fact["name"], {})[sub] = fact["vis"]
    for rel, fact, my_sub in elements:
        imports = set(fact["imports"])
        reported: set[tuple[str, ...]] = set()
        for root, chain_name, line, col in fact["cands"]:
            if root in local_types:
                continue
            subs = placement.get(root)
            if not subs or my_sub in subs:
                continue
            candidates = tuple(sorted(
                sub for sub, vis in subs.items() if vis in _PUBLIC_SCOPES
            ))
            if not candidates or imports.intersection(candidates):
                continue
            if candidates in reported:
                continue
            reported.add(candidates)
            yield Diagnostic(
                rel, line, col, "yaml/missing-import", Severity.WARNING,
                i18n.t("yaml/missing-import.missing", name=chain_name, sub="/".join(candidates)),
            )
