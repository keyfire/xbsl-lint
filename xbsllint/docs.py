"""Рантайм-доступ к документации Элемента (docs.sqlite): поиск, страница, дерево, символ.

База собирается `tools/extract_docs.py` из дистрибутива и лежит в бандле данных
`<корень>/<версия>/docs.sqlite` рядом со `stdlib.json` (см. dataset.py). Документация
необязательна: если базы нет, `available()` возвращает Ложь, а прочие функции – пустой
результат, чтобы MCP-сервер и LSP работали и без неё.

Поверх этого API строятся: инструменты MCP (Клод ищет методы, их свойства и параметры),
эндпоинт LSP "дока для символа под курсором" и панель расширения (дерево + просмотр HTML).
"""
from __future__ import annotations

import re
import sqlite3
from functools import lru_cache
from pathlib import Path

from xbsllint import dataset

_DB_NAME = "docs.sqlite"
# Токен запроса: буквы (вкл. кириллицу), цифры, подчёркивание – всё прочее для FTS5 отбрасываем.
_TOKEN_RE = re.compile(r"\w+", re.UNICODE)


def available(version: str | None = None) -> bool:
    """Есть ли база документации для версии данных."""
    return dataset.has_data_file(_DB_NAME, version)


@lru_cache(maxsize=8)
def _connect(root: str, path: str) -> sqlite3.Connection:
    """Кэшированное соединение только для чтения (ключ – корень+путь, как в dataset)."""
    uri = Path(path).as_uri() + "?mode=ro"  # корректный file-URI на любой ОС (Windows-пути тоже)
    con = sqlite3.connect(uri, uri=True, check_same_thread=False)
    con.row_factory = sqlite3.Row
    return con


def _db(version: str | None = None) -> sqlite3.Connection | None:
    if not available(version):
        return None
    path = dataset.data_file(_DB_NAME, version)
    return _connect(str(dataset.data_root()), str(path))


def _fts_query(query: str) -> str:
    """Свободный текст -> безопасное выражение FTS5: слова в кавычках через И, последнее с префиксом."""
    tokens = _TOKEN_RE.findall(query)
    if not tokens:
        return ""
    terms = [f'"{t}"' for t in tokens[:-1]]
    terms.append(f'"{tokens[-1]}"*')  # префикс на последнем слове – удобно для набора на лету
    return " ".join(terms)


def search(query: str, limit: int = 10, version: str | None = None) -> list[dict]:
    """Полнотекстовый поиск по документации, ранжирование bm25 (лучшее – первым)."""
    con = _db(version)
    match = _fts_query(query)
    if con is None or not match:
        return []
    rows = con.execute(
        "SELECT p.id, p.title, p.qualified, p.kind, p.availability, p.url,"
        "       snippet(pages_fts, 3, '', '', ' ... ', 12) AS snippet "
        "FROM pages_fts f JOIN pages p ON p.id = f.id "
        "WHERE pages_fts MATCH ? ORDER BY bm25(pages_fts) LIMIT ?",
        (match, limit),
    ).fetchall()
    return [dict(r) for r in rows]


def page(doc_id: str, version: str | None = None) -> dict | None:
    """Полная запись страницы (с очищенным HTML) по её id или None."""
    con = _db(version)
    if con is None:
        return None
    row = con.execute(
        "SELECT id, kind, title, qualified, availability, parent, url, html FROM pages WHERE id = ?",
        (doc_id,),
    ).fetchone()
    return dict(row) if row else None


def tree(version: str | None = None) -> list[dict]:
    """Плоский список узлов оглавления (id, parent, title, kind) – дерево строит потребитель."""
    con = _db(version)
    if con is None:
        return []
    rows = con.execute(
        "SELECT p.id, p.parent, p.title, p.kind FROM tree t JOIN pages p ON p.id = t.id "
        "ORDER BY t.ord"
    ).fetchall()
    return [dict(r) for r in rows]


def for_symbol(name: str, version: str | None = None) -> str | None:
    """id страницы для имени символа/типа: точное совпадение заголовка сильнее, иначе – топ поиска.

    Имя может быть простым (`Массив`) или последним сегментом квалификатора (`Стд::...::Массив`).
    """
    con = _db(version)
    if con is None or not name:
        return None
    name = name.strip()
    exact = con.execute(
        "SELECT id FROM pages WHERE title = ? ORDER BY length(qualified) LIMIT 1", (name,)
    ).fetchone()
    if exact:
        return exact["id"]
    byq = con.execute(
        "SELECT id FROM pages WHERE qualified LIKE ? ORDER BY length(qualified) LIMIT 1",
        (f"%::{name}",),
    ).fetchone()
    if byq:
        return byq["id"]
    hits = search(name, limit=1, version=version)
    return hits[0]["id"] if hits else None


def asset(asset_id: str, version: str | None = None) -> dict | None:
    """Байты картинки по её id (`assets/...`) с mime, для рендера страницы в панели, или None."""
    con = _db(version)
    if con is None:
        return None
    row = con.execute("SELECT id, mime, bytes FROM assets WHERE id = ?", (asset_id,)).fetchone()
    return dict(row) if row else None
