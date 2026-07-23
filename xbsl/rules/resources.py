"""Resources addressed by `Ресурс{...}`: the shape of the name and its existence.

Two rules live here:

- code/resource-bare-name (tier C, file) – the name carries a folder;
- code/unknown-resource (tier D, project) – the name is nowhere to be found.

The code/resource-bare-name rule. A resource lives in a `Ресурсы` folder of a subsystem, but
the platform resolves it by file name alone: spelling the folder out the way it lies on disk
is rejected when the build is applied. Measured on a probe applied to a local server, with a
control in the same project:

    ПробаРесурсов.xbsl [10:20]: Неизвестный ресурс: 'Ресурсы/Проба.svg'
    (the same file addressed as `Ресурс{Проба.svg}` applied cleanly)

Positions match the compiler's: both point at the first character inside the braces.

The `inbase/` prefix is NOT a folder: it addresses a resource uploaded into the application
base (the web editor names them by uuid - `Ресурс{inbase/<uuid>.png}` in deployed code).
Probed on the local server next to the same controls: a DANGLING uuid fails with the very
message a missing bare name gets ('Неизвестный ресурс: inbase/...', the position on the
first character inside the braces) - a lookup that found nothing, not a rejected spelling -
while the deployed code whose uuid exists in ITS base applies cleanly. Both rules leave the
form alone: the spelling is legal, and whether the uuid exists is a fact of the application
base no static check can see - the compiler verifies it at apply.

The code/unknown-resource rule. A name that resolves to nothing is rejected the same way
(`Неизвестный ресурс: 'НетТакого.svg'` on the probe), but "exists" means more than "lies in
the project": the platform ships an image library of its own, and code may use it without any
file in the project. That nearly cost a rule full of false positives - a corpus survey found
five such names in a deployed project (Настройки.svg, Время.svg, Скачать.svg, Ссылка2.svg,
ГалочкаВКруге.svg), and a project-only check would have called all five errors. The probe
settled it: `Ресурс{Настройки.svg}` compiles in a project with no such file, while
`Ресурс{Настройки3.svg}` right next to it fails.

So the known set is the union of two sources: every file under the project's `Ресурсы` folders
(the project root is the folder holding `Проект.yaml`) and the 152 names of the platform's
image library, taken from the documentation page `topics/image-library` – the first source of
truth, not a hand-written list. A qualified name (`Стд::Грузовик.svg`, the form the docs show)
is stripped of its namespace before the lookup. Without the documentation data the rule stays
silent: guessing without the library is exactly what produces the five false positives. A name
carrying a folder is left to code/resource-bare-name, so one mistake is not reported twice.

The union spans the projects of the run – a resource of a foreign subsystem is never reported,
which is deliberate: whether the compiler resolves across subsystems is untested, and a wider
set can only silence the rule, never make it fire. Names are matched exactly: the platform's
lookup is case-sensitive while a Windows checkout is not.
"""

from __future__ import annotations

import re
from collections.abc import Iterable
from functools import lru_cache
from pathlib import Path

from xbsl import docs, i18n
from xbsl.diagnostics import Diagnostic, Severity
from xbsl.engine import SourceFile, rule
from xbsl.lexer import Token
from xbsl.rules._syntax import code_tokens

MESSAGES = {
    "code/resource-bare-name.title": {
        "ru": "Ресурс задан путём, а не именем файла",
        "en": "A resource addressed by a path, not a file name",
    },
    "code/unknown-resource.title": {
        "ru": "Неизвестный ресурс",
        "en": "Unknown resource",
    },
    "code/unknown-resource.unknown": {
        "ru": "Неизвестный ресурс '{name}' – его нет ни в каталогах 'Ресурсы' проекта, ни в "
              "библиотеке картинок платформы; применение сборки упадёт 'Неизвестный ресурс'.",
        "en": "Unknown resource '{name}' – neither in the project's 'Ресурсы' folders nor in "
              "the platform's image library; applying the build will fail with 'Неизвестный "
              "ресурс'.",
    },
    "code/resource-bare-name.path": {
        "ru": "Ресурс задаётся ГОЛЫМ именем файла: '{name}' содержит каталог, платформа такой "
              "путь не разрешает и применение сборки падает 'Неизвестный ресурс'. "
              "Правильно: 'Ресурс{{{base}}}'.",
        "en": "A resource is addressed by its BARE file name: '{name}' carries a folder, which "
              "the platform does not resolve - applying the build fails with 'Неизвестный "
              "ресурс'. Correct: 'Ресурс{{{base}}}'.",
    },
}
i18n.register(MESSAGES)

