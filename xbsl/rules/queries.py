"""Checks of the query DSL (`Запрос{ ... }` blocks).

query/unknown-table - a table referenced by ИЗ/СОЕДИНЕНИЕ (FROM/JOIN) must be an object of the
project, and `<Объект>.<Секция>` must name a tabular section of that object. Otherwise such
errors only show up in the database at run time.

query/in-subquery-composite - the platform standard "Использование выражения В с подзапросом для
выражений составного типа": on most DBMSs that variant is implemented inefficiently, the
condition is written via СУЩЕСТВУЕТ (EXISTS). A field type counts as composite when it has two
or more alternatives in yaml (`Строка|Число|?`), where `?` is only Неопределено being allowed,
not a separate type.

The parsing is deliberately conservative (the zero-false-positives invariant):

- a block with constructs outside the supported subset (temporary tables, unions, a subquery or
  anything but a plain name in the table position) is skipped as a whole;
- a dotted table whose root is not an object of the project is considered external (from a
  library) and skipped - only a KNOWN root with an unknown section is reported;
- a section after the dot found in the virtual table dictionary (СрезПоследних, Остатки, ...)
  is not questioned, and chains deeper than two segments are left alone;
- in `В` only a field whose type is known for sure is questioned: `Алиас.Поле` or
  `Таблица.Поле` where the alias is unambiguous within the block (one redefined in a subquery
  is skipped) and the field is found in the table's yaml.
"""

from __future__ import annotations

from typing import Iterable, Iterator, Optional

from xbsl import i18n
from xbsl.diagnostics import Diagnostic, Severity
from xbsl.engine import SourceFile, rule
from xbsl.lexer import Token, tokens
from xbsl.rules._syntax import (
    QUERY_TABLE_INTRO,
    WORD_KINDS,
    query_alias_pairs,
    query_block_tokens,
    query_ranges,
)
from xbsl.rules.yaml_schema import _HAVE_YAML, _parsed

MESSAGES = {
    "query/unknown-table.title": {
        "ru": "Неизвестная таблица в запросе",
        "en": "Unknown table in a query",
    },
    "query/unknown-table.unknown": {
        "ru": "Неизвестная таблица запроса '{name}' – такого объекта нет в проекте.",
        "en": "Unknown query table '{name}' – no such object in the project.",
    },
    "query/unknown-table.tabular": {
        "ru": "Неизвестная таблица запроса '{name}' – у объекта '{root}' ({kind}) нет "
              "табличной части '{seg}'.",
        "en": "Unknown query table '{name}' – object '{root}' ({kind}) has no tabular "
              "section named '{seg}'.",
    },
    "query/in-subquery-composite.title": {
        "ru": "'В' с подзапросом по составному типу",
        "en": "'IN' with a subquery over a composite type",
    },
    "query/in-subquery-composite.in": {
        "ru": "'{expr}' составного типа ({types}): 'В' с подзапросом на большинстве СУБД "
              "реализовано неэффективно – использовать 'СУЩЕСТВУЕТ (ВЫБРАТЬ 1 ИЗ ... ГДЕ "
              "... = {expr})'.",
        "en": "'{expr}' is of a composite type ({types}): 'IN' with a subquery is implemented "
              "inefficiently on most DBMSs – use 'EXISTS (SELECT 1 FROM ... WHERE ... = {expr})'.",
    },
    "query/in-subquery-composite.not-in": {
        "ru": "'{expr}' составного типа ({types}): 'НЕ В' с подзапросом на большинстве СУБД "
              "реализовано неэффективно – использовать 'НЕ СУЩЕСТВУЕТ (ВЫБРАТЬ 1 ИЗ ... ГДЕ "
              "... = {expr})'.",
        "en": "'{expr}' is of a composite type ({types}): 'NOT IN' with a subquery is implemented "
              "inefficiently on most DBMSs – use 'NOT EXISTS (SELECT 1 FROM ... WHERE "
              "... = {expr})'.",
    },
}
i18n.register(MESSAGES)

