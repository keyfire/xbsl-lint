"""Tier D: undefined names in expressions - the first pass of the symbol table over the AST.

Catches the classic typo the compiler rejects but no token heuristic can see:

    метод ТелоПравки(Адреса: Массив<Строка>): Строка
        для Адрес из Адресар   // <- 'Адресар' is not declared anywhere

Scope model (per the platform semantics):
- the module level contributes its methods, structures/enums/exceptions and module
  fields/constants;
- a method contributes its parameters; statements introduce names as they go (пер/знч/исп,
  loop variables, поймать variables); a lambda opens a nested scope with its parameters;
- the project contributes object and common-module names (from the yaml sources of the run),
  the stdlib contributes its global names - both via the helpers of rules/semantics.py.

Only the ROOT of a member chain is checked (`Х` in `Х.Поле[0].Метод()`): member names need
type inference (stage 3). Qualified roots (`Подсистема::Имя`) and method references are
skipped. Roots the file's module kind provides implicitly (`Компоненты` of a form module,
`Это`/`До` of an object module etc.) are collected in _IMPLICIT - verified on the corpus.

The rule needs the stdlib catalog (tier D): without the data it is silent - a name unknown
to an incomplete world is not evidence.
"""

from __future__ import annotations

import difflib
from collections.abc import Iterable

from xbsl import dataset, i18n, parser as P
from xbsl.diagnostics import Diagnostic, Severity
from xbsl.engine import SourceFile, rule
from xbsl.lexer import linemap
from xbsl.rules.semantics import _parsed, _project_object_names, _stdlib_names

MESSAGES = {
    "code/undefined-name.title": {
        "ru": "Неизвестное имя",
        "en": "Undefined name",
    },
    "code/undefined-name.found": {
        "ru": "Имя '{name}' нигде не объявлено – компилятор откажет.",
        "en": "Name '{name}' is not declared anywhere - the compiler will reject it.",
    },
    "code/undefined-name.found-hint": {
        "ru": "Имя '{name}' нигде не объявлено – возможно, имелось в виду '{hint}'.",
        "en": "Name '{name}' is not declared anywhere - did you mean '{hint}'?",
    },
}
i18n.register(MESSAGES)

# Context roots the module kind itself provides (never declared in code): collected by
# running over the corpus and from the documentation of the module kinds.
_IMPLICIT = frozenset({
    "Компоненты", "Components",   # an interface-component module: access to the named form components
    "Это", "До",    # an object module: the record after/before the change in ПередЗаписью/ПослеЗаписи
    "Сущность",     # the rights namespace in permission handlers (Сущность.Право.Чтение)
})

# Standard attributes available by bare name in an entity module (X.Объект.xbsl): the
# platform provides them without a yaml declaration (Наименование/Код of a catalog,
# Номер/Дата of a document, Период/Регистратор/ВидЗаписи of register records) plus
# Ссылка and the write methods.
# Members that exist on the platform but are absent from the distribution docs -
# verified against real shipped code (БизКуб, the demo project). Kept deliberately tiny.
_UNDOCUMENTED = frozenset({
    "ВыполнитьЗаписать", "ВыполнитьЗаписатьИЗакрыть",  # ФормаОбъекта commands
    "СобственнаяМодифицированность",                   # a form-component property
    "Message",                                          # the English form of Сообщить
})

_ENTITY_COMMON = frozenset({
    "Наименование", "Код", "Номер", "Дата", "Ссылка",
    "Период", "Регистратор", "ВидЗаписи",
    "Записать", "Удалить", "ПометитьНаУдаление", "СнятьПометкуУдаления",
    "ЭтоНовый", "ПометкаУдаления", "РежимЗагрузкиДанных",
})

# The yaml sections whose items become bare names in the object modules.
_FIELD_SECTIONS = (
    "Реквизиты", "Измерения", "Ресурсы", "Константы", "Свойства", "Параметры",
    "ТабличныеЧасти", "События", "Поля",
)


