"""Shared syntactic helpers for code rules (tiers B/C).

Collected here is what several rule modules need and what cannot be expressed with a single
pass over the tokens:

- `query_ranges` – offsets of `Запрос{ ... }` blocks. Inside them lives the query language,
  which the XBSL code-writing conventions do not cover (CODE_STYLE, "Область действия"),
  so code rules skip these ranges;
- `code_tokens` – the module tokens without comments and without query-block contents;
- `lines` / `line_span` – access to source lines by number;
- `type_expr` – the tokens of a type expression and the parsing of its alternatives (`Строка|Число|?`);
- `declaration_types` / `method_params` – type positions of declarations and method signatures.

Parsing is token-based, without a full AST: rules must yield zero false positives on the
corpus, so an ambiguous construct is better skipped than guessed.
"""

from __future__ import annotations

import bisect
from dataclasses import dataclass

from xbsllint.engine import SourceFile
from xbsllint.lexer import Token, tokens

# Keywords that introduce a declaration with a type annotation: `знч/пер/конст/поймать/обз Имя: Тип`.
DECL_KEYWORDS = ("VAL", "VAR", "CONST", "CATCH", "REQ")
# Keywords that carry a signature (parameter list and return type).
SIGNATURE_KEYWORDS = ("METHOD", "CONSTRUCTOR")

_OPEN_CH = "([{"
_CLOSE_CH = ")]}"


# --- Запрос{ ... } blocks -------------------------------------------------------------

def query_ranges(source: SourceFile) -> list[tuple[int, int]]:
    """Offsets [start, end) of `Запрос{ ... }` blocks, including the curly braces."""
    cached = source.cache.get("query_ranges")
    if cached is not None:
        return cached

    toks = tokens(source)
    ranges: list[tuple[int, int]] = []
    i, n = 0, len(toks)
    while i < n:
        t = toks[i]
        if t.kind == "KEYWORD" and t.canonical == "QUERY":
            j = _skip_comments(toks, i + 1)
            if j < n and toks[j].kind == "OP" and toks[j].value == "{":
                k, depth = j, 0
                while k < n:
                    tk = toks[k]
                    if tk.kind == "OP" and tk.value == "{":
                        depth += 1
                    elif tk.kind == "OP" and tk.value == "}":
                        depth -= 1
                        if depth == 0:
                            break
                    k += 1
                end = toks[k].end if k < n else len(source.text)
                ranges.append((toks[j].start, end))
                i = k + 1
                continue
        i += 1

    source.cache["query_ranges"] = ranges
    return ranges


def in_query(source: SourceFile, offset: int) -> bool:
    """The offset falls inside a query block."""
    ranges = query_ranges(source)
    idx = bisect.bisect_right([r[0] for r in ranges], offset) - 1
    return idx >= 0 and offset < ranges[idx][1]


def code_tokens(source: SourceFile) -> list[Token]:
    """Code tokens: without comments, without EOF and without query-block contents."""
    cached = source.cache.get("code_tokens")
    if cached is not None:
        return cached
    out = [
        t for t in tokens(source)
        if t.kind not in ("COMMENT", "EOF") and not in_query(source, t.start)
    ]
    source.cache["code_tokens"] = out
    return out


def _skip_comments(toks: list[Token], k: int) -> int:
    n = len(toks)
    while k < n and toks[k].kind == "COMMENT":
        k += 1
    return k


# --- Source lines ---------------------------------------------------------------------

def lines(source: SourceFile) -> list[str]:
    """Source lines without line breaks (line 1 – index 0)."""
    cached = source.cache.get("lines")
    if cached is None:
        cached = source.text.splitlines()
        source.cache["lines"] = cached
    return cached


def line_starts(source: SourceFile) -> list[int]:
    """Offset of the start of each line (line 1 – index 0)."""
    cached = source.cache.get("line_starts")
    if cached is not None:
        return cached
    starts, pos = [], 0
    text = source.text
    n = len(text)
    while pos <= n:
        starts.append(pos)
        nl = text.find("\n", pos)
        if nl == -1:
            break
        pos = nl + 1
    source.cache["line_starts"] = starts
    return starts


