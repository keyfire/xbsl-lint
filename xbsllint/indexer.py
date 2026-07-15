"""Индекс проекта для навигации в редакторе (флаг CLI --index).

`xbsllint --index <root>` печатает в stdout JSON-снимок проекта: объекты (вид, табличные
части, локальные типы, объявленные в модулях, порождённое семейство членов, значения
перечислений), объявления методов каждого модуля (вместе с их аннотациями) и именованные
компоненты интерфейса форм. Редакторы используют индекс для перехода к определению и
автодополнения.

Форма индекса зафиксирована (поля можно добавлять, но не переименовывать):

    meta       – {root: абсолютный путь в POSIX-виде, version: версия линтера};
    objects    – элементы yaml с ВидЭлемента: name/kind/path/line, табличные части,
                 локальные типы модулей объекта (`<Имя>.xbsl`, `<Имя>.<Часть>.xbsl`),
                 семейство членов для автодополнения по точке, значения перечисления
                 (только Перечисление);
    methods    – объявления методов и конструкторов всех модулей, аннотации без `@`;
    components – узлы yaml для КомпонентИнтерфейса, у которых есть и Имя, и Тип;
    references – использования индексируемых имён (объектов, методов, компонентов) в модулях
                 и в yaml-обработчиках: name/qualifier/module/path/line/col – для "найти
                 использования" (разрешение конкретной цели по этому списку – в навигационном ядре).

Пути записаны в POSIX-виде и относительно meta.root; строки нумеруются с единицы (ключ
`Имя` объекта в yaml, объявление метода или структуры, элемент перечисления, узел
компонента). Позиции в yaml находятся текстовым поиском по исходному тексту (парсер
позиций не хранит, см. _value_positions в yaml_types.py); ненайденная позиция вырождается
в строку 1 – построение индекса на этом никогда не падает.
"""

from __future__ import annotations

import re
from collections import defaultdict, deque
from pathlib import Path

from xbsllint import __version__
from xbsllint.engine import SourceFile, find_sources, load
from xbsllint.lexer import linemap, tokens
from xbsllint.rules.semantics import _file_local_type_decls, _member_family
from xbsllint.rules.yaml_schema import _HAVE_YAML, _parsed

# Строка с ключом `Имя:`: отступ (дефис элемента списка тоже считается отступом), значение
# в кавычках или без них, необязательный хвостовой комментарий; `\r?` позволяет совпадать
# файлам с CRLF (`$` привязан к позиции перед `\n`).
_NAME_LINE_RE = re.compile(
    r"(?m)^([ \t]*(?:-[ \t]+)?)Имя:[ \t]*(['\"]?)([^\r\n#]*?)\2[ \t]*(?:#.*)?\r?$"
)


# --- позиции в yaml (текстовый поиск, как в _value_positions из yaml_types.py) ---------

def _name_entries(s: SourceFile) -> list[tuple[int, int, str]]:
    """(смещение, отступ, значение) каждой строки с ключом `Имя:` файла, в порядке документа."""
    cached = s.cache.get("index-name-entries")
    if cached is None:
        cached = [
            (m.start(), len(m.group(1)), m.group(3))
            for m in _NAME_LINE_RE.finditer(s.text)
        ]
        s.cache["index-name-entries"] = cached
    return cached


def _top_name_line(s: SourceFile, name: str) -> int:
    """Строка ключа `Имя:` верхнего уровня у объекта (1, если ключ не найден)."""
    for off, indent, value in _name_entries(s):
        if indent == 0 and value == name:
            return linemap(s).linecol(off)[0]
    return 1


def _section_span(text: str, key: str) -> tuple[int, int] | None:
    """Смещения тела секции верхнего уровня (`ТабличныеЧасти:` ... следующий ключ того же уровня)."""
    m = re.search(rf"(?m)^{key}:[ \t]*\r?$", text)
    if m is None:
        return None
    end = re.compile(r"(?m)^[^\s#-]").search(text, m.end())
    return m.end(), end.start() if end else len(text)


