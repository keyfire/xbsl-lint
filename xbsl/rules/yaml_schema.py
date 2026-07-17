"""Tier A: checks on the YAML descriptions of elements.

- yaml/valid            – the YAML parses correctly;
- yaml/id-uuid          – every Ид (including the nested attributes) is a valid UUID;
- yaml/id-unique        – Ид values are unique within the project (a cross-file rule);
- yaml/id-required      – an object (has ВидЭлемента) carries a top-level Ид;
- yaml/name-matches-file – the object Имя matches the file name.

Structural files (Проект/Подсистема/Ресурсы) are recognised by the absence of ВидЭлемента and
are exempt from the Имя/required-Ид rules; the Ид checks (format/uniqueness) apply to every Ид
in every file.
"""

from __future__ import annotations

import re
from collections import defaultdict
from collections.abc import Iterable

from xbsl import i18n
from xbsl.diagnostics import Diagnostic, Severity
from xbsl.engine import SourceFile, rule
from xbsl.lexer import linemap

try:
    import yaml

    _HAVE_YAML = True
except ImportError:  # pragma: no cover
    _HAVE_YAML = False

MESSAGES = {
    "yaml/valid.title": {
        "ru": "YAML не парсится",
        "en": "YAML does not parse",
    },
    "yaml/valid.default-problem": {
        "ru": "ошибка синтаксиса YAML",
        "en": "YAML syntax error",
    },
    "yaml/valid.error": {
        "ru": "YAML: {problem}.",
        "en": "YAML: {problem}.",
    },
    "yaml/id-uuid.title": {
        "ru": "Ид не является UUID",
        "en": "Ид is not a UUID",
    },
    "yaml/id-uuid.not-uuid": {
        "ru": "Ид '{value}' не является UUID (формат 8-4-4-4-12).",
        "en": "Ид '{value}' is not a UUID (the 8-4-4-4-12 format).",
    },
    "yaml/id-required.title": {
        "ru": "У объекта нет Ид",
        "en": "The object has no Ид",
    },
    "yaml/id-required.missing": {
        "ru": "У объекта не задан Ид верхнего уровня.",
        "en": "The object has no top-level Ид.",
    },
    "yaml/name-matches-file.title": {
        "ru": "Имя не совпадает с именем файла",
        "en": "Имя does not match the file name",
    },
    "yaml/name-matches-file.mismatch": {
        "ru": "Имя '{name}' не совпадает с именем файла '{stem}'.",
        "en": "Имя '{name}' does not match the file name '{stem}'.",
    },
    "yaml/id-unique.title": {
        "ru": "Дубли Ид в проекте",
        "en": "Duplicate Ид in the project",
    },
    "yaml/id-unique.duplicate": {
        "ru": "Дублирующийся Ид '{value}' (также: {others}).",
        "en": "Duplicate Ид '{value}' (also: {others}).",
    },
}
i18n.register(MESSAGES)

