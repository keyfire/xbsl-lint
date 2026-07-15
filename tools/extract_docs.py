"""Извлечение документации 1С:Элемент из дистрибутива в docs.sqlite (страницы + индекс FTS5).

Внутри .car сервера-с-IDE документация лежит статическим сайтом (Docusaurus) по пути
`data/docs/help/ru/stdlib/element/xbsl/Std/**/index.html`. Здесь эти страницы разбираются в
структурированные записи и складываются в одну базу SQLite:

- `pages(id, kind, title, qualified, availability, parent, html)` – по странице на символ;
- `pages_fts` – виртуальная таблица FTS5 (title, qualified, text) для полнотекстового поиска;
- `tree(id, parent, ord)` – оглавление ("Содержание") из иерархии каталогов.

Разметка страниц единообразна (генерируется Docusaurus), поэтому чистка идёт набором строковых
замен: из страницы вырезается контент-блок `theme-doc-markdown` (тема, навигация и футер лежат
вне его), блоки кода Prism сплющиваются в текст, структурные обёртки разворачиваются, внутренние
ссылки переписываются в схему doc-id (`#<id>`). HTML хранится очищенным – панель редактора
рендерит его как есть, MCP отдаёт текстовую выжимку.

Данные Элемента под копирайтом 1С – база кладётся в приватный бандл (как stdlib.json), на PyPI
не публикуется. Версия и корень данных определяются так же, как в extract_stdlib.py.
"""
from __future__ import annotations

import argparse
import re
import sqlite3
import sys
import zipfile
from html import escape, unescape
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import _distro  # noqa: E402

# Корень справочника stdlib в архиве и префикс внутренних ссылок на него внутри сайта помощи.
STD_BASE = "data/docs/help/ru/stdlib/element/xbsl/Std/"
LINK_BASE = "/docs/help/stdlib/element/xbsl/Std/"
# Корень статического сайта помощи в архиве (относительно него разрешаются ссылки и ассеты).
SITE_ROOT = "data/docs/help/ru/"
SITE_PREFIX = "/docs/help/"  # этим префиксом сайт адресует свой корень
# Канонический адрес сайта документации берём из sitemap; запасной – облако Элемента.
_SITEMAP = SITE_ROOT + "sitemap.xml"
_DEFAULT_ORIGIN = "https://1cmycloud.com"
_LOC_RE = re.compile(r"<loc>\s*(https?://[^/\s<]+)")

_MIME = {
    ".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg",
    ".gif": "image/gif", ".svg": "image/svg+xml", ".webp": "image/webp",
}

_REGION_START = '<div class="theme-doc-markdown markdown">'
_REGION_END_RE = re.compile(r'<footer class="theme-doc-footer|<nav class="pagination-nav|</article>')

# Теги содержимого, которые сохраняем (у них срезаются атрибуты); ссылки обрабатываются отдельно.
_KEEP = "h1|h2|h3|h4|h5|p|ul|ol|li|strong|em|code|hr|br|blockquote|table|thead|tbody|tr|th|td"

_COMMENT_RE = re.compile(r"<!--.*?-->", re.S)
_SVG_RE = re.compile(r"<svg\b.*?</svg>", re.S)
_PRE_RE = re.compile(r"<pre\b[^>]*>(.*?)</pre>", re.S)
_BR_RE = re.compile(r"<br\s*/?>")
_HASHLINK_RE = re.compile(r'<a\b[^>]*class="[^"]*hash-link[^"]*"[^>]*>.*?</a>', re.S)
# Картинку сохраняем: src сайта (`/docs/help/assets/...`) переписываем в id ассета (`assets/...`);
# картинку без пригодного src убираем. Байты ассетов складываются в таблицу assets при сборке.
_IMG_RE = re.compile(r'<img\b[^>]*?\bsrc="([^"]*)"[^>]*>')
_IMG_BARE_RE = re.compile(r'<img\b(?![^>]*\bsrc="assets/)[^>]*>')  # уже переписанные не трогаем
_ASSET_REF_RE = re.compile(r'<img src="(assets/[^"]+)"')
_LINK_RE = re.compile(r'<a\b[^>]*?\bhref="([^"]*)"[^>]*>')
_BARE_A_RE = re.compile(r"<a\b(?![^>]*\bhref=)[^>]*>")  # только ссылки без href (переписанные не трогаем)
# Ссылки, не разрешённые в нашем наборе (шаблонный неймспейс, ассеты): разворачиваем в текст.
_DEADLINK_RE = re.compile(r'<a href="/[^"]*">(.*?)</a>', re.S)
_KEEP_RE = re.compile(rf"<(/?)(?:{_KEEP})\b[^>]*>")
_UNWRAP_RE = re.compile(r"</?(?:div|header|span|nav|button|time|meta|footer|figure|section)\b[^>]*>", re.S)
_TAG_RE = re.compile(r"<[^>]+>")
_WS_RE = re.compile(r"\s+")
# Управляющие символы, нулевые ширины и мягкий перенос – в разметке доков попадаются внутри слов
# и молча портят и текст, и индекс (напр. "Аннот\x00ации"); вырезаем на входе.
_CTRL_RE = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f​‌‍﻿­]")