#: The folder name holding the resource files of a subsystem.
_RESOURCE_DIR = "Ресурсы"

#: The prefix of a resource uploaded into the application base (see the module docstring).
_UPLOADED_PREFIX = "inbase/"


def _resource_refs(toks: list[Token], text: str) -> Iterable[tuple[str, int, int]]:
    """(name inside the braces, line, column) for every `Ресурс{...}` of the module.

    Comments and string literals are already stripped by code_tokens, so a `Ресурс{}`
    mentioned in a comment cannot false-match. The name is taken from the source text
    between the braces, not glued back from tokens: a name may hold characters the lexer
    splits (`adv-auto.svg`) or spaces it drops.
    """
    for i, t in enumerate(toks):
        if t.kind != "IDENT" or t.value != "Ресурс" or i + 1 >= len(toks):
            continue
        opener = toks[i + 1]
        if opener.kind != "OP" or opener.value != "{":
            continue
        for closer in toks[i + 2:]:
            if closer.kind == "OP" and closer.value == "}":
                name = text[opener.end:closer.start].strip()
                if name:
                    yield name, opener.end_line, opener.end_col
                break
            if closer.line != opener.line:
                break  # an unclosed brace - leave it to the parser


@rule("code/resource-bare-name", "code/resource-bare-name.title", "C", severity=Severity.ERROR)
def resource_bare_name(source: SourceFile) -> Iterable[Diagnostic]:
    if source.kind != "xbsl" or "Ресурс{" not in source.text:
        return
    for name, line, col in _resource_refs(code_tokens(source), source.text):
        if name.startswith(_UPLOADED_PREFIX):
            continue  # a resource uploaded into the base - a lookup key, not a disk path
        base = name.replace("\\", "/").rsplit("/", 1)[-1]
        if base == name:
            continue
        yield Diagnostic(
            source.rel, line, col, "code/resource-bare-name", Severity.ERROR,
            i18n.t("code/resource-bare-name.path", name=name, base=base),
        )


#: The documentation page listing the platform's image library.
_IMAGE_LIBRARY_PAGE = "topics/image-library"
#: A resource file name as the page spells it.
_IMAGE_NAME_RE = re.compile(r"[A-Za-zА-Яа-яЁё0-9_]+\.svg")


@lru_cache(maxsize=1)
def _platform_images() -> frozenset[str]:
    """Names of the platform's image library, or an empty set without the docs data."""
    page = docs.page(_IMAGE_LIBRARY_PAGE)
    if not page:
        return frozenset()
    return frozenset(_IMAGE_NAME_RE.findall(page.get("html") or ""))


def _unknown_resource_mapper(source: SourceFile) -> dict | None:
    """The map phase: a Проект.yaml contributes its folder, a module its resource refs."""
    if source.kind == "yaml":
        if source.path.name == "Проект.yaml":
            return {"root": str(source.path.parent)}
        return None
    if source.kind != "xbsl" or "Ресурс{" not in source.text:
        return None
    refs = list(_resource_refs(code_tokens(source), source.text))
    return {"refs": refs} if refs else None


def _project_resources(roots: Iterable[str]) -> set[str]:
    """File names of every `Ресурсы` folder under the given project roots."""
    names: set[str] = set()
    for root in roots:
        for path in Path(root).rglob("*"):
            if path.is_file() and _RESOURCE_DIR in path.parts:
                names.add(path.name)
    return names


@rule(
    "code/unknown-resource", "code/unknown-resource.title", "D",
    scope="project", severity=Severity.ERROR, mapper=_unknown_resource_mapper,
)
def unknown_resource(facts: dict[str, dict]) -> Iterable[Diagnostic]:
    library = _platform_images()
    if not library:
        return  # no documentation data - the library is unknown, guessing would be wrong
    roots = {fact["root"] for fact in facts.values() if "root" in fact}
    if not roots:
        return  # no Проект.yaml in the run - nothing to compare against
    known = _project_resources(roots) | library
    for rel, fact in facts.items():
        for name, line, col in fact.get("refs", ()):
            if "/" in name or "\\" in name:
                # A folder path - code/resource-bare-name reports it; an uploaded-to-base
                # reference (inbase/...) is legal, and its existence lives in the base,
                # out of static reach either way.
                continue
            bare = name.rsplit("::", 1)[-1].strip()  # Стд::Грузовик.svg -> Грузовик.svg
            if bare in known:
                continue
            yield Diagnostic(
                rel, line, col, "code/unknown-resource", Severity.ERROR,
                i18n.t("code/unknown-resource.unknown", name=name),
            )
