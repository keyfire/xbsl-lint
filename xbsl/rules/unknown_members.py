"""Tier D: a member access on a variable of a known stdlib type must exist on that type.

First-hop only, negatives only. A variable counts as typed when every declaration of that
name in the method (parameters, `пер`/`знч` with an explicit type, `поймать`) names the
same single non-generic stdlib type; the member is then checked against the type's
properties + methods from the stdlib catalog. Everything else is skipped: project types,
generic and compound types, chains beyond the first hop, Latin member spellings (the
bilingual stdlib is cataloged under Russian member names), names redeclared with
different or absent types anywhere in the method (lambda parameters included).
"""

from __future__ import annotations

import difflib
from collections.abc import Iterable

from xbsl import dataset, i18n
from xbsl import parser as P
from xbsl.diagnostics import Diagnostic, Severity
from xbsl.engine import SourceFile, rule
from xbsl.lexer import linemap
from xbsl.parser import parse

MESSAGES = {
    "code/unknown-member.title": {
        "ru": "Неизвестный член типа",
        "en": "Unknown member of a type",
    },
    "code/unknown-member.found": {
        "ru": "У типа {type} нет члена {member}",
        "en": "The type {type} has no member {member}",
    },
    "code/unknown-member.found-hint": {
        "ru": "У типа {type} нет члена {member} – возможно, имелся в виду {hint}",
        "en": "The type {type} has no member {member} - did you mean {hint}",
    },
}
i18n.register(MESSAGES)

# Undocumented members seen on every instance (the object protocol).
_COMMON_MEMBERS = frozenset({"ПолучитьТип", "ВСтроку", "Представление"})

# Entity aggregates (Пользователи, ДвоичныйОбъект, register records...) carry an
# undocumented record protocol (Ид, Ссылка, Загрузить, ЗагрузитьОбъект...) on top of
# their documented page - their member lists are incomplete, so they are not checked.
_ENTITY_MARKERS = frozenset({"Записать", "Ссылка", "ПолучитьСсылку"})

_members_cache: dict[str, frozenset[str]] | None = None


def _stdlib_members() -> dict[str, frozenset[str]]:
    global _members_cache
    if _members_cache is None:
        try:
            raw = dataset.load_json("stdlib.json").get("type_members") or {}
        except Exception:  # noqa: BLE001 - no data, no rule
            raw = {}
        _members_cache = {}
        for name, m in raw.items():
            members = frozenset(m.get("properties", ())) | frozenset(m.get("methods", ()))
            if not (_ENTITY_MARKERS & members):
                _members_cache[name] = members
    return _members_cache


def _nominal(tref: P.TypeRef | None) -> str | None:
    """The single plain type name of a declaration, or None when anything is fancy."""
    if tref is None or len(tref.names) != 1:
        return None
    name = tref.names[0]
    if "::" in name or "." in name or "<" in tref.text:
        return None
    return name


class _Scope:
    """Per-method collection: name -> type (or None once the name is poisoned)."""

    def __init__(self) -> None:
        self.types: dict[str, str | None] = {}

    def declare(self, name: str, tref: P.TypeRef | None) -> None:
        nominal = _nominal(tref)
        if name in self.types and self.types[name] != nominal:
            self.types[name] = None
        else:
            self.types[name] = nominal


def _walk_expr(expr: P.Expr | None, scope: _Scope, uses: list[P.Member]) -> None:
    if expr is None:
        return
    if isinstance(expr, P.Member):
        if isinstance(expr.obj, P.Name):
            uses.append(expr)
        else:
            _walk_expr(expr.obj, scope, uses)
        return
    if isinstance(expr, P.Lambda):
        for p in expr.params:
            scope.declare(p.name, p.type)
        if isinstance(expr.body_expr, P.Expr):
            _walk_expr(expr.body_expr, scope, uses)
        elif isinstance(expr.body_expr, P.Assign):
            _walk_expr(expr.body_expr.target, scope, uses)
            _walk_expr(expr.body_expr.value, scope, uses)
        if expr.body_stmts is not None:
            _walk_body(expr.body_stmts, scope, uses)
        return
    if isinstance(expr, P.Call):
        _walk_expr(expr.callee, scope, uses)
        for arg in expr.args:
            _walk_expr(arg.value, scope, uses)
    elif isinstance(expr, P.Unary):
        _walk_expr(expr.operand, scope, uses)
    elif isinstance(expr, P.Binary):
        _walk_expr(expr.left, scope, uses)
        _walk_expr(expr.right, scope, uses)
    elif isinstance(expr, P.Compare):
        _walk_expr(expr.first, scope, uses)
        for _op, right in expr.rest:
            _walk_expr(right, scope, uses)
    elif isinstance(expr, (P.IsType, P.AsType, P.NonNull)):
        _walk_expr(expr.operand, scope, uses)
    elif isinstance(expr, P.Ternary):
        _walk_expr(expr.cond, scope, uses)
        _walk_expr(expr.then, scope, uses)
        _walk_expr(expr.otherwise, scope, uses)
    elif isinstance(expr, P.Coalesce):
        _walk_expr(expr.left, scope, uses)
        _walk_expr(expr.right, scope, uses)
    elif isinstance(expr, P.Index):
        _walk_expr(expr.obj, scope, uses)
        _walk_expr(expr.index, scope, uses)
    elif isinstance(expr, P.New):
        if expr.args:
            for arg in expr.args:
                _walk_expr(arg.value, scope, uses)
    elif isinstance(expr, P.ArrayLit):
        for item in expr.items:
            _walk_expr(item, scope, uses)
    elif isinstance(expr, P.MapLit):
        for k, v in expr.entries:
            _walk_expr(k, scope, uses)
            _walk_expr(v, scope, uses)
    elif isinstance(expr, P.Throw):
        _walk_expr(expr.value, scope, uses)