_QUALIFIED_RE = re.compile(r"<code>(Стд(?:::[^<]+)*)</code>")
_AVAIL_RE = re.compile(r"Доступность:\s*([^<]+?)\s*</code>")
_H1_RE = re.compile(r"<h1>(.*?)</h1>", re.S)


def _rewrite_href(href: str) -> str:
    """Внутреннюю ссылку на Std -> `#<id>[#якорь]`, прочее оставляем как есть."""
    if not href.startswith(LINK_BASE):
        return href
    rest = href[len(LINK_BASE):]
    anchor = ""
    if "#" in rest:
        rest, anchor = rest.split("#", 1)
        anchor = "#" + anchor
    return "#" + rest.strip("/") + anchor


def _flatten_pre(m: re.Match) -> str:
    """Блок кода Prism/rouge -> `<pre><code>текст</code></pre>` (спаны выброшены, <br> -> перенос)."""
    inner = _BR_RE.sub("\n", m.group(1))
    code = unescape(_TAG_RE.sub("", inner)).strip("\n")  # хвостовой <br> даёт лишний перенос
    return "<pre><code>" + escape(code) + "</code></pre>"


def _rewrite_img(m: re.Match) -> str:
    """<img src="/docs/help/assets/X.png" ...> -> <img src="assets/X.png">; без пригодного src -> убираем."""
    src = unescape(m.group(1))
    if src.startswith(SITE_PREFIX):
        return f'<img src="{escape(src[len(SITE_PREFIX):])}">'  # -> assets/...
    return ""


def _clean(raw: str) -> tuple[str, str]:
    """Очищенный HTML контент-блока и плоский текст для индекса (пусто, если блока нет)."""
    start = raw.find(_REGION_START)
    if start < 0:
        return "", ""
    me = _REGION_END_RE.search(raw, start)
    region = raw[start: me.start() if me else len(raw)]

    region = _PRE_RE.sub(_flatten_pre, region)      # код сплющиваем до снятия тегов
    region = _COMMENT_RE.sub("", region)
    region = _SVG_RE.sub("", region)
    region = _IMG_RE.sub(_rewrite_img, region)      # картинку сохраняем (src -> id ассета)
    region = _IMG_BARE_RE.sub("", region)           # картинку без пригодного src убираем
    region = _HASHLINK_RE.sub("", region)
    region = _LINK_RE.sub(lambda m: f'<a href="{escape(_rewrite_href(unescape(m.group(1))))}">', region)
    region = _DEADLINK_RE.sub(r"\1", region)        # неразрешённые ссылки -> текст
    region = _BARE_A_RE.sub("<a>", region)          # ссылки без href
    region = _KEEP_RE.sub(_strip_attrs, region)     # атрибуты сохраняемых тегов срезаем
    region = _UNWRAP_RE.sub("", region)             # структурные обёртки разворачиваем
    html = _WS_RE.sub(" ", region).strip()

    text = _WS_RE.sub(" ", unescape(_TAG_RE.sub(" ", html))).strip()
    return html, text


def _strip_attrs(m: re.Match) -> str:
    """<h2 class=...> -> <h2>, </p> -> </p> (сохраняем только имя тега и слэш закрытия)."""
    slash = m.group(1)
    name = m.group(0)[1 + len(slash):].split()[0].rstrip(">/")
    return f"<{slash}{name}>"


def _record(entry: str, raw: str) -> dict | None:
    """Структурированная запись страницы или None, если контент-блока нет."""
    raw = _CTRL_RE.sub("", raw)  # управляющие символы портят текст, индекс и заголовки
    html, text = _clean(raw)
    if not html:
        return None
    doc_id = entry[len(STD_BASE):].rsplit("/", 1)[0]  # путь без /index.html
    mh = _H1_RE.search(html)
    title = unescape(_TAG_RE.sub("", mh.group(1)).strip()) if mh else doc_id.rsplit("/", 1)[-1]
    mq = _QUALIFIED_RE.search(raw)
    ma = _AVAIL_RE.search(raw)
    return {
        "id": doc_id,
        "kind": _kind(text),
        "title": title,
        "qualified": mq.group(1) if mq else "",
        "availability": ma.group(1).strip() if ma else "",
        "parent": "/".join(doc_id.split("/")[:-1]),
        "html": html,
        "text": text,
    }


def _origin(z: zipfile.ZipFile) -> str:
    """Схема+хост сайта документации из sitemap (для ссылок на первоисточник); запасной – облако."""
    try:
        raw = z.read(_SITEMAP).decode("utf-8", "replace")
    except KeyError:
        return _DEFAULT_ORIGIN
    m = _LOC_RE.search(raw)
    return m.group(1) if m else _DEFAULT_ORIGIN