def line_span(source: SourceFile, line: int) -> tuple[int, int]:
    """Offsets [start, end) of the line numbered `line` (1-based), without the line break."""
    starts = line_starts(source)
    start = starts[line - 1]
    return start, start + len(lines(source)[line - 1])


def spans_of(source: SourceFile, kinds: tuple[str, ...]) -> list[tuple[int, int]]:
    """Offsets of tokens of the given kinds (e.g. STRING/COMMENT) – for text-based checks."""
    key = "spans_" + "_".join(kinds)
    cached = source.cache.get(key)
    if cached is None:
        cached = [(t.start, t.end) for t in tokens(source) if t.kind in kinds]
        source.cache[key] = cached
    return cached


def inside(spans: list[tuple[int, int]], offset: int) -> bool:
    """The offset lies within one of the ranges (bounds – left-inclusive)."""
    idx = bisect.bisect_right([s[0] for s in spans], offset) - 1
    return idx >= 0 and offset < spans[idx][1]


# --- Type expressions -----------------------------------------------------------------

@dataclass
class TypeExpr:
    """A type expression: its tokens and top-level alternatives (via `|`)."""

    toks: list[Token]
    alternatives: list[list[Token]]
    end: int  # index of the token past the end of the expression


def type_expr(toks: list[Token], start: int) -> TypeExpr | None:
    """Parse a type expression starting at position start (the first type token).

    Understands FQNs (`Справочник.Товары.Ссылка`), generics (`Массив<Строка>`), the nullable
    suffix `?` and unions `Строка|Число|?`. Returns None if there is no type at position start.
    """
    n = len(toks)
    i = _skip_comments(toks, start)
    if i >= n or (toks[i].kind != "IDENT" and not _is_undefined(toks[i])):
        return None

    collected: list[Token] = []
    alternatives: list[list[Token]] = [[]]
    depth = 0
    expect_operand = True  # expect a type name (start of the expression, after `|`, `<`, `,`, `.`)

    while i < n:
        t = toks[i]
        if t.kind == "COMMENT":
            i += 1
            continue
        if t.kind == "IDENT" or _is_undefined(t):
            if not expect_operand and depth == 0:
                break
            collected.append(t)
            alternatives[-1].append(t)
            expect_operand = False
            i += 1
            continue
        if t.kind == "OP":
            v = t.value
            if v == "." and not expect_operand:
                collected.append(t)
                alternatives[-1].append(t)
                expect_operand = True
                i += 1
                continue
            if v == "<":
                depth += 1
                collected.append(t)
                alternatives[-1].append(t)
                expect_operand = True
                i += 1
                continue
            if v == ">" and depth > 0:
                depth -= 1
                collected.append(t)
                alternatives[-1].append(t)
                expect_operand = False
                i += 1
                continue
            if v == "," and depth > 0:
                collected.append(t)
                alternatives[-1].append(t)
                expect_operand = True
                i += 1
                continue
            if v == "?" and not expect_operand:  # nullable type suffix
                collected.append(t)
                alternatives[-1].append(t)
                i += 1
                continue
            if v == "?" and expect_operand:  # standalone `|?` alternative
                collected.append(t)
                alternatives[-1].append(t)
                expect_operand = False
                i += 1
                continue
            if v == "|":
                collected.append(t)
                if depth == 0:
                    alternatives.append([])
                else:
                    alternatives[-1].append(t)
                expect_operand = True
                i += 1
                continue
        break

    if not collected or expect_operand and depth == 0 and not alternatives[-1]:
        # the expression broke off at a separator – nothing to parse
        return None if not collected else TypeExpr(collected, [a for a in alternatives if a], i)
    return TypeExpr(collected, [a for a in alternatives if a], i)


def _is_undefined(tok: Token) -> bool:
    return tok.kind == "KEYWORD" and tok.canonical == "UNDEFINED"


# --- Declarations and signatures ------------------------------------------------------