def _walk_body(stmts: list[P.Stmt], scope: _Scope, uses: list[P.Member]) -> None:
    for st in stmts:
        if isinstance(st, P.VarDecl):
            scope.declare(st.name, st.type)
            _walk_expr(st.init, scope, uses)
        elif isinstance(st, P.Assign):
            _walk_expr(st.target, scope, uses)
            _walk_expr(st.value, scope, uses)
        elif isinstance(st, (P.ExprStmt, P.UseStmt)):
            _walk_expr(st.expr, scope, uses)
        elif isinstance(st, P.If):
            for cond, body in st.branches:
                _walk_expr(cond, scope, uses)
                _walk_body(body, scope, uses)
            if st.else_body is not None:
                _walk_body(st.else_body, scope, uses)
        elif isinstance(st, P.Case):
            if st.subject is not None:
                _walk_expr(st.subject, scope, uses)
            for when in st.whens:
                for cond in when.conditions:
                    _walk_expr(cond, scope, uses)
                _walk_body(when.body, scope, uses)
            if st.else_body is not None:
                _walk_body(st.else_body, scope, uses)
        elif isinstance(st, P.While):
            _walk_expr(st.cond, scope, uses)
            _walk_body(st.body, scope, uses)
        elif isinstance(st, P.ForEach):
            scope.declare(st.var, None)  # the element type is inference territory
            _walk_expr(st.source, scope, uses)
            _walk_body(st.body, scope, uses)
        elif isinstance(st, P.ForTo):
            scope.declare(st.var, None)
            _walk_expr(st.start_expr, scope, uses)
            _walk_expr(st.to, scope, uses)
            if st.step is not None:
                _walk_expr(st.step, scope, uses)
            _walk_body(st.body, scope, uses)
        elif isinstance(st, P.Try):
            _walk_body(st.body, scope, uses)
            for var, tref, body in st.catches:
                if var:
                    scope.declare(var, tref)
                _walk_body(body, scope, uses)
            if st.finally_body is not None:
                _walk_body(st.finally_body, scope, uses)
        elif isinstance(st, P.Scope):
            _walk_body(st.body, scope, uses)
        elif isinstance(st, P.Return):
            _walk_expr(st.value, scope, uses)


def _is_latin(name: str) -> bool:
    return all(ord(c) < 128 for c in name)


@rule("code/unknown-member", "code/unknown-member.title", "D", severity=Severity.ERROR)
def unknown_member(source: SourceFile) -> Iterable[Diagnostic]:
    """A first-hop member access on a variable of a plain stdlib type must exist on it."""
    if source.kind != "xbsl":
        return
    members_by_type = _stdlib_members()
    if not members_by_type:
        return
    module, errors = parse(source)
    if errors:
        return
    lm = linemap(source)
    methods: list[P.Method] = []
    for m in module.members:
        if isinstance(m, P.Method):
            methods.append(m)
        elif isinstance(m, P.Structure):
            methods.extend(sub for sub in m.members if isinstance(sub, P.Method))
        elif isinstance(m, P.Enum):
            methods.extend(m.methods)
    for method in methods:
        scope = _Scope()
        for p in method.params:
            scope.declare(p.name, p.type)
        uses: list[P.Member] = []
        for p in method.params:
            _walk_expr(p.default, scope, uses)
        _walk_body(method.body, scope, uses)
        for use in uses:
            assert isinstance(use.obj, P.Name)
            type_name = scope.types.get(use.obj.name)
            if type_name is None:
                continue
            members = members_by_type.get(type_name)
            if members is None or _is_latin(use.name):
                continue
            if use.name in members or use.name in _COMMON_MEMBERS:
                continue
            hint = difflib.get_close_matches(use.name, members, n=1, cutoff=0.75)
            line, col = lm.linecol(use.start)
            message = (
                i18n.t("code/unknown-member.found-hint",
                       type=type_name, member=use.name, hint=hint[0])
                if hint
                else i18n.t("code/unknown-member.found", type=type_name, member=use.name)
            )
            yield Diagnostic(
                source.rel, line, col, "code/unknown-member", Severity.ERROR, message,
            )