# Words that introduce a table (the next word token starts a table expression) and the word
# token kinds - shared with the alias parsing in _syntax.
_TABLE_INTRO = QUERY_TABLE_INTRO
_WORD_KINDS = WORD_KINDS
# Constructs outside the supported subset - a block with them is skipped as a whole.
_UNSUPPORTED = frozenset({"ПОМЕСТИТЬ", "INTO", "ОБЪЕДИНИТЬ", "UNION", "ВРЕМЕННАЯ", "TEMPORARY"})
# Virtual tables after the dot - not questioned.
_VIRTUAL = frozenset({
    "СРЕЗПОСЛЕДНИХ", "СРЕЗПЕРВЫХ", "ОСТАТКИ", "ОБОРОТЫ", "ОСТАТКИИОБОРОТЫ",
    "SLICELAST", "SLICEFIRST", "BALANCE", "TURNOVERS", "BALANCEANDTURNOVERS",
})
# Query language words - in both forms, as the lexer sees them (the token value, not the canon).
_IN = frozenset({"В", "IN"})
_NOT = frozenset({"НЕ", "NOT"})
_SELECT = frozenset({"ВЫБРАТЬ", "SELECT"})
# Yaml sections that provide the fields of a query table.
_FIELD_SECTIONS = ("Реквизиты", "Измерения", "Ресурсы")


def _query_tables(source: SourceFile) -> Iterable[tuple]:
    """Table expressions of all query blocks of a file: (segment tokens,) one per table.

    A block where ИЗ/СОЕДИНЕНИЕ is followed by something other than a name (a subquery, an
    interpolation) or where an unsupported word occurs yields no expressions at all - silence
    instead of guessing.
    """
    toks = tokens(source)
    for start, end in query_ranges(source):
        block = [t for t in toks if start <= t.start < end and t.kind not in ("COMMENT", "BOM")]
        tables: list[list] = []
        supported = True
        i, n = 0, len(block)
        while i < n:
            t = block[i]
            if t.kind in _WORD_KINDS and t.value.upper() in _UNSUPPORTED:
                supported = False
                break
            if t.kind in _WORD_KINDS and t.value.upper() in _TABLE_INTRO:
                j = i + 1
                if j >= n or block[j].kind not in _WORD_KINDS:
                    supported = False  # a subquery/interpolation in the table position
                    break
                segs = [block[j]]
                j += 1
                while (
                    j + 1 < n
                    and block[j].kind == "OP" and block[j].value == "."
                    and block[j + 1].kind in _WORD_KINDS
                ):
                    segs.append(block[j + 1])
                    j += 2
                tables.append(segs)
                i = j
                continue
            i += 1
        if supported:
            yield from tables


def _tabular_catalog(sources: list[SourceFile]) -> dict[str, dict]:
    """Project objects: name -> {kind, tabular, fields}.

    Tabular sections come only from yaml (local module types are not database tables); the
    fields are attributes, dimensions and resources together with their type spec
    (`Строка|Число|?`).
    """
    info: dict[str, dict] = {}
    if not _HAVE_YAML:
        return info
    for s in sources:
        if s.kind != "yaml":
            continue
        data, err = _parsed(s)
        if err is not None or not isinstance(data, dict) or not data.get("ВидЭлемента"):
            continue
        nm = data.get("Имя")
        if not isinstance(nm, str):
            continue
        tabular: set[str] = set()
        parts = data.get("ТабличныеЧасти")
        if isinstance(parts, list):
            for p in parts:
                if isinstance(p, dict) and isinstance(p.get("Имя"), str):
                    tabular.add(p["Имя"])
        fields: dict[str, str] = {}
        for section in _FIELD_SECTIONS:
            items = data.get(section)
            if not isinstance(items, list):
                continue
            for it in items:
                if isinstance(it, dict) and isinstance(it.get("Имя"), str) and isinstance(it.get("Тип"), str):
                    fields[it["Имя"]] = it["Тип"]
        info[nm] = {"kind": data["ВидЭлемента"], "tabular": tabular, "fields": fields}
    return info


def _alternatives(spec: str) -> list[str]:
    """Top-level type alternatives: `Строка|Число|?` -> ["Строка", "Число"].

    `?` is not a type but Неопределено being allowed (mandatory for a composite type, because
    such a type has no default value), so it does not count. Inside generics `|` does not
    split: `Массив<Строка|Число>` is one type, not a composite one.
    """
    parts: list[str] = []
    depth = 0
    current = ""
    for ch in spec:
        if ch == "<":
            depth += 1
        elif ch == ">":
            depth -= 1
        elif ch == "|" and depth == 0:
            parts.append(current)
            current = ""
            continue
        current += ch
    parts.append(current)
    return [p.strip() for p in parts if p.strip() and p.strip() != "?"]


def _block_aliases(block: list[Token]) -> dict[str, str]:
    """Alias -> table for a block; an alias redefined in a subquery is dropped.

    The same alias in a block and in its subquery may point to different tables - then the
    alias does not tell us the table, and we stay silent rather than pick one at random.
    """
    out: dict[str, str] = {}
    for alias, table in query_alias_pairs(block):
        if alias in out and out[alias] != table:
            out[alias] = ""  # conflict: the alias cannot be resolved
        else:
            out.setdefault(alias, table)
    return {a: t for a, t in out.items() if t}


