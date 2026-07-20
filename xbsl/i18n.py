"""Language of the linter output: message catalogs and lookup.

A rule module registers its own messages next to the rules that emit them, so that a rule
and its wording cannot drift apart:

    MESSAGES = {
        "code/brackets.unclosed": {
            "ru": "Не закрыта скобка '{ch}'.",
            "en": "Unclosed bracket '{ch}'.",
        },
    }
    i18n.register(MESSAGES)

Keys are `<rule id>.title` for a rule title and `<rule id>.<variant>` for its messages;
non-rule text uses a `<module>.<name>` key. Placeholders are `str.format` fields and must be
the same in every language – `tests/test_i18n.py` enforces that. A brace that is part of the
text – `() [] {{}}` – has to be doubled, because every template is formatted.

The language is chosen by: set_lang() (CLI --lang) > env XBSL_LANG (or the pre-rename
XBSLLINT_LANG) > system locale > ru.
An unknown key is returned as is, so a plugin written against 0.3 – which passed literal
strings rather than keys – keeps working.

The check-mode --help text is translated too (the `cli.help.*` keys). Its parser is built after
the language is resolved: cli.main reads --lang out of argv with lang_from_argv() before
build_parser(), because argparse learns --lang only when it parses. The scaffolding and
`templates` sub-parsers keep Russian help for now (they take no --lang and emit JSON).
"""

from __future__ import annotations

import locale as _locale
import os

LANGS = ("ru", "en")
DEFAULT_LANG = "ru"
ENV_LANG = "XBSL_LANG"
_ENV_LANG_LEGACY = "XBSLLINT_LANG"

_catalog: dict[str, dict[str, str]] = {}
_selected: str | None = None

