"""Tier D: cross-component calls must target methods visible outside their module.

The code/local-method-cross-component rule: a method of an interface component is
@Локально by default – a call `Компоненты.X.Метод(...)` from ANOTHER component's module
fails at runtime with "Method is invisible due to visibility modifier @Локально" unless
the method carries a visibility annotation wider than local: @ВПодсистеме, @ВПроекте,
@ВТипе or @Глобально (docs: Стд::Аннотации::ОбластиВидимости, topic "Модульная
разработка" – @Локально is the default for language constructs).

The real-corpus pattern the rule encodes: every cross-component call targets a method
annotated @ВПодсистеме (a router page-switch is the reference shape –
`Компоненты.ПросмотрКонтента.Загрузить(...)`); every other `Компоненты.X.Y(...)` call
hits a form-local instance (an HTML container, a table) whose X is not a project
component, so those are skipped by construction. Yaml bindings (`=Компоненты...`)
reference form-local tables and platform built-ins only, never project components –
bindings are not checked.

Zero-false-positive guards:

- only CALLS are checked (the member name is followed by `(`); reads and writes of
  properties are left alone;
- the caller must be the paired module of a КомпонентИнтерфейса yaml, and that yaml
  must embed the component under the same instance name (a node with `Имя: X` and
  `Тип: X`) – this rules out a same-name instance of a different type;
- X must be a project КомпонентИнтерфейса with a paired module `X.xbsl`, and the called
  name must be found among the methods declared in that module – platform built-ins on
  component instances (ПодключитьОбработчикТаймера, ВызватьМетод...) are not declared
  there and are skipped;
- a module where the name `Компоненты` is shadowed (declared, assigned, annotated or
  bound by a lambda parameter) is skipped entirely for the rule;
- comments and `Запрос{...}` blocks are excluded via code_tokens; a root preceded by
  `.` is a member of another object, not the components collection;
- the component's own module is never checked against itself (visibility does not
  restrict calls inside one module).

The diagnostic is reported at the CALL site: that is where the runtime error surfaces
and where the drift is introduced; the fix (the annotation on the declaration) lives in
the other file and is named in the message. The rule is project-wide: it needs the
target component's yaml and module next to the caller.
"""

from __future__ import annotations

from collections.abc import Iterable

from xbsl import i18n
from xbsl.diagnostics import Diagnostic, Severity
from xbsl.engine import SourceFile, rule
from xbsl.rules._syntax import code_tokens
from xbsl.rules.yaml_schema import _HAVE_YAML, _parsed

MESSAGES = {
    "code/local-method-cross-component.title": {
        "ru": "Кросс-компонентный вызов локального метода",
        "en": "Cross-component call of a local method",
    },
    "code/local-method-cross-component.invisible": {
        "ru": "Метод '{method}' компонента '{comp}' виден только в своём модуле "
              "(@Локально по умолчанию) – вызов из другого компонента упадёт в рантайме. "
              "Пометьте метод в {module} аннотацией @ВПодсистеме или шире.",
        "en": "Method '{method}' of component '{comp}' is only visible inside its module "
              "(@Локально by default) – the call from another component fails at runtime. "
              "Mark the method in {module} with @ВПодсистеме or a wider visibility.",
    },
}
i18n.register(MESSAGES)

# The visibility-scope annotations (Стд::Аннотации::ОбластиВидимости). Anything from
# _WIDE makes the method callable from another component's module; @ВТипе is counted as
# wide too – the docs describe it as visible "в данном типе, его наследниках и внешних
# объектах", so treating it as local could produce false positives.
_VISIBILITY = frozenset({"Локально", "ВПодсистеме", "ВПроекте", "ВТипе", "Глобально"})
_WIDE = _VISIBILITY - {"Локально"}

# Declaration keywords that bind a name (shadowing the components collection).
_DECL_KW = ("VAL", "VAR", "CONST", "REQ", "CATCH", "FOR")


def _annotations_before(toks: list, i: int) -> set[str]:
    """Names of the annotations directly above the method keyword at index i.

    Walks backwards over `@Имя` pairs (annotation arguments in parentheses are skipped
    by bracket balance) and over the `статический` keyword; any other token ends the
    annotation block.
    """
    names: set[str] = set()
    j = i - 1
    if j >= 0 and toks[j].kind == "KEYWORD" and toks[j].canonical == "STATIC":
        j -= 1
    while j >= 0:
        t = toks[j]
        if t.kind == "OP" and t.value == ")":
            depth = 0
            while j >= 0:
                if toks[j].kind == "OP" and toks[j].value == ")":
                    depth += 1
                elif toks[j].kind == "OP" and toks[j].value == "(":
                    depth -= 1
                    if depth == 0:
                        break
                j -= 1
            j -= 1
            continue
        if t.kind == "IDENT" and j >= 1 and toks[j - 1].kind == "OP" and toks[j - 1].value == "@":
            names.add(t.value)
            j -= 2
            continue
        break
    return names


def _method_visibility(module: SourceFile) -> dict[str, set[str]]:
    """Module method name -> the annotation names above its declaration (cached on the file)."""
    cached = module.cache.get("local_visibility_methods")
    if cached is not None:
        return cached
    toks = code_tokens(module)
    n = len(toks)
    result: dict[str, set[str]] = {}
    for i, t in enumerate(toks):
        if t.kind != "KEYWORD" or t.canonical != "METHOD" or not t.value[:1].islower():
            continue
        if i + 1 < n and toks[i + 1].kind == "IDENT":
            result[toks[i + 1].value] = _annotations_before(toks, i)
    module.cache["local_visibility_methods"] = result
    return result


