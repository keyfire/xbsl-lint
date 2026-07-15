"""Разбор страницы документации в tools/extract_docs.py – на мини-фикстурах (без дистрибутива)."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "tools"))
import extract_docs as ex  # noqa: E402

# Мини-страница в разметке Docusaurus: хлебные крошки и футер вне контент-блока, ссылка на Std,
# якорь-решётка, блок кода Prism, картинка и управляющий символ внутри слова.
PAGE = (
    "<html><body><article>"
    '<nav class="theme-doc-breadcrumbs"><span itemprop="name">Мас\x00сив</span></nav>'
    '<div class="theme-doc-markdown markdown"><div class="row"><div class="col col--12 markdown">'
    "<header><h1>Мас\x00сив</h1></header>"
    "<p><code>Стд::Коллекции::Массив</code>  <code>Доступность: КлиентИСервер</code></p>"
    '<p>См. <a href="/docs/help/stdlib/element/xbsl/Std/Object_ru/">Объект</a> и '
    '<a href="https://example.org/x">внешнее</a>.</p>'
    '<h2 class="anchor anchorWithStickyNavbar" id="r">Раздел'
    '<a href="#r" class="hash-link" title="ссылка">​</a></h2>'
    '<p><em>Дочерние типы:</em> <a href="/docs/help/stdlib/element/xbsl/DeveloperName/X/">Шаблон</a></p>'
    '<div class="language-xbsl codeBlockContainer"><div class="codeBlockContent">'
    '<pre class="prism-code"><code class="codeBlockLines">'
    '<span class="token-line"><span class="token xbsl-keyword">знч</span>'
    '<span class="token plain"> Х = 1</span><br></span></code></pre></div></div>'
    '<p><img decoding="async" alt="s" src="/docs/help/assets/images/a.png" width="10" class="img_x"></p>'
    "</div></div></div>"
    '<footer class="theme-doc-footer">низ страницы</footer>'
    "</article></body></html>"
)


def _rec():
    return ex._record("data/docs/help/ru/stdlib/element/xbsl/Std/Collections/Array_ru/index.html", PAGE)


def test_fields_extracted():
    r = _rec()
    assert r["id"] == "Collections/Array_ru"
    assert r["title"] == "Массив"           # управляющий символ вычищен
    assert r["qualified"] == "Стд::Коллекции::Массив"
    assert r["availability"] == "КлиентИСервер"
    assert r["parent"] == "Collections"


def test_kind_heuristic():
    assert ex._kind("... Иерархия типа ...") == "type"
    assert ex._kind("... Места применения ...") == "annotation"
    assert ex._kind("... Синтаксис ... Параметры ...") == "method"
    assert ex._kind("просто текст") == "member"


def test_chrome_stripped():
    html = _rec()["html"]
    assert "theme-doc" not in html and "breadcrumbs" not in html
    assert "низ страницы" not in html       # футер вне контента
    assert "class=" not in html and "<nav" not in html and "<div" not in html
    assert "hash-link" not in html and "​" not in html


def test_std_link_rewritten_external_kept():
    html = _rec()["html"]
    assert '<a href="#Object_ru">Объект</a>' in html
    assert '<a href="https://example.org/x">внешнее</a>' in html


def test_template_link_becomes_text():
    html = _rec()["html"]
    assert "Шаблон" in html                 # текст остался
    assert "DeveloperName" not in html      # неразрешённая ссылка развёрнута


def test_code_flattened():
    html = _rec()["html"]
    assert "<pre><code>знч Х = 1</code></pre>" in html
    assert "token" not in html and "<span" not in html


def test_image_preserved_and_ref_collected():
    html = _rec()["html"]
    assert '<img src="assets/images/a.png">' in html
    assert ex._ASSET_REF_RE.findall(html) == ["assets/images/a.png"]


def test_text_has_no_tags():
    text = _rec()["text"]
    assert "<" not in text and ">" not in text
    assert "Массив" in text and "знч Х = 1" in text


def test_canonical_url():
    assert (
        ex._canonical_url("https://1cmycloud.com", "Collections/Array_ru")
        == "https://1cmycloud.com/docs/help/stdlib/element/xbsl/Std/Collections/Array_ru/"
    )


def test_no_content_block_returns_none():
    assert ex._record("x/index.html", "<html><body>нет разметки</body></html>") is None