def _section_item_lines(s: SourceFile, key: str) -> dict[str, deque[int]]:
    """По имени элемента: строки ключей `Имя:` уровня элемента в секции верхнего уровня.

    Ключи уровня элемента – это ключи с минимальным отступом внутри секции; `Имя` вложенного
    реквизита лежит глубже и в выборку не попадает. Очереди хранят одноимённые элементы в
    порядке документа; вызывающий код забирает по одной строке на каждый разобранный элемент.
    """
    span = _section_span(s.text, key)
    if span is None:
        return {}
    lo, hi = span
    inside = [(off, indent, value) for off, indent, value in _name_entries(s) if lo <= off < hi]
    if not inside:
        return {}
    level = min(indent for _, indent, _ in inside)
    lm = linemap(s)
    queues: dict[str, deque[int]] = defaultdict(deque)
    for off, indent, value in inside:
        if indent == level:
            queues[value].append(lm.linecol(off)[0])
    return queues


def _named_items(s: SourceFile, data: dict, key: str) -> list[dict]:
    """{name, line} именованных элементов секции-списка верхнего уровня (ТабличныеЧасти/Элементы)."""
    items = data.get(key)
    if not isinstance(items, list):
        return []
    queues = _section_item_lines(s, key)
    out: list[dict] = []
    for item in items:
        if isinstance(item, dict) and isinstance(item.get("Имя"), str):
            name = item["Имя"]
            q = queues.get(name)
            out.append({"name": name, "line": q.popleft() if q else 1})
    return out


# --- объявления в модулях (по токенам) -------------------------------------------------

def _annotations_before(toks: list, i: int) -> list[str]:
    """Имена аннотаций над ключевым словом объявления с индексом i, в порядке текста, без `@`.

    Обход идёт назад по парам `@Имя` и `@Имя(...)` (комментарии между ними пропускаются,
    скобки аргументов балансируются); первый не подходящий токен останавливает обход.
    """
    names: list[str] = []
    k = i - 1
    while k >= 0:
        while k >= 0 and toks[k].kind == "COMMENT":
            k -= 1
        if k >= 0 and toks[k].kind == "OP" and toks[k].value == ")":
            depth = 1
            k -= 1
            while k >= 0 and depth:
                if toks[k].kind == "OP":
                    if toks[k].value == ")":
                        depth += 1
                    elif toks[k].value == "(":
                        depth -= 1
                k -= 1
            while k >= 0 and toks[k].kind == "COMMENT":
                k -= 1
        if (
            k >= 1
            and toks[k].kind == "IDENT"
            and toks[k - 1].kind == "OP"
            and toks[k - 1].value == "@"
        ):
            names.append(toks[k].value)
            k -= 2
            continue
        break
    names.reverse()
    return names


def _method_decls(s: SourceFile) -> list[dict]:
    """{name, line, annotations} объявлений методов и конструкторов одного модуля."""
    decls: list[dict] = []
    toks = tokens(s)
    n = len(toks)
    for i, t in enumerate(toks):
        if t.kind != "KEYWORD" or t.canonical not in ("METHOD", "CONSTRUCTOR"):
            continue
        if not t.value[:1].islower():
            continue  # ключевое слово объявления пишется строчными (как в правиле handlers)
        j = i + 1
        while j < n and toks[j].kind == "COMMENT":
            j += 1
        if j < n and toks[j].kind == "IDENT":
            decls.append({
                "name": toks[j].value,
                "line": toks[j].line,
                "annotations": _annotations_before(toks, i),
            })
    return decls


# --- ссылки (использования) для навигации "найти использования" ------------------------

def _prev_significant(toks: list, i: int) -> int:
    """Индекс ближайшего значимого токена слева от i (комментарии пропускаются), или -1."""
    j = i - 1
    while j >= 0 and toks[j].kind == "COMMENT":
        j -= 1
    return j


def _next_significant(toks: list, i: int, n: int) -> int:
    """Индекс ближайшего значимого токена справа от i (комментарии пропускаются), или n."""
    j = i + 1
    while j < n and toks[j].kind == "COMMENT":
        j += 1
    return j