def _canonical_url(origin: str, doc_id: str) -> str:
    """Канонический адрес страницы на сайте документации (первоисточник)."""
    return f"{origin}{LINK_BASE}{doc_id}/"


def _kind(text: str) -> str:
    if "Иерархия типа" in text or "Базовые типы" in text:
        return "type"
    if "Места применения" in text:
        return "annotation"
    if "Синтаксис" in text and "Параметры" in text:
        return "method"
    return "member"


_SCHEMA = """
CREATE TABLE pages (
    id TEXT PRIMARY KEY, kind TEXT, title TEXT, qualified TEXT,
    availability TEXT, parent TEXT, url TEXT, html TEXT
);
CREATE VIRTUAL TABLE pages_fts USING fts5(
    id UNINDEXED, title, qualified, text, tokenize='unicode61 remove_diacritics 0'
);
CREATE TABLE tree (id TEXT, parent TEXT, ord INTEGER);
CREATE TABLE assets (id TEXT PRIMARY KEY, mime TEXT, bytes BLOB);
CREATE INDEX pages_parent ON pages(parent);
"""


def build(dist: Path, out: Path) -> int:
    car = _distro.find_car(dist)
    if out.exists():
        out.unlink()
    con = sqlite3.connect(out)
    _assert_fts5(con)
    con.executescript(_SCHEMA)
    n = 0
    with zipfile.ZipFile(car) as z:
        origin = _origin(z)
        asset_ids: set[str] = set()
        pages = sorted(e for e in z.namelist() if e.startswith(STD_BASE) and e.endswith("/index.html"))
        for entry in pages:
            rec = _record(entry, z.read(entry).decode("utf-8", "replace"))
            if rec is None:
                continue
            con.execute(
                "INSERT INTO pages(id, kind, title, qualified, availability, parent, url, html)"
                " VALUES(?,?,?,?,?,?,?,?)",
                (rec["id"], rec["kind"], rec["title"], rec["qualified"], rec["availability"],
                 rec["parent"], _canonical_url(origin, rec["id"]), rec["html"]),
            )
            con.execute(
                "INSERT INTO pages_fts(id, title, qualified, text) VALUES(?,?,?,?)",
                (rec["id"], rec["title"], rec["qualified"], rec["text"]),
            )
            con.execute("INSERT INTO tree(id, parent, ord) VALUES(?,?,?)", (rec["id"], rec["parent"], n))
            asset_ids.update(_ASSET_REF_RE.findall(rec["html"]))
            n += 1
        _store_assets(con, z, asset_ids)
    con.execute("INSERT INTO pages_fts(pages_fts) VALUES('optimize')")
    con.commit()
    con.close()
    return n


def _store_assets(con: sqlite3.Connection, z: zipfile.ZipFile, asset_ids: set[str]) -> None:
    """Сохранить в таблицу assets байты картинок, на которые ссылаются страницы (id = `assets/...`)."""
    for aid in sorted(asset_ids):
        try:
            data = z.read(SITE_ROOT + aid)
        except KeyError:
            continue  # ссылка на отсутствующий ассет – пропускаем, картинка просто не покажется
        mime = _MIME.get("." + aid.rsplit(".", 1)[-1].lower(), "application/octet-stream")
        con.execute("INSERT OR IGNORE INTO assets(id, mime, bytes) VALUES(?,?,?)", (aid, mime, data))


def _assert_fts5(con: sqlite3.Connection) -> None:
    try:
        con.execute("CREATE VIRTUAL TABLE _t USING fts5(x)")
        con.execute("DROP TABLE _t")
    except sqlite3.OperationalError as e:
        raise SystemExit(f"В этой сборке SQLite нет FTS5: {e}")


def main() -> int:
    ap = argparse.ArgumentParser(description="Извлечь документацию Элемента из дистрибутива в docs.sqlite")
    ap.add_argument("--dist", required=True, help="каталог дистрибутива 1С:Элемент (с .car сервера-с-IDE)")
    ap.add_argument("--element-version", help="версия Элемента (если не из дистрибутива)")
    ap.add_argument("--no-default", action="store_true", help="не делать эту версию версией по умолчанию")
    ap.add_argument("--out", help="переопределить путь docs.sqlite")
    _distro.add_data_dir_arg(ap)
    args = ap.parse_args()
    _distro.set_data_root(args.data_dir)

    dist = Path(args.dist)
    if not dist.is_dir():
        raise SystemExit(f"Каталог дистрибутива не найден: {dist}")
    version = _distro.detect_version(dist, args.element_version)
    out = Path(args.out) if args.out else _distro.version_dir(version) / "docs.sqlite"
    n = build(dist, out)
    if not args.out:
        _distro.update_index(version, make_default=not args.no_default)
    print(f"Документация {version}: {n} страниц -> {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
