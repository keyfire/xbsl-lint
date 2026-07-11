"""Разбор страниц доков дистрибутива в tools/extract_stdlib.py (component_props).

Инструмент – скрипт вне пакета, поэтому грузится по пути через importlib; сеть и
дистрибутив не нужны – страницы синтетические, по образцу реальной разметки Docusaurus.
"""

import importlib.util
import sys
from pathlib import Path

_TOOLS = Path(__file__).resolve().parents[1] / "tools"


def _extractor():
    spec = importlib.util.spec_from_file_location("extract_stdlib", _TOOLS / "extract_stdlib.py")
    mod = importlib.util.module_from_spec(spec)
    sys.modules.setdefault("extract_stdlib", mod)
    spec.loader.exec_module(mod)
    return mod


_МОДУЛЬ = _extractor()

_СТРАНИЦА_КОМПОНЕНТА = (
    "<html><head><title>МойКомпонент | 1С:Предприятие.Элемент</title></head><body>"
    "<article><h1>МойКомпонент</h1>"
    '<h2 class="anchor" id="иерархия-типа">Иерархия типа<a href="#иерархия-типа" '
    'class="hash-link">​</a></h2>'
    '<p>Базовые типы: <a href="/Object_ru/">Объект</a>, '
    '<a href="/Component_ru/">Стд::Интерфейс::Компонент</a></p>'
    "<h2>Конструкторы​</h2><h3>МойКомпонент​</h3>"
    "<h2>Свойства​</h2>"
    '<h3 class="anchor" id="заголовок">Заголовок<a href="#заголовок" '
    'class="hash-link">​</a></h3>'
    '<p>Тип: <a href="/String_ru/">Строка</a></p>'
    "<h3>Заголовок​</h3><p>Тип: <a href='/String_ru/'>Строка</a> (установка)</p>"
    "<h2>Список унаследованных свойств​</h2>"
    '<h3 class="anchor" id="компонент">Компонент<a href="#компонент" '
    'class="hash-link">​</a></h3>'
    '<p><a href="/Component_ru/#видимость">Видимость</a>, '
    '<a href="/Component_ru/#ширина">Ширина</a></p>'
    "</article></body></html>"
)

_СТРАНИЦА_НЕ_КОМПОНЕНТА = (
    "<html><head><title>ПростойТип | 1С:Предприятие.Элемент</title></head><body>"
    "<article><h1>ПростойТип</h1>"
    "<h2>Иерархия типа​</h2><p>Базовые типы: <a href='/Object_ru/'>Объект</a></p>"
    "<h2>Свойства​</h2><h3>Заголовок​</h3>"
    "</article></body></html>"
)


def test_component_page_props_collected():
    got = _МОДУЛЬ.component_props("какой-то/путь/index.html", _СТРАНИЦА_КОМПОНЕНТА)
    assert got is not None
    name, props = got
    assert name == "МойКомпонент"
    # свои свойства – только заголовки H3 (дубль геттер/сеттер схлопнут, ссылки на типы
    # из описаний не попадают), унаследованные – тексты ссылок своей секции
    assert props == {"Заголовок", "Видимость", "Ширина"}


def test_non_component_page_skipped():
    # в базовых типах нет Стд::Интерфейс::Компонент – страница не компонент
    assert _МОДУЛЬ.component_props("какой-то/путь/index.html", _СТРАНИЦА_НЕ_КОМПОНЕНТА) is None


def test_component_base_page_included_by_path():
    # сама страница Компонента (в базовых только Объект) включается по известному пути
    raw = _СТРАНИЦА_НЕ_КОМПОНЕНТА.replace("ПростойТип", "Компонент")
    got = _МОДУЛЬ.component_props(_МОДУЛЬ.COMPONENT_PAGE, raw)
    assert got is not None
    assert got[0] == "Компонент" and got[1] == {"Заголовок"}