def _yaml_pair(source: SourceFile, by_dir: dict) -> SourceFile | None:
    """The paired yaml of a module: X.xbsl -> X.yaml, X.Объект.xbsl -> X.yaml."""
    parts = source.rel.replace("\\", "/").rsplit("/", 1)
    directory = parts[0] if len(parts) == 2 else ""
    stem = parts[-1]
    for suffix in (".Объект.xbsl", ".xbsl"):
        if stem.endswith(suffix):
            stem = stem[: -len(suffix)]
            break
    return by_dir.get((directory, stem + ".yaml"))


def _section_names(data: dict) -> set[str]:
    names: set[str] = set()
    for section in _FIELD_SECTIONS:
        items = data.get(section)
        if isinstance(items, list):
            for item in items:
                if isinstance(item, dict) and isinstance(item.get("Имя"), str):
                    names.add(item["Имя"])
    return names


def _base_type_root(data: dict) -> str | None:
    inherits = data.get("Наследует")
    base = inherits.get("Тип") if isinstance(inherits, dict) else None
    if not isinstance(base, str):
        return None
    return base.split("<", 1)[0].strip()


def _component_scope(
    data: dict, by_name: dict, type_members: dict, seen: set[str],
) -> set[str]:
    """The names a component gives its module: Свойства plus the base members up the chain.

    The base is either a platform type (members from type_members) or a project component
    (its Свойства and its base, recursively); an inheritance cycle is cut by `seen`.
    """
    names = _section_names(data)
    root = _base_type_root(data)
    if not root or root in seen:
        return names
    seen.add(root)
    members = type_members.get(root)
    if members:
        names |= set(members.get("properties", ())) | set(members.get("methods", ()))
    parent = by_name.get(root)
    if parent is not None:
        names |= _component_scope(parent, by_name, type_members, seen)
    return names


# On by default (severity error - the compiler rejects such code) since the stdlib
# catalog carries the global context (Сообщить, ПерейтиПоСсылке...) and the kind-manager
# methods: the whole real-world corpus (site, БизКуб, chiriker, demo - 1600+ modules)
# runs with zero false findings.
@rule(
    "code/undefined-name", "code/undefined-name.title", "D",
    scope="project", severity=Severity.ERROR,
)
def undefined_name(sources: list[SourceFile]) -> Iterable[Diagnostic]:
    stdlib = _stdlib_names()
    if not stdlib:
        return  # without the stdlib catalog "unknown" cannot be proven
    try:
        catalog = dataset.load_json("stdlib.json")
    except dataset.DatasetError:
        return
    type_members = catalog.get("type_members", {})
    object_members = catalog.get("object_members", {})
    manager_members = catalog.get("manager_members", {})
    # The global context: members of Стд and its first-level packages (Сообщить,
    # ПерейтиПоСсылке, ЗагрузкаФайлов...) are reachable by bare name everywhere.
    context_globals = set(catalog.get("globals", ()))
    known_global = (set(stdlib) | _project_object_names(sources) | _IMPLICIT
                    | context_globals | _UNDOCUMENTED)

    # Maps of the paired yaml: by (directory, file name) and by object name (for the Наследует chain).
    by_dir: dict[tuple[str, str], SourceFile] = {}
    by_name: dict[str, dict] = {}
    for s in sources:
        if s.kind != "yaml":
            continue
        parts = s.rel.replace("\\", "/").rsplit("/", 1)
        directory = parts[0] if len(parts) == 2 else ""
        by_dir[(directory, parts[-1])] = s
        data, err = _parsed(s)
        if err is None and isinstance(data, dict) and isinstance(data.get("Имя"), str):
            by_name[data["Имя"]] = data

    for source in sources:
        if source.kind != "xbsl":
            continue
        module, errors = P.parse(source)
        if errors:
            continue  # a broken file has its own diagnostics (code/parse-error)
        if any("::" in i.name for i in module.imports):
            # an import of an external namespace (a library): its contents are not
            # visible to the rule, any bare name may come from there - skip the file
            continue
        scope = set(known_global)
        pair = _yaml_pair(source, by_dir)
        if pair is not None:
            data, err = _parsed(pair)
            if err is None and isinstance(data, dict):
                imports = data.get("Импорт")
                if isinstance(imports, list) and any(
                    isinstance(i, str) and "::" in i for i in imports
                ):
                    continue  # an external namespace in the yaml Импорт - the same blind spot
                kind = data.get("ВидЭлемента")
                if source.rel.endswith(".Объект.xbsl"):
                    # an entity module: the attributes plus the standard fields and write methods
                    scope |= _section_names(data) | _ENTITY_COMMON
                elif kind == "КомпонентИнтерфейса":
                    scope |= _component_scope(data, by_name, type_members, set())
                else:
                    # a data-kind manager module / common module: the yaml fields plus the manager members
                    scope |= _section_names(data)
                    scope |= set(object_members.get(kind, ()))
                    scope |= set(manager_members.get(kind, ()))
        yield from _check_module(source, module, scope)


