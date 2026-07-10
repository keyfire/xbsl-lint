"""Tier C: structure fields of a reference type must not rely on a default value.

The code/ref-field-needs-req rule. A structure field whose type is a project-object
reference (`Программа.Ссылка`, `Справочник.Товары.Ссылка` – the last segment of the dotted
chain is `Ссылка`) has no default value on the platform, so the server-side apply fails with
"cannot be initialized with a default value". The correct forms are:

- `обз пер Ссылка: Программа.Ссылка` – the field is required in the constructor;
- `пер Ссылка: Программа.Ссылка?` – a nullable type has the default `Неопределено`;
- `пер Ссылка: Программа.Ссылка = <выражение>` – an explicit initializer.

Detection is token-based: inside a `структура ... ;` block (nesting-aware – fields are taken
only at the top level of the structure body, not inside its methods or constructors) every
`пер`/`знч` declaration is checked; a declaration is flagged when its type annotation is a
plain dotted chain ending in `Ссылка`, with no `?`, no `= ...` initializer and no `обз`
before the declaration keyword.

Deliberate narrowings (skip rather than guess – no false positives):

- union types (`А.Ссылка|Б.Ссылка`, `А.Ссылка|?`) are skipped: the platform's defaulting
  rules for unions are not encoded here, and a `|?` union is nullable anyway;
- generics (`Массив<Программа.Ссылка>`) are skipped: the field itself is a collection, not
  a direct reference, and collections have default values;
- a bare `Ссылка` (a one-segment chain) is skipped: it is a local type name, not a
  project-object reference;
- an alternative that is not a plain IDENT(.IDENT)* chain is skipped.
"""

from __future__ import annotations

from collections.abc import Iterable

from xbsllint import i18n
from xbsllint.diagnostics import Diagnostic, Severity
from xbsllint.engine import SourceFile, rule
from xbsllint.lexer import Token
from xbsllint.rules._syntax import code_tokens, type_expr
from xbsllint.rules.code_structure import _OPENERS

MESSAGES = {
    "code/ref-field-needs-req.title": {
        "ru": "Поле-ссылка структуры без 'обз'",
        "en": "Structure reference field without 'обз'",
    },
    "code/ref-field-needs-req.missing": {
        "ru": "Поле структуры '{name}' имеет ссылочный тип '{type}' без 'обз', '?' и "
              "инициализатора – применение сборки падает с 'cannot be initialized with "
              "a default value'. Правильно: 'обз {kw} {name}: {type}'.",
        "en": "Structure field '{name}' has the reference type '{type}' without 'обз', '?' "
              "or an initializer – applying the build fails with 'cannot be initialized "
              "with a default value'. Correct: 'обз {kw} {name}: {type}'.",
    },
}
i18n.register(MESSAGES)

_FIELD_KEYWORDS = ("VAR", "VAL")


def _structure_field_decls(toks: list[Token]) -> list[tuple[int, bool]]:
    """Indices of `пер`/`знч` keywords at the top level of structure bodies.

    Returns (index, has_req) pairs; has_req – the declaration is preceded by `обз`.
    Block tracking mirrors code_structure: a lowercase opener keyword pushes a block,
    `;` pops one; `иначе если` on one line continues the same `если` block. Query-block
    contents and comments are already stripped by code_tokens, so a `;` inside a query
    cannot break the balance.
    """
    out: list[tuple[int, bool]] = []
    stack: list[str] = []
    prev: Token | None = None
    for i, t in enumerate(toks):
        if t.kind == "KEYWORD" and t.canonical in _OPENERS and t.value[:1].islower():
            is_else_if = (
                t.canonical == "IF"
                and prev is not None
                and prev.kind == "KEYWORD"
                and prev.canonical == "ELSE"
                and prev.line == t.line
            )
            if not is_else_if:
                stack.append(t.canonical)
        elif t.kind == "OP" and t.value == ";":
            if stack:
                stack.pop()
        elif (
            t.kind == "KEYWORD"
            and t.canonical in _FIELD_KEYWORDS
            and t.value[:1].islower()
            and stack
            and stack[-1] == "STRUCTURE"
        ):
            has_req = prev is not None and prev.kind == "KEYWORD" and prev.canonical == "REQ"
            out.append((i, has_req))
        prev = t
    return out


def _decl_names(toks: list[Token], start: int) -> tuple[list[Token], int]:
    """The name tokens of a declaration (`Имя` or `Имя1, Имя2`) and the index past them."""
    names: list[Token] = []
    j, n = start, len(toks)
    while j < n and toks[j].kind == "IDENT":
        names.append(toks[j])
        k = j + 1
        if k < n and toks[k].kind == "OP" and toks[k].value == ",":
            j = k + 1
            continue
        return names, k
    return names, j


def _plain_ref_chain(alt: list[Token]) -> list[Token] | None:
    """The IDENT tokens of a plain dotted chain ending in `Ссылка`, else None.

    The alternative must strictly alternate IDENT and '.', have at least two segments
    and no other tokens (`?`, `<...>`, `Неопределено` – not a plain reference chain).
    """
    idents: list[Token] = []
    expect_ident = True
    for t in alt:
        if expect_ident:
            if t.kind != "IDENT":
                return None
            idents.append(t)
        elif not (t.kind == "OP" and t.value == "."):
            return None
        expect_ident = not expect_ident
    if expect_ident or len(idents) < 2 or idents[-1].value != "Ссылка":
        return None
    return idents


@rule(
    "code/ref-field-needs-req", "code/ref-field-needs-req.title", "C",
    severity=Severity.ERROR,
)
def ref_field_needs_req(source: SourceFile) -> Iterable[Diagnostic]:
    if source.kind != "xbsl":
        return []
    toks = code_tokens(source)
    n = len(toks)
    diags: list[Diagnostic] = []

    for i, has_req in _structure_field_decls(toks):
        if has_req:
            continue
        names, j = _decl_names(toks, i + 1)
        if not names or j >= n or not (toks[j].kind == "OP" and toks[j].value == ":"):
            continue
        te = type_expr(toks, j + 1)
        if te is None or len(te.alternatives) != 1:
            continue  # no type, or a union – skip (see the module docstring)
        if te.end < n and toks[te.end].kind == "OP" and toks[te.end].value == "=":
            continue  # an explicit initializer
        chain = _plain_ref_chain(te.alternatives[0])
        if chain is None:
            continue
        type_text = ".".join(t.value for t in chain)
        for name in names:
            diags.append(Diagnostic(
                source.rel, name.line, name.col, "code/ref-field-needs-req",
                Severity.ERROR,
                i18n.t(
                    "code/ref-field-needs-req.missing",
                    name=name.value, type=type_text, kw=toks[i].value,
                ),
            ))
    return diags
