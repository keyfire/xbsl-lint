"""The linter core: source loading, the rule registry and the run.

Rules register themselves with the @rule(...) decorator (id, tier, severity, scope). Scope:
- 'file'    – per-file rule: (SourceFile) -> Iterable[Diagnostic];
- 'project' – cross-file rule (e.g. Ид uniqueness): (list[SourceFile]) -> Iterable[Diagnostic].

Tiers: 'A' structure/YAML, 'B' text/conventions, 'C' parser/code structure, 'D' semantics.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable
from dataclasses import dataclass, field
from pathlib import Path

from xbsllint import i18n
from xbsllint.diagnostics import Diagnostic, Severity

UTF8_BOM = b"\xef\xbb\xbf"


@dataclass
class SourceFile:
    path: Path
    kind: str  # 'xbsl' | 'yaml'
    data: bytes
    text: str
    had_bom: bool
    newline: str  # '\n', '\r\n', '\r', 'mixed', or '' when there are no line breaks
    decode_error: str | None = None
    # Cache of the expensive representations (tokens, AST, YAML) – filled on demand
    cache: dict = field(default_factory=dict)

    @property
    def rel(self) -> str:
        return str(self.path)


def _detect_newline(data: bytes) -> str:
    crlf = data.count(b"\r\n")
    cr = data.count(b"\r") - crlf
    lf = data.count(b"\n") - crlf
    kinds = [k for k, n in (("\r\n", crlf), ("\r", cr), ("\n", lf)) if n]
    if not kinds:
        return ""
    if len(kinds) > 1:
        return "mixed"
    return kinds[0]


def make_source(path: Path, data: bytes) -> SourceFile:
    """Build a SourceFile from a path and bytes (shared by the disk and memory paths)."""
    kind = "xbsl" if path.suffix == ".xbsl" else "yaml"
    had_bom = data.startswith(UTF8_BOM)
    decode_error: str | None = None
    try:
        text = data.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        decode_error = str(exc)
        text = data.decode("utf-8", errors="replace")
    return SourceFile(
        path=path,
        kind=kind,
        data=data,
        text=text,
        had_bom=had_bom,
        newline=_detect_newline(data),
        decode_error=decode_error,
    )


def load(path: Path) -> SourceFile:
    return make_source(path, path.read_bytes())


def load_text(name: str, content: str) -> SourceFile:
    """Build a SourceFile from in-memory content (for the MCP lint_source tool)."""
    return make_source(Path(name), content.encode("utf-8"))


# --- Rule registry -------------------------------------------------------------------

FileRuleFn = Callable[[SourceFile], Iterable[Diagnostic]]
ProjectRuleFn = Callable[[list[SourceFile]], Iterable[Diagnostic]]


@dataclass(frozen=True)
class RuleInfo:
    id: str
    title_key: str
    tier: str  # 'A' | 'B' | 'C' | 'D'
    scope: str  # 'file' | 'project'
    severity: Severity
    func: Callable
    enabled_by_default: bool = True

    @property
    def title(self) -> str:
        """Translated at read time: the output language may be set after registration."""
        return i18n.t(self.title_key)

    def as_dict(self) -> dict:
        return {
            "id": self.id,
            "title": self.title,
            "tier": self.tier,
            "scope": self.scope,
            "severity": self.severity.value,
            "enabled_by_default": self.enabled_by_default,
        }


RULES: list[RuleInfo] = []


def rule(
    rule_id: str,
    title: str,
    tier: str,
    *,
    scope: str = "file",
    severity: Severity = Severity.WARNING,
    enabled_by_default: bool = True,
) -> Callable[[Callable], Callable]:
    """Register a rule with its metadata.

    `title` is a catalog key (`<rule id>.title`); a literal string still works and is used
    verbatim, which keeps plugins written against 0.3 running.
    """

    def deco(fn: Callable) -> Callable:
        RULES.append(RuleInfo(rule_id, title, tier, scope, severity, fn, enabled_by_default))
        return fn

    return deco


def _is_selected(info: RuleInfo, select: set[str] | None, ignore: set[str] | None) -> bool:
    # select/ignore match a rule id, a rule group (the part of the id before '/')
    # or a tier letter ('A'..'D')
    group = info.id.split("/", 1)[0]

    def matches(keys: set[str]) -> bool:
        return info.id in keys or group in keys or info.tier in keys

    if ignore and matches(ignore):
        return False
    if select:
        # An explicit selection enables a rule even when it is off by default
        return matches(select)
    return info.enabled_by_default


def active_rules(select: set[str] | None = None, ignore: set[str] | None = None) -> list[RuleInfo]:
    return [r for r in RULES if _is_selected(r, select, ignore)]


def run_sources(
    sources: list[SourceFile],
    *,
    select: set[str] | None = None,
    ignore: set[str] | None = None,
    scopes: tuple[str, ...] = ("file", "project"),
) -> list[Diagnostic]:
    diags: list[Diagnostic] = []
    active = active_rules(select, ignore)
    if "file" in scopes:
        file_rules = [r for r in active if r.scope == "file"]
        for src in sources:
            for r in file_rules:
                diags.extend(r.func(src))
    if "project" in scopes:
        for r in (r for r in active if r.scope == "project"):
            diags.extend(r.func(sources))
    return diags


def run(
    paths: list[Path],
    *,
    select: set[str] | None = None,
    ignore: set[str] | None = None,
) -> list[Diagnostic]:
    sources = [load(p) for p in paths]
    return run_sources(sources, select=select, ignore=ignore)


# Importing the rules package registers them (the decorators run on module import).
from xbsllint import rules as _rules  # noqa: E402,F401
from xbsllint import plugins as _plugins  # noqa: E402

# Rules of external packages come after the built-in ones, to keep the registry order stable.
_plugins.load_rules()