def _check_module(source: SourceFile, module: P.Module, known_global: set[str]) -> Iterable[Diagnostic]:
    module_names: set[str] = set(known_global)
    for m in module.members:
        if isinstance(m, (P.Method, P.Structure, P.Enum, P.ObjectField)):
            module_names.add(m.name)
    lm = linemap(source)
    findings: list[tuple[int, str, str | None]] = []
    for m in module.members:
        if isinstance(m, P.Method):
            scope = set(module_names) | {p.name for p in m.params}
            for p in m.params:
                if p.default is not None:
                    _walk_expr(p.default, scope, findings)
            _walk_body(m.body, set(scope), findings)
        elif isinstance(m, P.ObjectField) and m.init is not None:
            _walk_expr(m.init, set(module_names), findings)
        elif isinstance(m, (P.Structure, P.Enum)):
            inner = set(module_names) | {
                f.name for f in m.members if isinstance(f, P.ObjectField)
            } if isinstance(m, P.Structure) else set(module_names)
            members = m.members if isinstance(m, P.Structure) else m.methods
            for sub in members:
                if isinstance(sub, P.Method):
                    sub_scope = set(inner) | {p.name for p in sub.params} | {"этот"}
                    _walk_body(sub.body, sub_scope, findings)
                elif isinstance(sub, P.ObjectField) and sub.init is not None:
                    _walk_expr(sub.init, set(inner), findings)
    for offset, name, hint in findings:
        line, col = lm.linecol(offset)
        message = (
            i18n.t("code/undefined-name.found-hint", name=name, hint=hint)
            if hint else i18n.t("code/undefined-name.found", name=name)
        )
        yield Diagnostic(source.rel, line, col, "code/undefined-name", Severity.ERROR, message)


def _walk_body(stmts: list[P.Stmt], scope: set[str], findings: list) -> None:
    """A block body: statements in order, a declaration introduces its name AFTER its expression."""
    for st in stmts:
        if isinstance(st, P.VarDecl):
            if st.init is not None:
                _walk_expr(st.init, scope, findings)
            scope.add(st.name)
        elif isinstance(st, P.Assign):
            _walk_expr(st.target, scope, findings)
            if st.value is not None:
                _walk_expr(st.value, scope, findings)
        elif isinstance(st, P.ExprStmt):
            _walk_expr(st.expr, scope, findings)
        elif isinstance(st, P.UseStmt):
            _walk_expr(st.expr, scope, findings)
        elif isinstance(st, P.If):
            for cond, body in st.branches:
                _walk_expr(cond, scope, findings)
                _walk_body(body, set(scope), findings)
            if st.else_body is not None:
                _walk_body(st.else_body, set(scope), findings)
        elif isinstance(st, P.Case):
            if st.subject is not None:
                _walk_expr(st.subject, scope, findings)
            for when in st.whens:
                for cond in when.conditions:
                    _walk_expr(cond, scope, findings)
                _walk_body(when.body, set(scope), findings)
            if st.else_body is not None:
                _walk_body(st.else_body, set(scope), findings)
        elif isinstance(st, P.While):
            _walk_expr(st.cond, scope, findings)
            _walk_body(st.body, set(scope), findings)
        elif isinstance(st, P.ForEach):
            _walk_expr(st.source, scope, findings)
            inner = set(scope)
            inner.add(st.var)
            _walk_body(st.body, inner, findings)
        elif isinstance(st, P.ForTo):
            _walk_expr(st.start_expr, scope, findings)
            _walk_expr(st.to, scope, findings)
            if st.step is not None:
                _walk_expr(st.step, scope, findings)
            inner = set(scope)
            inner.add(st.var)
            _walk_body(st.body, inner, findings)
        elif isinstance(st, P.Try):
            _walk_body(st.body, set(scope), findings)
            for var, _type, body in st.catches:
                inner = set(scope)
                if var:
                    inner.add(var)
                _walk_body(body, inner, findings)
            if st.finally_body is not None:
                _walk_body(st.finally_body, set(scope), findings)
        elif isinstance(st, P.Scope):
            _walk_body(st.body, set(scope), findings)
        elif isinstance(st, P.Return):
            if st.value is not None:
                _walk_expr(st.value, scope, findings)


