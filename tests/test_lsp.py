"""Pure LSP server helpers (no pygls): the word under the cursor and parameter parsing."""

from xbsl import lsp


def test_word_at():
    line = "знч Список = новый Массив()"
    assert lsp._word_at(line, 0) == "знч"
    assert lsp._word_at(line, 6) == "Список"      # middle of the word
    assert lsp._word_at(line, 20) == "Массив"
    assert lsp._word_at(line, 10) == "Список"      # trailing edge of the word (cursor at its end)
    assert lsp._word_at(line, 11) == ""            # on the '=' operator


def test_word_at_edges():
    assert lsp._word_at("", 0) == ""
    assert lsp._word_at("Массив", 100) == "Массив"  # cursor past the end of the line
    assert lsp._word_at("A.Поле", 2) == "Поле"      # a dot is a word boundary
    assert lsp._word_at("Тип_1", 0) == "Тип_1"       # underscore and digit are part of the name


def test_param_dict_and_object():
    assert lsp._param({"query": "массив"}, "query") == "массив"
    assert lsp._param({"query": "x"}, "limit", 20) == 20
    assert lsp._param(None, "query", "def") == "def"

    class P:
        query = "z"

    assert lsp._param(P(), "query") == "z"
    assert lsp._param(P(), "missing", 5) == 5


def test_doc_key_meets_both_uri_spellings(tmp_path):
    """The editor sends file:///d%3A/..., the server builds file:///d:/... - the key must match.

    While uri strings were compared directly, project findings of an open file were getting
    lost: the key they were stored under could not be found by the key from the editor.
    """
    import os
    import re
    from pathlib import Path

    import pytest

    uris = pytest.importorskip("pygls.uris")
    f = tmp_path / "М.yaml"
    f.write_text("ВидЭлемента: Справочник\n", encoding="utf-8")

    серверный = uris.from_fs_path(str(f))
    # exactly the way the editor's spelling differs on Windows
    редакторский = re.sub(r"^file:///([A-Za-z]):", r"file:///\1%3A", серверный)
    if os.name == "nt":
        assert серверный != редакторский  # otherwise the test checks nothing

    ключ = lambda u: lsp._doc_key(Path(uris.to_fs_path(u)), u)
    assert ключ(серверный) == ключ(редакторский)


def test_doc_key_without_path_falls_back_to_uri():
    assert lsp._doc_key(None, "untitled:Untitled-1") == "untitled:Untitled-1"


def test_resolve_templates_path(tmp_path):
    """Without --templates the server falls back to the panel's file at the workspace
    root: what the panel saves, the next Ctrl+Space must see."""
    from pathlib import Path

    from xbsl.templates import DEFAULT_FILE

    assert lsp._resolve_templates_path(None, tmp_path) == tmp_path / DEFAULT_FILE
    assert lsp._resolve_templates_path(None, None) is None
    assert lsp._resolve_templates_path("own.json", tmp_path) == tmp_path / "own.json"
    absolute = str(tmp_path / "t.json")
    assert lsp._resolve_templates_path(absolute, tmp_path) == Path(absolute)