@dataclass
class Declaration:
    """A declaration `знч/пер/поймать/обз Имя[, Имя2]: Тип [= инициализация]`."""

    keyword: Token
    names: list[Token]
    colon: Token | None
    type_start: int | None  # index of the token where the type begins
    assign: Token | None  # the `=` token, if there is an initialization
    value_start: int | None  # index of the first token of the value


def declarations(toks: list[Token]) -> list[Declaration]:
    """All declarations introduced by знч/пер/поймать/обз in the token list."""
    out: list[Declaration] = []
    n = len(toks)
    for i, t in enumerate(toks):
        if t.kind != "KEYWORD" or t.canonical not in DECL_KEYWORDS:
            continue
        j = _skip_comments(toks, i + 1)
        names: list[Token] = []
        while j < n and toks[j].kind == "IDENT":
            names.append(toks[j])
            k = _skip_comments(toks, j + 1)
            if k < n and toks[k].kind == "OP" and toks[k].value == ",":
                j = _skip_comments(toks, k + 1)
                continue
            j = k
            break
        if not names:
            continue

        colon = type_start = None
        if j < n and toks[j].kind == "OP" and toks[j].value == ":":
            colon = toks[j]
            type_start = _skip_comments(toks, j + 1)
            te = type_expr(toks, type_start)
            j = te.end if te is not None else type_start

        assign = value_start = None
        j = _skip_comments(toks, j)
        if j < n and toks[j].kind == "OP" and toks[j].value == "=":
            assign = toks[j]
            value_start = _skip_comments(toks, j + 1)

        out.append(Declaration(t, names, colon, type_start, assign, value_start))
    return out


@dataclass
class Param:
    """A method parameter: name, the type colon (if any) and the default value."""

    name: Token
    colon: Token | None
    type_start: int | None
    has_default: bool


@dataclass
class Signature:
    """A method/constructor signature: name, parameters and the return-type colon."""

    keyword: Token
    name: Token
    params: list[Param]
    return_colon: Token | None
    return_type_start: int | None


def signatures(toks: list[Token]) -> list[Signature]:
    """Signatures of all methods and constructors in the token list."""
    out: list[Signature] = []
    n = len(toks)
    for i, t in enumerate(toks):
        if t.kind != "KEYWORD" or t.canonical not in SIGNATURE_KEYWORDS or not t.value[:1].islower():
            continue
        j = _skip_comments(toks, i + 1)
        if j >= n or toks[j].kind != "IDENT":
            continue
        name = toks[j]
        p = _skip_comments(toks, j + 1)
        if p >= n or not (toks[p].kind == "OP" and toks[p].value == "("):
            continue

        params: list[Param] = []
        depth, k = 1, p + 1
        expect_name = True
        current: Param | None = None
        while k < n and depth > 0:
            tk = toks[k]
            if tk.kind == "COMMENT":
                k += 1
                continue
            if tk.kind == "OP" and tk.value in _OPEN_CH:
                depth += 1
                k += 1
                continue
            if tk.kind == "OP" and tk.value in _CLOSE_CH:
                depth -= 1
                k += 1
                continue
            if depth == 1 and expect_name and tk.kind == "IDENT":
                current = Param(tk, None, None, False)
                params.append(current)
                expect_name = False
                c = _skip_comments(toks, k + 1)
                if c < n and toks[c].kind == "OP" and toks[c].value == ":":
                    current.colon = toks[c]
                    current.type_start = _skip_comments(toks, c + 1)
                    te = type_expr(toks, current.type_start)
                    k = te.end if te is not None else current.type_start
                    continue
                k = c
                continue
            if depth == 1 and tk.kind == "OP" and tk.value == "=":
                if current is not None:
                    current.has_default = True
                k += 1
                continue
            if depth == 1 and tk.kind == "OP" and tk.value == ",":
                expect_name = True
                k += 1
                continue
            k += 1

        return_colon = return_type_start = None
        r = _skip_comments(toks, k)
        if r < n and toks[r].kind == "OP" and toks[r].value == ":":
            return_colon = toks[r]
            return_type_start = _skip_comments(toks, r + 1)

        out.append(Signature(t, name, params, return_colon, return_type_start))
    return out