# Text of the adapters themselves (CLI summary, tool descriptions) – not tied to any one rule.
_CORE_MESSAGES = {
    "cli.summary": {
        "ru": "\nПроверено файлов: {files} ({xbsl} .xbsl, {yaml} .yaml); "
              "замечаний: {diags} (ошибок: {errors})",
        "en": "\nFiles checked: {files} ({xbsl} .xbsl, {yaml} .yaml); "
              "diagnostics: {diags} (errors: {errors})",
    },
    "cli.no-rules": {
        "ru": "(правила ещё не зарегистрированы)",
        "en": "(no rules registered yet)",
    },
    "cli.data-error": {
        "ru": "Ошибка данных Элемента: {error}",
        "en": "Element data error: {error}",
    },
    "cli.stdin-needs-filename": {
        "ru": "Режиму --stdin нужен --filename (напр. Форма.xbsl): по расширению определяется вид файла.",
        "en": "--stdin needs --filename (e.g. Form.xbsl): the extension sets the file kind.",
    },
    "cli.index-single-path": {
        "ru": "Режиму --index нужен ровно один путь – корень индексируемого проекта.",
        "en": "--index takes exactly one path – the root of the project to index.",
    },
    "cli.index-missing-path": {
        "ru": "Путь '{path}' не существует.",
        "en": "Path '{path}' does not exist.",
    },
    "cli.baseline-summary": {
        "ru": "Погашено базлайном: {suppressed}; устаревших записей базлайна: {unused}",
        "en": "Suppressed by the baseline: {suppressed}; stale baseline entries: {unused}",
    },
    "cli.baseline-written": {
        "ru": "Базлайн записан: {path} ({diags} замечаний в {files} файлах)",
        "en": "Baseline written: {path} ({diags} findings in {files} files)",
    },
    "cli.fix-summary": {
        "ru": "Исправлено замечаний: {fixed} в {files} файлах; осталось: {left}",
        "en": "Fixed findings: {fixed} in {files} files; remaining: {left}",
    },
    "cli.fix-needs-files": {
        "ru": "Режим --fix пишет файлы на диске и несовместим с --stdin.",
        "en": "--fix writes files on disk and is incompatible with --stdin.",
    },
    "cli.fix-conflicts-baseline": {
        "ru": "Режим --fix несовместим с --baseline / --write-baseline.",
        "en": "--fix is incompatible with --baseline / --write-baseline.",
    },
    # -- help: check-mode argparse help (cli.py build_parser / _commands_help) --
    # The scaffolding and templates sub-parsers keep Russian help (no --lang, JSON output).
    "cli.help.usage": {
        "ru": "%(prog)s [пути] [опции]        (без команды: проверка исходников)\n"
              "       %(prog)s <команда> [опции]",
        "en": "%(prog)s [paths] [options]       (no command: check the sources)\n"
              "       %(prog)s <command> [options]",
    },
    "cli.help.description": {
        "ru": "Линтер исходников 1С:Элемент (пары .yaml/.xbsl).\n\n"
              "Без команды проверяет указанные пути – это режим по умолчанию.\n"
              "Команды ниже адресуют остальные части инструментария.",
        "en": "Linter for 1C:Element sources (.yaml/.xbsl pairs).\n\n"
              "With no command it checks the given paths – this is the default mode.\n"
              "The commands below address the other parts of the toolkit.",
    },
    "cli.help.paths": {
        "ru": "файлы или каталоги для проверки",
        "en": "files or directories to check",
    },
    "cli.help.select": {
        "ru": "проверять только эти правила (через запятую или повтором флага: id, группа – "
              "часть id до '/' (напр. style) – или буква тира A/B/C/D)",
        "en": "check only these rules (comma-separated or by repeating the flag: id, group – "
              "the part of the id before '/' (e.g. style) – or a tier letter A/B/C/D)",
    },
    "cli.help.ignore": {
        "ru": "исключить эти правила (через запятую или повтором флага: id, группа или буква тира)",
        "en": "exclude these rules (comma-separated or by repeating the flag: id, group or tier letter)",
    },
    "cli.help.enable": {
        "ru": "добавить выключенные по умолчанию правила ПОВЕРХ стандартного набора "
              "(--select набор заменяет); формы значений те же",
        "en": "add rules disabled by default ON TOP of the standard set "
              "(--select replaces the set); the value forms are the same",
    },
    "cli.help.baseline": {
        "ru": "гасить находки, замороженные в файле базлайна (создаётся --write-baseline); "
              "новые находки выводятся как обычно",
        "en": "suppress findings frozen in a baseline file (created by --write-baseline); "
              "new findings are reported as usual",
    },
    "cli.help.write-baseline": {
        "ru": "вместо отчёта записать все текущие находки в файл базлайна "
              "(заморозить долг; пути в файле – относительно его каталога)",
        "en": "instead of a report, write all current findings to a baseline file "
              "(freeze the debt; paths in the file are relative to its directory)",
    },
    "cli.help.fix": {
        "ru": "исправить механические находки на месте (хвостовые пробелы, типографские "
              "символы, переводы строк) и вывести оставшиеся; правит только однозначно",
        "en": "fix mechanical findings in place (trailing spaces, typographic "
              "characters, line endings) and report the rest; only unambiguous fixes",
    },
    "cli.help.jobs": {
        "ru": "процессов для файловых правил: 0 – авто (включается на больших прогонах), "
              "1 – последовательно, N – явное число воркеров",
        "en": "processes for file-scope rules: 0 – auto (kicks in on large runs), "
              "1 – sequential, N – an explicit worker count",
    },
    "cli.help.list-rules": {
        "ru": "вывести список правил и выйти",
        "en": "print the list of rules and exit",
    },
    "cli.help.where": {
        "ru": "показать корень данных Элемента (путь, источник, версии) и выйти",
        "en": "show the Element data root (path, source, versions) and exit",
    },
    "cli.help.element-version": {
        "ru": "версия данных Элемента (по умолчанию – последняя из бандла)",
        "en": "Element data version (default: the latest in the bundle)",
    },
    "cli.help.data-dir": {
        "ru": "корень данных Элемента (каталог с index.json); также env XBSL_DATA_DIR",
        "en": "Element data root (a directory with index.json); also env XBSL_DATA_DIR",
    },
    "cli.help.lang": {
        "ru": "язык вывода линтера (по умолчанию: env XBSL_LANG / локаль системы / ru)",
        "en": "linter output language (default: env XBSL_LANG / system locale / ru)",
    },
    "cli.help.format": {
        "ru": "формат вывода: text (по умолчанию), json (машиночитаемый: diagnostics + summary) "
              "или codeclimate (отчёт GitLab Code Quality – виджет в merge request)",
        "en": "output format: text (default), json (machine-readable: diagnostics + summary) "
              "or codeclimate (a GitLab Code Quality report – the merge request widget)",
    },
    "cli.help.stdin": {
        "ru": "проверить один буфер из stdin (для интеграции с редактором); "
              "вид файла и путь в позициях задаёт --filename",
        "en": "check a single buffer from stdin (for editor integration); "
              "--filename sets the file kind and the reported path",
    },
    "cli.help.index": {
        "ru": "вместо проверки вывести JSON-индекс проекта (объекты, методы, компоненты форм) "
              "для навигации в редакторе; путь – корень проекта",
        "en": "instead of checking, print a JSON project index (objects, methods, form components) "
              "for editor navigation; the path is the project root",
    },
    "cli.help.filename": {
        "ru": "имя проверяемого буфера при --stdin (напр. Форма.xbsl); расширение задаёт вид файла",
        "en": "name of the buffer checked with --stdin (e.g. Форма.xbsl); the extension sets the file kind",
    },
    "cli.help.meta.rule-selector": {
        "ru": "ID/ГРУППА/ТИР",
        "en": "ID/GROUP/TIER",
    },
    "cli.help.meta.file": {
        "ru": "ФАЙЛ",
        "en": "FILE",
    },
    "cli.help.meta.version": {
        "ru": "ВЕРСИЯ",
        "en": "VERSION",
    },
    "cli.help.meta.dir": {
        "ru": "КАТАЛОГ",
        "en": "DIR",
    },
    "cli.help.meta.name": {
        "ru": "ИМЯ",
        "en": "NAME",
    },
    "cli.help.server.lsp": {
        "ru": "сервер LSP для редактора",
        "en": "LSP server for the editor",
    },
    "cli.help.server.mcp": {
        "ru": "сервер MCP для агента",
        "en": "MCP server for the agent",
    },
    "cli.help.server.web": {
        "ru": "веб-панель",
        "en": "web panel",
    },
    "cli.help.commands.header": {
        "ru": "команды:",
        "en": "commands:",
    },
    "cli.help.commands.lint-name": {
        "ru": "lint <пути>",
        "en": "lint <paths>",
    },
    "cli.help.commands.lint-desc": {
        "ru": "проверить исходники – то же, что без команды",
        "en": "check the sources – the same as with no command",
    },
    "cli.help.commands.templates": {
        "ru": "шаблоны кода: list, export, import, save",
        "en": "code templates: list, export, import, save",
    },
    "cli.help.commands.self-update": {
        "ru": "обновить xbsl распаковкой колеса с PyPI",
        "en": "update xbsl by unpacking the wheel from PyPI",
    },
    "cli.help.commands.scaffold-header": {
        "ru": "скаффолдинг метаданных (создание и правка исходников):",
        "en": "metadata scaffolding (create and edit sources):",
    },
    "cli.help.commands.footer": {
        "ru": "Опции команды: xbsl <команда> --help. Опции выше относятся к режиму проверки.",
        "en": "Command options: xbsl <command> --help. The options above apply to the check mode.",
    },
}