def _module_references(s: SourceFile, referable: set[str], module: str, path: str) -> list[dict]:
    """Использования индексируемых имён в модуле .xbsl: вызовы, обращения к члену, корни цепочек.

    Для каждого токена-идентификатора со значением из referable, который является вызовом
    (перед `(`), обращением к члену (после `.`) или корнем цепочки (перед `.`), пишем
    {name, qualifier, module, path, line, col}: qualifier – идентификатор перед точкой (иначе "").
    Имя в объявлении метода/конструктора пропускаем – это определение, а не использование;
    имя аннотации (после `@`) ссылкой не считаем. Позиции: line 1-based, col 0-based (для редактора).
    """
    refs: list[dict] = []
    toks = tokens(s)
    n = len(toks)
    for i, t in enumerate(toks):
        if t.kind != "IDENT" or t.value not in referable:
            continue
        p = _prev_significant(toks, i)
        f = _next_significant(toks, i, n)
        prev = toks[p] if p >= 0 else None
        nxt = toks[f] if f < n else None
        if prev is not None and prev.kind == "OP" and prev.value == "@":
            continue  # имя аннотации, не ссылка
        if prev is not None and prev.kind == "KEYWORD" and prev.canonical in ("METHOD", "CONSTRUCTOR"):
            continue  # объявление метода/конструктора – это определение
        after_dot = prev is not None and prev.kind == "OP" and prev.value == "."
        before_dot = nxt is not None and nxt.kind == "OP" and nxt.value == "."
        is_call = nxt is not None and nxt.kind == "OP" and nxt.value == "("
        if not (after_dot or before_dot or is_call):
            continue
        qualifier = ""
        if after_dot:
            q = _prev_significant(toks, p)
            if q >= 0 and toks[q].kind == "IDENT":
                qualifier = toks[q].value
        refs.append({
            "name": t.value,
            "qualifier": qualifier,
            "module": module,
            "path": path,
            "line": t.line,
            "col": t.col - 1,
        })
    return refs


# Строка обработчика в yaml: `Обработчик: ИмяМетода` – значение указывает на метод парного модуля.
_HANDLER_REF_RE = re.compile(
    r"(?m)^[ \t]*Обработчик:[ \t]*(['\"]?)([A-Za-zА-Яа-яЁё_][A-Za-z0-9А-Яа-яЁё_]*)\1[ \t]*(?:#.*)?\r?$"
)


def _handler_references(s: SourceFile, module: str, path: str) -> list[dict]:
    """Использования методов через `Обработчик:` в yaml (метод парного модуля формы/объекта)."""
    refs: list[dict] = []
    lm = linemap(s)
    for m in _HANDLER_REF_RE.finditer(s.text):
        line, col = lm.linecol(m.start(2))
        refs.append({
            "name": m.group(2),
            "qualifier": "",
            "module": module,
            "path": path,
            "line": line,
            "col": col - 1,
        })
    return refs


# --- компоненты форм ----------------------------------------------------------------------

def _component_nodes(node) -> list[tuple[str, str]]:
    """(Имя, Тип) каждого узла yaml, где есть оба ключа; обход в глубину в порядке документа."""
    found: list[tuple[str, str]] = []
    if isinstance(node, dict):
        name, typ = node.get("Имя"), node.get("Тип")
        if isinstance(name, str) and isinstance(typ, str):
            found.append((name, typ))
        for value in node.values():
            found.extend(_component_nodes(value))
    elif isinstance(node, list):
        for item in node:
            found.extend(_component_nodes(item))
    return found


def _form_components(s: SourceFile, data: dict, form: str, path: str) -> list[dict]:
    """Именованные компоненты одной формы вместе со строками их ключей `Имя:`."""
    lm = linemap(s)
    queues: dict[str, deque[int]] = defaultdict(deque)
    for off, indent, value in _name_entries(s):
        if indent > 0:  # Имя верхнего уровня – это сама форма, а не компонент
            queues[value].append(lm.linecol(off)[0])
    out: list[dict] = []
    for name, typ in _component_nodes(data):
        q = queues.get(name)
        out.append({
            "form": form,
            "name": name,
            "type": typ,
            "path": path,
            "line": q.popleft() if q else 1,
        })
    return out