def _shadows(toks: list, name: str) -> bool:
    """The module binds the name somewhere: a declaration, an assignment, an annotation.

    Wider than necessary on purpose – a shadowed name only makes the rule skip.
    """
    n = len(toks)
    for i, t in enumerate(toks):
        if t.kind == "KEYWORD" and t.value[:1].islower() and t.canonical in _DECL_KW:
            for j in range(i + 1, min(i + 3, n)):
                if toks[j].kind == "IDENT":
                    if toks[j].value == name:
                        return True
                    break
        elif t.kind == "IDENT" and t.value == name and i + 1 < n and toks[i + 1].kind == "OP":
            # `Объект.Компоненты = ...` is a member of another object, not the collection
            member = i > 0 and toks[i - 1].kind == "OP" and toks[i - 1].value == "."
            if not member and toks[i + 1].value in ("=", ":", "->"):
                return True
    return False


def _instance_types(node, out: dict[str, set[str]]) -> None:
    """Collect `Имя -> {Тип}` pairs from the parsed yaml tree (component placements)."""
    if isinstance(node, dict):
        nm, tp = node.get("Имя"), node.get("Тип")
        if isinstance(nm, str) and isinstance(tp, str):
            out.setdefault(nm, set()).add(tp)
        for v in node.values():
            _instance_types(v, out)
    elif isinstance(node, list):
        for item in node:
            _instance_types(item, out)


def _pair_stem(rel: str) -> str:
    slash = rel.replace("\\", "/")
    return slash[: slash.rfind(".")] if "." in slash.rsplit("/", 1)[-1] else slash


def _cross_component_mapper(source: SourceFile) -> dict | None:
    """The map phase. The yaml of an interface component contributes its name and the
    embedded instances; a module contributes its method visibility and its
    `Компоненты.X.Y(...)` calls with the local skips settled. The reduce joins the
    caller's pair, resolves X to the component's module and checks the visibility."""
    if not _HAVE_YAML:
        return None
    if source.kind == "yaml":
        data, err = _parsed(source)
        if err is not None or not isinstance(data, dict):
            return None
        if data.get("ВидЭлемента") != "КомпонентИнтерфейса":
            return None
        name = data.get("Имя")
        instances: dict[str, set[str]] = {}
        _instance_types(data, instances)
        return {
            "k": "y",
            "stem": _pair_stem(source.rel),
            "name": name if isinstance(name, str) else None,
            "instances": {inst: sorted(types) for inst, types in instances.items()},
        }
    if source.kind != "xbsl":
        return None
    toks = code_tokens(source)
    visibility = {
        name: sorted(anns) for name, anns in _method_visibility(source).items()
    }
    calls: list[tuple[str, str, int, int]] = []
    if not _shadows(toks, "Компоненты"):
        owner = source.path.name[: -len(".xbsl")].split(".", 1)[0]
        n = len(toks)
        for i, t in enumerate(toks):
            if t.kind != "IDENT" or t.value != "Компоненты" or i + 5 >= n:
                continue
            if i > 0 and toks[i - 1].kind == "OP" and toks[i - 1].value == ".":
                continue  # member of another object, not the components collection
            if not (toks[i + 1].kind == "OP" and toks[i + 1].value == "."
                    and toks[i + 2].kind == "IDENT"
                    and toks[i + 3].kind == "OP" and toks[i + 3].value == "."
                    and toks[i + 4].kind == "IDENT"
                    and toks[i + 5].kind == "OP" and toks[i + 5].value == "("):
                continue  # not a call Компоненты.X.Y(...)
            comp, meth = toks[i + 2], toks[i + 4]
            if comp.value == owner:
                continue  # the component's own module – locality never restricts it
            calls.append((comp.value, meth.value, meth.line, meth.col))
    if not visibility and not calls:
        return None
    return {
        "k": "x",
        "stem": _pair_stem(source.rel),
        "file": source.path.name,
        "visibility": visibility,
        "calls": calls,
    }


@rule(
    "code/local-method-cross-component", "code/local-method-cross-component.title", "D",
    scope="project", severity=Severity.WARNING, mapper=_cross_component_mapper,
)
def local_method_cross_component(facts: dict[str, dict]) -> Iterable[Diagnostic]:
    # Component name -> the stem of its paired module; caller stem -> its instances.
    comp_stems: dict[str, str] = {}
    instances_by_stem: dict[str, dict[str, list[str]]] = {}
    module_facts: dict[str, dict] = {}
    for fact in facts.values():
        if fact["k"] == "y":
            instances_by_stem[fact["stem"]] = fact["instances"]
            if fact["name"]:
                comp_stems[fact["name"]] = fact["stem"]
    for fact in facts.values():
        if fact["k"] == "x":
            module_facts[fact["stem"]] = fact
    if not comp_stems:
        return
    for rel, fact in facts.items():
        if fact["k"] != "x" or not fact["calls"]:
            continue
        instances = instances_by_stem.get(fact["stem"])
        if instances is None:
            continue  # not an interface component module – no components collection
        for comp, meth, line, col in fact["calls"]:
            target_stem = comp_stems.get(comp)
            if target_stem is None or target_stem == fact["stem"]:
                continue  # X is not a project component with a paired module
            target = module_facts.get(target_stem)
            if target is None:
                continue
            if instances.get(comp) != [comp]:
                continue  # the form embeds no instance X of type X – ambiguous, skip
            annotations = target["visibility"].get(meth)
            if annotations is None:
                continue  # not declared in the module – a platform built-in, skip
            if set(annotations) & _WIDE:
                continue
            yield Diagnostic(
                rel, line, col, "code/local-method-cross-component",
                Severity.WARNING,
                i18n.t(
                    "code/local-method-cross-component.invisible",
                    method=meth, comp=comp, module=target["file"],
                ),
            )
