"""Чистые помощники LSP-сервера (без pygls): слово под курсором и разбор параметров."""

from xbsllint import lsp


def test_word_at():
    line = "знч Список = новый Массив()"
    assert lsp._word_at(line, 0) == "знч"
    assert lsp._word_at(line, 6) == "Список"      # середина слова
    assert lsp._word_at(line, 20) == "Массив"
    assert lsp._word_at(line, 10) == "Список"      # хвостовой край слова (курсор в конце)
    assert lsp._word_at(line, 11) == ""            # на операторе '='


def test_word_at_edges():
    assert lsp._word_at("", 0) == ""
    assert lsp._word_at("Массив", 100) == "Массив"  # курсор за концом строки
    assert lsp._word_at("A.Поле", 2) == "Поле"      # точка – граница слова
    assert lsp._word_at("Тип_1", 0) == "Тип_1"       # подчёркивание и цифра – часть имени


def test_param_dict_and_object():
    assert lsp._param({"query": "массив"}, "query") == "массив"
    assert lsp._param({"query": "x"}, "limit", 20) == 20
    assert lsp._param(None, "query", "def") == "def"

    class P:
        query = "z"

    assert lsp._param(P(), "query") == "z"
    assert lsp._param(P(), "missing", 5) == 5