# --- индекс -------------------------------------------------------------------------------

def _discover(root: Path) -> list[Path]:
    """Файлы исходников под корнем (или сам корень, если это файл), отсортированные."""
    if root.is_file():
        return [root] if root.suffix in (".xbsl", ".yaml") else []
    return find_sources(root, "*.yaml") + find_sources(root, "*.xbsl")


def build_index(root: Path) -> dict:
    """Готовый к выводу в JSON индекс проекта под корнем root (см. докстринг модуля)."""
    base = (root if root.is_dir() else root.parent).resolve()
    sources = [load(p) for p in _discover(root)]
    yaml_sources = [s for s in sources if s.kind == "yaml"]
    xbsl_sources = [s for s in sources if s.kind == "xbsl"]

    def rel(p: Path) -> str:
        rp = p.resolve()
        try:
            return rp.relative_to(base).as_posix()
        except ValueError:
            return rp.as_posix()

    # Локальные типы по объекту-владельцу: файлы модулей `<Имя>.xbsl` и `<Имя>.<Часть>.xbsl`
    # (сопоставление по имени, по инварианту "имя в yaml совпадает с именем файла" – как в
    # _project_object_info).
    local_types: dict[str, list[dict]] = defaultdict(list)
    for s in xbsl_sources:
        owner = s.path.name[: -len(".xbsl")].split(".", 1)[0]
        module_path = rel(s.path)
        for name, line in _file_local_type_decls(s):
            local_types[owner].append({"name": name, "path": module_path, "line": line})

    objects: list[dict] = []
    components: list[dict] = []
    if _HAVE_YAML:
        for s in yaml_sources:
            data, err = _parsed(s)
            if err is not None or not isinstance(data, dict):
                continue
            name, kind = data.get("Имя"), data.get("ВидЭлемента")
            if not isinstance(name, str) or not isinstance(kind, str):
                continue
            entry: dict = {
                "name": name,
                "kind": kind,
                "path": rel(s.path),
                "line": _top_name_line(s, name),
                "tabular": _named_items(s, data, "ТабличныеЧасти"),
                "attributes": _named_items(s, data, "Реквизиты"),
                "local_types": local_types.get(name, []),
            }
            entry["family"] = sorted(
                set(_member_family(kind))
                | {t["name"] for t in entry["tabular"]}
                | {t["name"] for t in entry["local_types"]}
            )
            if kind == "Перечисление":
                entry["values"] = _named_items(s, data, "Элементы")
            objects.append(entry)
            if kind == "КомпонентИнтерфейса":
                components.extend(_form_components(s, data, name, entry["path"]))

    methods: list[dict] = []
    for s in xbsl_sources:
        module = s.path.name[: -len(".xbsl")]
        module_path = rel(s.path)
        for decl in _method_decls(s):
            methods.append({
                "module": module,
                "name": decl["name"],
                "path": module_path,
                "line": decl["line"],
                "annotations": decl["annotations"],
            })

    # Использования (для "найти использования"): имена объектов, компонентов и методов, встреченные
    # как вызов/член/корень цепочки в модулях, плюс методы в yaml-обработчиках. Разрешение конкретной
    # цели (метод модуля X, объект, компонент формы) выполняет навигационное ядро по этому списку.
    referable = (
        {o["name"] for o in objects}
        | {c["name"] for c in components}
        | {m["name"] for m in methods}
    )
    references: list[dict] = []
    for s in xbsl_sources:
        module = s.path.name[: -len(".xbsl")]
        references.extend(_module_references(s, referable, module, rel(s.path)))
    for s in yaml_sources:
        references.extend(_handler_references(s, s.path.stem, rel(s.path)))

    return {
        "meta": {"root": base.as_posix(), "version": __version__},
        "objects": objects,
        "methods": methods,
        "components": components,
        "references": references,
    }
