"""Рантайм-API документации (xbsllint/docs.py) на крошечной БД, собранной в тесте (без дистрибутива)."""

import sqlite3
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "tools"))
import extract_docs as ex  # noqa: E402
from xbsllint import dataset, docs  # noqa: E402


def _has_fts5() -> bool:
    try:
        c = sqlite3.connect(":memory:")
        c.execute("CREATE VIRTUAL TABLE t USING fts5(x)")
        return True
    except sqlite3.OperationalError:
        return False


pytestmark = pytest.mark.skipif(not _has_fts5(), reason="в этой сборке SQLite нет FTS5")

_VER = "9.9.9+0"
_PAGES = [
    # id, kind, title, qualified, availability, parent, url, html, text
    ("Collections/Array_ru", "type", "Массив", "Стд::Коллекции::Массив", "КлиентИСервер",
     "Collections", "https://host/docs/help/stdlib/element/xbsl/Std/Collections/Array_ru/",
     '<h1>Массив</h1><p>Динамический массив значений. <img src="assets/i.png"></p>',
     "Массив Динамический массив значений добавить элемент"),
    ("Database/Query_ru", "type", "Запрос", "Стд::БазаДанных::Запрос", "Сервер",
     "Database", "https://host/docs/help/stdlib/element/xbsl/Std/Database/Query_ru/",
     "<h1>Запрос</h1><p>Выполнение запросов к базе данных.</p>",
     "Запрос Выполнение запросов к базе данных выборка"),
]


@pytest.fixture
def docs_root(tmp_path):
    """Каталог данных с крошечной docs.sqlite; docs.py читает её как настоящую."""
    ver_dir = tmp_path / _VER
    ver_dir.mkdir()
    con = sqlite3.connect(ver_dir / "docs.sqlite")
    con.executescript(ex._SCHEMA)
    for i, p in enumerate(_PAGES):
        con.execute("INSERT INTO pages VALUES(?,?,?,?,?,?,?,?)", p[:8])  # text – только в FTS
        con.execute("INSERT INTO pages_fts(id,title,qualified,text) VALUES(?,?,?,?)",
                    (p[0], p[2], p[3], p[8]))
        con.execute("INSERT INTO tree(id,parent,ord) VALUES(?,?,?)", (p[0], p[5], i))
    con.execute("INSERT INTO assets VALUES(?,?,?)", ("assets/i.png", "image/png", b"\x89PNG\r\n"))
    con.commit()
    con.close()
    (tmp_path / "index.json").write_text(
        '{"available": ["%s"], "default": "%s"}' % (_VER, _VER), encoding="utf-8"
    )
    dataset.set_data_root(tmp_path)
    docs._connect.cache_clear()
    yield tmp_path
    dataset.set_data_root(None)
    docs._connect.cache_clear()


def test_available(docs_root):
    assert docs.available() is True


def test_available_false_without_data(tmp_path):
    dataset.set_data_root(tmp_path)  # пусто, индекса нет
    docs._connect.cache_clear()
    try:
        assert docs.available() is False
        assert docs.search("массив") == []
        assert docs.page("Collections/Array_ru") is None
        assert docs.tree() == []
        assert docs.for_symbol("Массив") is None
    finally:
        dataset.set_data_root(None)


def test_search_ranks_and_returns_url(docs_root):
    hits = docs.search("массив")
    assert hits and hits[0]["id"] == "Collections/Array_ru"
    assert hits[0]["url"].endswith("Collections/Array_ru/")
    assert "title" in hits[0] and "snippet" in hits[0]


def test_search_multiword(docs_root):
    assert docs.search("выполнение запросов")[0]["id"] == "Database/Query_ru"


def test_search_empty_query(docs_root):
    assert docs.search("   ") == []
    assert docs.search("!!!") == []  # нет словных токенов


def test_page(docs_root):
    p = docs.page("Database/Query_ru")
    assert p["title"] == "Запрос" and p["availability"] == "Сервер"
    assert p["url"].endswith("Database/Query_ru/") and "<h1>" in p["html"]
    assert docs.page("нет") is None


def test_for_symbol_exact_then_search(docs_root):
    assert docs.for_symbol("Массив") == "Collections/Array_ru"      # точный заголовок
    assert docs.for_symbol("Стд::БазаДанных::Запрос".split("::")[-1]) == "Database/Query_ru"
    assert docs.for_symbol("выборка") == "Database/Query_ru"        # только полнотекстом
    assert docs.for_symbol("такого-нет-нигде") is None


def test_tree(docs_root):
    t = docs.tree()
    assert {n["id"] for n in t} == {"Collections/Array_ru", "Database/Query_ru"}
    assert all("title" in n and "parent" in n for n in t)


def test_asset(docs_root):
    a = docs.asset("assets/i.png")
    assert a["mime"] == "image/png" and a["bytes"].startswith(b"\x89PNG")
    assert docs.asset("assets/нет.png") is None