_UUID_RE = re.compile(r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$")
_ID_LINE_RE = re.compile(r"(?m)^[ \t]*Ид:[ \t]*(\S+)")
# A line with the `Имя:` key: the indent (a list-item dash counts as indent), the value with or
# without quotes, an optional trailing comment (per YAML it is not part of the value); `\r?` lets
# CRLF files match (`$` anchors before `\n`). Groups: 1 – indent, 2 – quote, 3 – value.
# Shared by the naming rules and the indexer.
_NAME_LINE_RE = re.compile(
    r"(?m)^([ \t]*(?:-[ \t]+)?)Имя:[ \t]*(['\"]?)([^\r\n#]*?)\2[ \t]*(?:#.*)?\r?$"
)


# libyaml (CSafeLoader) parses 5-10x faster than the pure-Python loader and dominates the
# whole-project run time; the pure loader stays as the fallback for builds without it.
_LOADER = getattr(yaml, "CSafeLoader", yaml.SafeLoader)


def _parsed(source: SourceFile):
    """The parsed YAML (or None) and the parse error (or None), cached.

    The platform parser is more lenient than PyYAML: real shipped sources carry `\\'`
    inside double-quoted scalars (an HTML/JS onclick in БизКуб), which the platform
    accepts as a plain apostrophe while PyYAML rejects the escape. The retry below
    only runs when the strict parse has already failed, so no valid document can be
    misread by it.
    """
    if "yaml" not in source.cache:
        data = None
        err = None
        try:
            data = yaml.load(source.text, Loader=_LOADER)
        except yaml.YAMLError as exc:  # noqa: BLE001
            err = exc
            if "unknown escape character" in str(exc):
                try:
                    data = yaml.load(source.text.replace("\\'", "'"), Loader=_LOADER)
                    err = None
                except yaml.YAMLError:
                    data = None
        source.cache["yaml"] = data
        source.cache["yaml_error"] = err
    return source.cache["yaml"], source.cache["yaml_error"]


def _id_lines(source: SourceFile) -> list[tuple[str, int, int]]:
    """List of (Ид value, line, column) for every 'Ид:' line in the file."""
    key = "id_lines"
    if key not in source.cache:
        lm = linemap(source)
        out: list[tuple[str, int, int]] = []
        for m in _ID_LINE_RE.finditer(source.text):
            line, col = lm.linecol(m.start(1))
            out.append((m.group(1).strip(), line, col))
        source.cache[key] = out
    return source.cache[key]


def _is_object(data) -> bool:
    """Whether the file describes a metadata object (has ВидЭлемента)."""
    return isinstance(data, dict) and data.get("ВидЭлемента") is not None


@rule("yaml/valid", "yaml/valid.title", "A", severity=Severity.ERROR)
def yaml_valid(source: SourceFile) -> Iterable[Diagnostic]:
    if not _HAVE_YAML or source.kind != "yaml":
        return
    _data, err = _parsed(source)
    if err is not None:
        mark = getattr(err, "problem_mark", None)
        line = mark.line + 1 if mark else 1
        col = mark.column + 1 if mark else 1
        problem = getattr(err, "problem", None) or i18n.t("yaml/valid.default-problem")
        yield Diagnostic(
            source.rel, line, col, "yaml/valid", Severity.ERROR,
            i18n.t("yaml/valid.error", problem=problem),
        )


@rule("yaml/id-uuid", "yaml/id-uuid.title", "A", severity=Severity.ERROR)
def yaml_id_uuid(source: SourceFile) -> Iterable[Diagnostic]:
    if source.kind != "yaml":
        return
    for value, line, col in _id_lines(source):
        if not _UUID_RE.match(value):
            yield Diagnostic(
                source.rel, line, col, "yaml/id-uuid", Severity.ERROR,
                i18n.t("yaml/id-uuid.not-uuid", value=value),
            )


@rule("yaml/id-required", "yaml/id-required.title", "A", severity=Severity.WARNING)
def yaml_id_required(source: SourceFile) -> Iterable[Diagnostic]:
    if not _HAVE_YAML or source.kind != "yaml":
        return
    data, err = _parsed(source)
    if err is not None or not _is_object(data):
        return
    if "Ид" not in data:
        yield Diagnostic(
            source.rel, 1, 1, "yaml/id-required", Severity.WARNING,
            i18n.t("yaml/id-required.missing"),
        )


@rule("yaml/name-matches-file", "yaml/name-matches-file.title", "A", severity=Severity.WARNING)
def yaml_name_matches_file(source: SourceFile) -> Iterable[Diagnostic]:
    if not _HAVE_YAML or source.kind != "yaml":
        return
    data, err = _parsed(source)
    if err is not None or not _is_object(data):
        return
    name = data.get("Имя")
    stem = source.path.stem
    if isinstance(name, str) and name != stem:
        m = _NAME_LINE_RE.search(source.text)
        line, col = (1, 1)
        if m:
            line, col = linemap(source).linecol(m.start(3))
        yield Diagnostic(
            source.rel, line, col, "yaml/name-matches-file", Severity.WARNING,
            i18n.t("yaml/name-matches-file.mismatch", name=name, stem=stem),
        )


def _id_unique_mapper(source: SourceFile) -> list[tuple[str, int, int]] | None:
    """The map phase: every Ид value of the file with its position."""
    if source.kind != "yaml":
        return None
    ids = _id_lines(source)
    return ids or None


@rule(
    "yaml/id-unique", "yaml/id-unique.title", "A",
    scope="project", severity=Severity.ERROR, mapper=_id_unique_mapper,
)
def yaml_id_unique(facts: dict[str, list[tuple[str, int, int]]]) -> Iterable[Diagnostic]:
    occ: dict[str, list[tuple[str, int, int]]] = defaultdict(list)
    for rel, ids in facts.items():
        for value, line, col in ids:
            occ[value].append((rel, line, col))
    for value, places in occ.items():
        if len(places) < 2:
            continue
        for i, (rel, line, col) in enumerate(places):
            others = [f"{orel}:{ol}" for j, (orel, ol, _oc) in enumerate(places) if j != i]
            yield Diagnostic(
                rel, line, col, "yaml/id-unique", Severity.ERROR,
                i18n.t("yaml/id-unique.duplicate", value=value, others=", ".join(others[:3])),
            )
