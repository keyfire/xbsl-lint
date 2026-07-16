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


@rule(
    "yaml/missing-import", "yaml/missing-import.title", "D",
    scope="project", severity=Severity.WARNING,
)
def missing_yaml_import(sources: list[SourceFile]) -> Iterable[Diagnostic]:
    if not _HAVE_YAML:
        return []
    roots = _subsystem_roots(sources)
    if not roots:
        return []

    # The element name -> {subsystem: ОбластьВидимости} placement, and the elements to check.
    placement: dict[str, dict[str, object]] = {}
    elements: list[tuple[SourceFile, dict, str]] = []
    for s in sources:
        if s.kind != "yaml":
            continue
        data, err = _parsed(s)
        if err is not None or not isinstance(data, dict) or not data.get("ВидЭлемента"):
            continue
        sub = _subsystem_of(s.path, roots)
        if sub is None:
            continue
        elements.append((s, data, sub))
        nm = data.get("Имя")
        if isinstance(nm, str):
            placement.setdefault(nm, {})[sub] = data.get("ОбластьВидимости")

    stdlib = semantics._stdlib_names()
    try:
        local_types = semantics._local_type_names(sources)
    except DatasetError:
        local_types = set()  # no language data – the collision guard has nothing to skip

    diags: list[Diagnostic] = []
    for s, data, my_sub in elements:
        raw = data.get("Импорт")
        imports = {e for e in raw if isinstance(e, str)} if isinstance(raw, list) else set()
        reported: set[tuple[str, ...]] = set()
        for value in dict.fromkeys(_type_values(data)):  # unique, in document order
            chains = _parse_type_string(value)
            if not chains:
                continue
            for chain in chains:
                root = chain[0]
                subs = placement.get(root)
                if not subs or my_sub in subs or root in stdlib or root in local_types:
                    continue
                candidates = tuple(sorted(
                    sub for sub, vis in subs.items() if vis in _PUBLIC_SCOPES
                ))
                if not candidates or imports.intersection(candidates):
                    continue
                if candidates in reported:
                    continue
                reported.add(candidates)
                line, col = (_value_positions(s, value) or [(1, 1)])[0]
                diags.append(Diagnostic(
                    s.rel, line, col, "yaml/missing-import", Severity.WARNING,
                    i18n.t(
                        "yaml/missing-import.missing",
                        name=".".join(chain),
                        sub="/".join(candidates),
                    ),
                ))
    return diags