class MessageError(RuntimeError):
    pass


def _register_core() -> None:
    """Register the adapters' own messages. Called on import; safe to call again."""
    register(_CORE_MESSAGES)


def register(messages: dict[str, dict[str, str]]) -> None:
    """Add messages to the catalog. Every key must carry every language of LANGS."""
    for key, per_lang in messages.items():
        missing = [lang for lang in LANGS if lang not in per_lang]
        if missing:
            raise MessageError(f"Message '{key}' has no translation for: {', '.join(missing)}")
        known = _catalog.get(key)
        if known is not None and known != per_lang:
            raise MessageError(f"Message '{key}' is already registered with a different wording")
        _catalog[key] = dict(per_lang)


def registered_keys() -> list[str]:
    return sorted(_catalog)


def translations(key: str) -> dict[str, str] | None:
    entry = _catalog.get(key)
    return dict(entry) if entry else None


def set_lang(lang: str | None) -> None:
    """Pin the output language for the process (CLI --lang). None restores the lookup order."""
    global _selected
    if lang is not None and lang not in LANGS:
        raise MessageError(f"Unknown language '{lang}'. Available: {', '.join(LANGS)}")
    _selected = lang


def lang_from_argv(argv) -> str | None:
    """Read --lang out of raw argv, before the parser is built.

    The parser is built with translated help=, but argparse learns --lang only when it parses –
    too late to choose the help language. So the value is scanned out of argv beforehand.
    Accepts "--lang en" and "--lang=en". A value outside LANGS returns None: the language stays
    at its default and argparse rejects the bad value with its own message. env / locale need no
    prescan – t() already reads them through current_lang() when the parser is built.
    """
    for i, arg in enumerate(argv):
        value = None
        if arg == "--lang" and i + 1 < len(argv):
            value = argv[i + 1]
        elif arg.startswith("--lang="):
            value = arg[len("--lang="):]
        if value is not None:
            return value if value in LANGS else None
    return None


def _system_lang() -> str | None:
    code = ""
    try:
        code = _locale.getlocale()[0] or ""
    except (ValueError, TypeError):
        pass
    code = (code or os.environ.get("LC_ALL") or os.environ.get("LANG") or "").lower()
    # "ru_RU.UTF-8" and Windows' "Russian_Russia" both start with the language code.
    for lang in LANGS:
        if code.startswith(lang):
            return lang
    return None


def current_lang() -> str:
    if _selected is not None:
        return _selected
    env = os.environ.get(ENV_LANG, os.environ.get(_ENV_LANG_LEGACY, "")).strip().lower()
    if env in LANGS:
        return env
    return _system_lang() or DEFAULT_LANG


def t(key: str, /, **fields) -> str:
    """Translate a key and substitute the fields. An unknown key is returned unchanged.

    A template is always run through str.format, so a literal brace must be doubled: `{{}}`.
    Formatting conditionally – only when fields are passed – would turn a literal brace into a
    field the day someone adds one, and the failure would surface as a crash in a rule.
    """
    entry = _catalog.get(key)
    if entry is None:
        return key
    template = entry.get(current_lang()) or entry[DEFAULT_LANG]
    return template.format(**fields)


_register_core()
