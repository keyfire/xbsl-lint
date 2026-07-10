"""The linter's MCP adapter (a thin wrapper over xbsllint.engine).

Run: xbsllint-mcp  (or python -m xbsllint.mcp_server). Transport – stdio.
The `mcp` dependency comes from an extra:  pip install "xbsllint[mcp]".

Diagnostic message language follows env XBSLLINT_LANG (then the system locale, then ru), since
an MCP server takes no CLI flags.

Registration in Claude Code:
    claude mcp add xbsllint -- xbsllint-mcp
"""

from __future__ import annotations

from pathlib import Path

from xbsllint.cli import discover
from xbsllint.diagnostics import Diagnostic
from xbsllint.engine import RULES, load_text, run, run_sources

try:
    from mcp.server.fastmcp import FastMCP
except ModuleNotFoundError as exc:  # pragma: no cover - hint when the dependency is absent
    raise SystemExit(
        "The 'mcp' package is missing. Install the MCP extra: pip install \"xbsllint[mcp]\""
    ) from exc


mcp = FastMCP("xbsllint")


def _diag_dict(d: Diagnostic) -> dict:
    return {
        "path": d.path,
        "line": d.line,
        "col": d.col,
        "rule": d.rule_id,
        "severity": d.severity.value,
        "message": d.message,
    }


def _summary(diags: list[Diagnostic], n_files: int) -> dict:
    return {
        "files": n_files,
        "diagnostics": len(diags),
        "errors": sum(1 for d in diags if d.severity.value == "error"),
        "warnings": sum(1 for d in diags if d.severity.value == "warning"),
    }


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
    diags = sorted(diags, key=lambda x: x.sort_key())
    return {"diagnostics": [_diag_dict(d) for d in diags], "summary": _summary(diags, len(files))}


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
    diags = sorted(diags, key=lambda x: x.sort_key())
    return {"diagnostics": [_diag_dict(d) for d in diags], "summary": _summary(diags, 1)}


def main() -> None:
    mcp.run()


if __name__ == "__main__":
    main()
