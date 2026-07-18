"""Runtime access to the Element documentation (docs.sqlite): search, page, tree, symbol.

The database is built by `tools/extract_docs.py` from the distribution and lives in the
data bundle at `<root>/<version>/docs.sqlite` next to `stdlib.json` (see dataset.py). The
documentation is optional: when the database is missing, `available()` returns False and
the other functions return an empty result, so the MCP server and the LSP keep working
without it.

A connection is opened per request and closed right away: requests are rare (driven by a
user action), while the database file is not kept open - it can be rebuilt while the
server is alive (on Windows an open connection blocks overwriting).

Built on top of this API: the MCP tools (Claude searches methods, their properties and
parameters), the LSP "docs for the symbol under the cursor" endpoint, and the extension
panel (tree + HTML view).
"""
from __future__ import annotations

import re
import sqlite3
from pathlib import Path

from xbsl import dataset

_DB_NAME = "docs.sqlite"
# Query token: letters (incl. Cyrillic), digits, underscore - everything else is dropped for FTS5.
_TOKEN_RE = re.compile(r"\w+", re.UNICODE)
# Images live as files next to the database (`<version>/assets/...`), mime is derived from the extension.
_MIME = {
    ".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg",
    ".gif": "image/gif", ".svg": "image/svg+xml", ".webp": "image/webp",
}


def available(version: str | None = None) -> bool:
    """Whether a documentation database exists for the data version."""
    return dataset.has_data_file(_DB_NAME, version)


def _open(version: str | None = None) -> sqlite3.Connection | None:
    """A fresh read-only connection (the caller must close it) or None if there is no database."""
    if not available(version):
        return None
    uri = Path(dataset.data_file(_DB_NAME, version)).as_uri() + "?mode=ro"  # file URI on any OS
    con = sqlite3.connect(uri, uri=True)
    con.row_factory = sqlite3.Row
    return con


def _fts_query(query: str) -> str:
    """Free text -> a safe FTS5 expression: quoted words joined with AND, the last one as a prefix."""
    tokens = _TOKEN_RE.findall(query)
    if not tokens:
        return ""
    terms = [f'"{t}"' for t in tokens[:-1]]
    terms.append(f'"{tokens[-1]}"*')  # prefix on the last word - convenient while typing
    return " ".join(terms)


def search(query: str, limit: int = 10, version: str | None = None) -> list[dict]:
    """Full-text search over the documentation, bm25 ranking (best first)."""
    match = _fts_query(query)
    if not match:
        return []
    con = _open(version)
    if con is None:
        return []
    try:
        rows = con.execute(
            "SELECT p.id, p.title, p.qualified, p.kind, p.availability, p.url,"
            "       snippet(pages_fts, 3, '', '', ' ... ', 12) AS snippet "
            "FROM pages_fts f JOIN pages p ON p.id = f.id "
            "WHERE pages_fts MATCH ? ORDER BY bm25(pages_fts) LIMIT ?",
            (match, limit),
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        con.close()


def page(doc_id: str, version: str | None = None) -> dict | None:
    """Full page record (with cleaned HTML) by its id, or None."""
    con = _open(version)
    if con is None:
        return None
    try:
        row = con.execute(
            "SELECT id, kind, title, qualified, availability, url, html FROM pages WHERE id = ?",
            (doc_id,),
        ).fetchone()
        return dict(row) if row else None
    finally:
        con.close()


def type_pages(version: str | None = None) -> list[dict]:
    """All reference pages of kind 'type' (id, title, qualified, html), ordered by id.

    A bulk read for offline consumers - tools/extract_uischema.py derives the interface
    component ui schema from these pages. Empty list when the documentation is absent.
    """
    con = _open(version)
    if con is None:
        return []
    try:
        rows = con.execute(
            "SELECT id, title, qualified, html FROM pages WHERE kind = 'type' ORDER BY id"
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        con.close()


def tree(version: str | None = None) -> list[dict]:
    """Flat list of curated table-of-contents nodes - the consumer builds the tree.

    Node: node (node id), parent (parent id, or None for a tab section), label (caption),
    page (page id to link to, otherwise None), anchor (section id on the page for a heading
    node), kind (section/category/link/heading).
    """
    con = _open(version)
    if con is None:
        return []
    try:
        rows = con.execute(
            "SELECT node, parent, ord, label, page, anchor, kind FROM tree "
            "ORDER BY parent IS NOT NULL, parent, ord"
        ).fetchall()
        return [dict(r) for r in rows]
    except sqlite3.OperationalError:
        return []  # old-schema database (no curated tree) - empty result rather than a failure
    finally:
        con.close()


def for_symbol(name: str, version: str | None = None) -> str | None:
    """Page id for a symbol/type name on a CONFIDENT match, otherwise None.

    A match is an exact title or the last qualifier segment (`Стд::...::Массив`); for a
    type we prefer the reference (stdlib) page over a guide topic with the same title.
    There is NO fuzzy (full-text) fallback here: a method section (e.g. `Настроить`) has
    no exact page, and a guide topic guessed by the word is confusing - candidates are
    picked by the caller via search().
    """
    if not name:
        return None
    name = name.strip()
    con = _open(version)
    if con is None:
        return None
    try:
        exact = con.execute(
            "SELECT id FROM pages WHERE title = ? "
            "ORDER BY id LIKE 'stdlib/%' DESC, length(qualified) LIMIT 1",
            (name,),
        ).fetchone()
        if exact:
            return exact["id"]
        byq = con.execute(
            "SELECT id FROM pages WHERE qualified LIKE ? "
            "ORDER BY id LIKE 'stdlib/%' DESC, length(qualified) LIMIT 1",
            (f"%::{name}",),
        ).fetchone()
        return byq["id"] if byq else None
    finally:
        con.close()


def asset(asset_id: str, version: str | None = None) -> dict | None:
    """Image bytes by its id (`assets/...`) with mime - a file next to the database, or None.

    Images are stored not in the database but as files in `<root>/<version>/assets/...`
    (git-lfs). The path is confined to the assets subdirectory - no escaping the bundle.
    """
    if not asset_id.startswith("assets/") or ".." in asset_id:
        return None
    try:
        ver = dataset.resolve_version(version)
    except dataset.DatasetError:
        return None
    path = dataset.data_root() / ver / asset_id
    if not path.is_file():
        return None
    return {
        "id": asset_id,
        "mime": _MIME.get(path.suffix.lower(), "application/octet-stream"),
        "bytes": path.read_bytes(),
    }
