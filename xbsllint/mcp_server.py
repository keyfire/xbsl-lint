"""The linter's MCP adapter (a thin wrapper over xbsllint.engine).

Run: xbsllint-mcp  (or python -m xbsllint.mcp_server). Transport – stdio.
The `mcp` dependency comes from an extra:  pip install "xbsllint[mcp]".

Diagnostic message language follows env XBSLLINT_LANG (then the system locale, then ru), since
an MCP server takes no CLI flags.

Registration in Claude Code:
    claude mcp add xbsllint -- xbsllint-mcp
"""

from __future__ import annotations

import re
from html import unescape
from pathlib import Path

from xbsllint import docs, report
from xbsllint.cli import discover
from xbsllint.engine import RULES, load_text, run, run_sources

_TAGS_RE = re.compile(r"<[^>]+>")

try:
    from mcp.server.fastmcp import FastMCP
except ModuleNotFoundError as exc:  # pragma: no cover - hint when the dependency is absent
    raise SystemExit(
        "The 'mcp' package is missing. Install the MCP extra: pip install \"xbsllint[mcp]\""
    ) from exc


mcp = FastMCP("xbsllint")


def _as_set(value: list[str] | None) -> set[str] | None:
    return set(value) if value else None


@mcp.tool()
def list_rules() -> list[dict]:
    """List the available linter rules (id, title, tier, scope, severity)."""
    return [r.as_dict() for r in sorted(RULES, key=lambda x: (x.tier, x.id))]


@mcp.tool()
def lint_paths(
    paths: list[str],
    select: list[str] | None = None,
    ignore: list[str] | None = None,
) -> dict:
    """Check files/directories on disk.

    paths  – list of paths (.xbsl/.yaml files or directories, traversed recursively);
    select – limit the rule set (id or tier letter A/B/C/D);
    ignore – exclude rules.
    Returns {diagnostics: [...], summary: {...}}.
    """
    files = discover(paths)
    diags = run(files, select=_as_set(select), ignore=_as_set(ignore))
    return report.report(diags, len(files))


@mcp.tool()
def lint_source(
    filename: str,
    content: str,
    select: list[str] | None = None,
    ignore: list[str] | None = None,
) -> dict:
    """Check in-memory content (e.g. before writing the file).

    filename – name with an extension (.xbsl/.yaml); sets the kind and appears in positions;
    content  – the source text.
    Only per-file rules run (cross-file rules need the whole project).
    """
    src = load_text(filename, content)
    diags = run_sources(
        [src], select=_as_set(select), ignore=_as_set(ignore), scopes=("file",)
    )
    return report.report(diags, 1)


def _page_as_text(doc_id: str | None) -> dict:
    """Страница документации с текстовой (не HTML) выжимкой – в таком виде её удобно читать модели."""
    page = docs.page(doc_id) if doc_id else None
    if page is None:
        return {}
    page = dict(page)
    page["text"] = unescape(_TAGS_RE.sub(" ", page.pop("html"))).strip()
    return page


@mcp.tool()
def docs_search(query: str, limit: int = 10) -> list[dict]:
    """Full-text search over the 1C:Element documentation.

    Covers stdlib types, their methods, properties and parameters. Returns ranked hits
    (best first): id, title, qualified name, kind, availability and a text snippet. Pass a hit's
    id to docs_page to read the full article. Empty list if the docs data is not installed.
    """
    return docs.search(query, limit=limit)


@mcp.tool()
def docs_page(id: str) -> dict:
    """Read a documentation page by its id (obtained from docs_search or docs_symbol).

    Returns id, kind, title, qualified name, availability and the article as plain text.
    Empty object if there is no such page (or the docs data is not installed).
    """
    return _page_as_text(id)


@mcp.tool()
def docs_symbol(name: str) -> dict:
    """Find the documentation page for a symbol by name (a type or member, e.g. "Массив", "Запрос").

    Prefers an exact title match, then a qualified-name match, then the top search hit. Returns the
    same shape as docs_page, or an empty object if nothing matches.
    """
    return _page_as_text(docs.for_symbol(name))


def main() -> None:
    mcp.run()


if __name__ == "__main__":
    main()