def _walk_expr(expr: P.Expr | None, scope: set[str], findings: list) -> None:
    if expr is None:
        return
    if isinstance(expr, P.Name):
        # Qualified roots (Подсистема::Имя) are not checked: the contents of foreign
        # namespaces are not visible to this rule.
        if "::" not in expr.name and expr.name and expr.name not in scope:
            hint = _closest(expr.name, scope)
            findings.append((expr.start, expr.name, hint))
        return
    if isinstance(expr, P.Member):
        _walk_expr(expr.obj, scope, findings)  # the member name is a type-inference stage
        return
    if isinstance(expr, P.Call):
        _walk_expr(expr.callee, scope, findings)
        for arg in expr.args:
            _walk_expr(arg.value, scope, findings)
        return
    if isinstance(expr, P.Lambda):
        if expr.body_expr is not None or expr.body_stmts is not None:
            inner = set(scope) | {p.name for p in expr.params}
            if isinstance(expr.body_expr, P.Expr):
                _walk_expr(expr.body_expr, inner, findings)
            if expr.body_stmts is not None:
                _walk_body(expr.body_stmts, inner, findings)
        return
    if isinstance(expr, P.Index):
        _walk_expr(expr.obj, scope, findings)
        _walk_expr(expr.index, scope, findings)
        return
    if isinstance(expr, P.Binary):
        _walk_expr(expr.left, scope, findings)
        _walk_expr(expr.right, scope, findings)
        return
    if isinstance(expr, P.Compare):
        _walk_expr(expr.first, scope, findings)
        for _op, right in expr.rest:
            _walk_expr(right, scope, findings)
        return
    if isinstance(expr, P.Unary):
        _walk_expr(expr.operand, scope, findings)
        return
    if isinstance(expr, (P.IsType, P.AsType)):
        _walk_expr(expr.operand, scope, findings)
        return
    if isinstance(expr, P.Ternary):
        _walk_expr(expr.cond, scope, findings)
        _walk_expr(expr.then, scope, findings)
        _walk_expr(expr.otherwise, scope, findings)
        return
    if isinstance(expr, P.Coalesce):
        _walk_expr(expr.left, scope, findings)
        _walk_expr(expr.right, scope, findings)
        return
    if isinstance(expr, P.NonNull):
        _walk_expr(expr.operand, scope, findings)
        return
    if isinstance(expr, P.New):
        if expr.args:
            for arg in expr.args:
                _walk_expr(arg.value, scope, findings)
        return
    if isinstance(expr, P.ArrayLit):
        for item in expr.items:
            _walk_expr(item, scope, findings)
        return
    if isinstance(expr, P.MapLit):
        for key, value in expr.entries:
            _walk_expr(key, scope, findings)
            _walk_expr(value, scope, findings)
        return
    if isinstance(expr, P.Throw):
        _walk_expr(expr.value, scope, findings)
        return
    # Literal, This, GlobalAccess, MethodRef are atoms (method references - stage 3)


def _closest(name: str, scope: set[str]) -> str | None:
    hits = difflib.get_close_matches(name, scope, n=1, cutoff=0.75)
    return hits[0] if hits else None
