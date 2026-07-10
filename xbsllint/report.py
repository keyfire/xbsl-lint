"""The machine-readable report shape, shared by the CLI (--format json), the MCP server and editors.

One contract for structured output — a list of diagnostics plus a summary — so that the CLI and the
MCP adapter cannot drift apart. Editors (the VS Code extension) consume the same JSON.
"""

from __future__ import annotations

from xbsllint.diagnostics import Diagnostic


def diag_dict(d: Diagnostic) -> dict:
    """One diagnostic as a plain dict. Position is 1-based (line, col), as in the model."""
    return {
        "path": d.path,
        "line": d.line,
        "col": d.col,
        "rule": d.rule_id,
        "severity": d.severity.value,
        "message": d.message,
    }


def summary(diags: list[Diagnostic], n_files: int) -> dict:
    return {
        "files": n_files,
        "diagnostics": len(diags),
        "errors": sum(1 for d in diags if d.severity.value == "error"),
        "warnings": sum(1 for d in diags if d.severity.value == "warning"),
    }


def report(diags: list[Diagnostic], n_files: int) -> dict:
    """The full payload: {diagnostics: [...sorted...], summary: {...}}."""
    ordered = sorted(diags, key=lambda x: x.sort_key())
    return {
        "diagnostics": [diag_dict(d) for d in ordered],
        "summary": summary(ordered, n_files),
    }