def _in_subqueries(source: SourceFile) -> Iterator[tuple[Token, Token, bool, dict[str, str]]]:
    """`<Таблица|Алиас>.<Поле> [НЕ] В (ВЫБРАТЬ ...)` constructs: (prefix, field, negation, aliases).

    Only qualified fields are picked: for a bare name in a condition there is no reliable way
    to establish the table, and a value list in parentheses (`В (1, 2, &Коды)`) is outside the
    standard - it only speaks of a subquery.
    """
    for span in query_ranges(source):
        block = query_block_tokens(source, span)
        aliases = _block_aliases(block)
        n = len(block)
        for i, t in enumerate(block):
            if t.kind not in _WORD_KINDS or t.value.upper() not in _IN:
                continue
            if i + 2 >= n or not (block[i + 1].kind == "OP" and block[i + 1].value == "("):
                continue
            after = block[i + 2]
            if after.kind not in _WORD_KINDS or after.value.upper() not in _SELECT:
                continue  # a value list, not a subquery
            j = i - 1
            negated = j >= 0 and block[j].kind in _WORD_KINDS and block[j].value.upper() in _NOT
            if negated:
                j -= 1
            if j < 2:
                continue
            field, dot, prefix = block[j], block[j - 1], block[j - 2]
            if field.kind not in _WORD_KINDS or prefix.kind not in _WORD_KINDS:
                continue
            if not (dot.kind == "OP" and dot.value == "."):
                continue
            if j - 3 >= 0 and block[j - 3].kind == "OP" and block[j - 3].value == ".":
                continue  # a chain deeper than two segments - the type of the last field is unknown
            yield prefix, field, negated, aliases


@rule(
    "query/unknown-table", "query/unknown-table.title", "D",
    scope="project", severity=Severity.WARNING,
)
def unknown_query_table(sources: list[SourceFile]) -> Iterable[Diagnostic]:
    catalog = _tabular_catalog(sources)
    if not catalog:
        return []  # yaml not parsed (no PyYAML) or a project with no objects - stay silent

    diags: list[Diagnostic] = []
    for s in sources:
        if s.kind != "xbsl":
            continue
        for segs in _query_tables(s):
            root = segs[0]
            name = ".".join(t.value for t in segs)
            rec = catalog.get(root.value)
            if len(segs) == 1:
                if rec is None:
                    diags.append(Diagnostic(
                        s.rel, root.line, root.col, "query/unknown-table",
                        Severity.WARNING,
                        i18n.t("query/unknown-table.unknown", name=name),
                    ))
                continue
            if len(segs) != 2 or rec is None:
                continue  # deep chains and external roots - out of scope
            seg = segs[1]
            if seg.value in rec["tabular"] or seg.value.upper() in _VIRTUAL:
                continue
            diags.append(Diagnostic(
                s.rel, seg.line, seg.col, "query/unknown-table",
                Severity.WARNING,
                i18n.t(
                    "query/unknown-table.tabular",
                    name=name, root=root.value, kind=rec["kind"], seg=seg.value,
                ),
            ))
    return diags


@rule(
    "query/in-subquery-composite", "query/in-subquery-composite.title", "D",
    scope="project", severity=Severity.WARNING,
)
def in_subquery_composite(sources: list[SourceFile]) -> Iterable[Diagnostic]:
    """A composite-type field in `В (ВЫБРАТЬ ...)` - the condition is rewritten via СУЩЕСТВУЕТ."""
    catalog = _tabular_catalog(sources)
    if not catalog:
        return []  # yaml not parsed (no PyYAML) or a project with no objects - stay silent

    diags: list[Diagnostic] = []
    for s in sources:
        if s.kind != "xbsl":
            continue
        for prefix, field, negated, aliases in _in_subqueries(s):
            table = aliases.get(prefix.value)
            if table is None and prefix.value in catalog:
                table = prefix.value  # the table is referenced by its own name, without an alias
            rec = catalog.get(table) if table else None
            if rec is None:
                continue
            alternatives = _alternatives(rec["fields"].get(field.value, ""))
            if len(alternatives) < 2:
                continue  # a plain or nullable type - the standard says nothing about it
            key = ".not-in" if negated else ".in"
            diags.append(Diagnostic(
                s.rel, prefix.line, prefix.col, "query/in-subquery-composite",
                Severity.WARNING,
                i18n.t(
                    "query/in-subquery-composite" + key,
                    expr=f"{prefix.value}.{field.value}",
                    types="|".join(alternatives),
                ),
            ))
    return diags
