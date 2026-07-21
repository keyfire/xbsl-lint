"""Checks of the resource rules: code/resource-bare-name and code/unknown-resource.

The platform image library is stubbed, so the tests need no documentation data; one test
marked needs_data checks that the real library is read and holds the documented names.
"""

import pytest

from xbsl import engine
from xbsl.cli import discover
from xbsl.rules import resources

_BARE = "code/resource-bare-name"
_UNKNOWN = "code/unknown-resource"

_PROJECT_YAML = (
    "Ид: 9a1b2c3d-4e5f-6071-8293-a4b5c6d7e8f9\nВерсия: 1.0.0\nВидПроекта: Приложение\n"
    "Имя: Проба\nПоставщик: acme\nПредставление: Проба\nРежимСовместимости: 9.0\n"
)


@pytest.fixture
def library(monkeypatch):
    """A stubbed image library: one name, as if the platform shipped exactly that."""
    monkeypatch.setattr(resources, "_platform_images", lambda: frozenset({"Настройки.svg"}))


def _project(tmp_path, module_text, resource_names=("Своя.svg",)):
    root = tmp_path / "acme" / "Проба"
    (root / "Основное" / "Ресурсы").mkdir(parents=True)
    (root / "Проект.yaml").write_text(_PROJECT_YAML, encoding="utf-8")
    for name in resource_names:
        (root / "Основное" / "Ресурсы" / name).write_text("<svg/>", encoding="utf-8")
    (root / "Основное" / "М.xbsl").write_text(module_text, encoding="utf-8")
    return tmp_path


def _run(tmp_path, module_text, select, resource_names=("Своя.svg",)):
    _project(tmp_path, module_text, resource_names)
    return engine.run(discover([str(tmp_path)]), select={select})


def _method(body):
    return f"// М\n\nметод М(): ДвоичныйОбъект.Ссылка\n    возврат {body}\n;\n"


# --- code/resource-bare-name (file scope, no data needed) ---------------------------------


def test_path_with_folder_flagged(tmp_path):
    d = _run(tmp_path, _method("Ресурс{Ресурсы/Своя.svg}.Ссылка"), _BARE)
    assert len(d) == 1 and d[0].rule_id == _BARE
    assert d[0].severity.name == "ERROR"
    assert "Ресурс{Своя.svg}" in d[0].message
    assert (d[0].line, d[0].col) == (4, 20)  # the first character inside the braces


def test_backslash_path_flagged(tmp_path):
    d = _run(tmp_path, _method("Ресурс{Ресурсы\\Своя.svg}.Ссылка"), _BARE)
    assert len(d) == 1


def test_bare_name_not_flagged(tmp_path):
    assert not _run(tmp_path, _method("Ресурс{Своя.svg}.Ссылка"), _BARE)


def test_qualified_name_not_flagged(tmp_path):
    # Стд::Грузовик.svg is the documented form of a library image, not a path
    assert not _run(tmp_path, _method("Ресурс{Стд::Грузовик.svg}.Ссылка"), _BARE)


def test_mention_in_a_comment_not_flagged(tmp_path):
    text = "// Ресурс{Ресурсы/Своя.svg} – так писать нельзя\n" + _method("Ресурс{Своя.svg}.Ссылка")
    assert not _run(tmp_path, text, _BARE)


# --- code/unknown-resource (project scope, needs the library) -----------------------------


def test_unknown_name_flagged(tmp_path, library):
    d = _run(tmp_path, _method("Ресурс{Настройки3.svg}.Ссылка"), _UNKNOWN)
    assert len(d) == 1 and d[0].rule_id == _UNKNOWN
    assert (d[0].line, d[0].col) == (4, 20)


def test_project_resource_not_flagged(tmp_path, library):
    assert not _run(tmp_path, _method("Ресурс{Своя.svg}.Ссылка"), _UNKNOWN)


def test_platform_library_name_not_flagged(tmp_path, library):
    # the file is not in the project – the platform ships it
    assert not _run(tmp_path, _method("Ресурс{Настройки.svg}.Ссылка"), _UNKNOWN)


def test_qualified_library_name_not_flagged(tmp_path, library):
    assert not _run(tmp_path, _method("Ресурс{Стд::Настройки.svg}.Ссылка"), _UNKNOWN)


def test_path_left_to_the_other_rule(tmp_path, library):
    # one mistake is not reported twice
    assert not _run(tmp_path, _method("Ресурс{Ресурсы/Своя.svg}.Ссылка"), _UNKNOWN)


def test_without_the_library_silent(tmp_path, monkeypatch):
    # no documentation data: guessing without the library is what produces false positives
    monkeypatch.setattr(resources, "_platform_images", frozenset)
    assert not _run(tmp_path, _method("Ресурс{Настройки3.svg}.Ссылка"), _UNKNOWN)


def test_without_a_project_file_silent(tmp_path, library):
    src = tmp_path / "acme"
    src.mkdir()
    (src / "М.xbsl").write_text(_method("Ресурс{Настройки3.svg}.Ссылка"), encoding="utf-8")
    assert not engine.run(discover([str(tmp_path)]), select={_UNKNOWN})


@pytest.mark.needs_data
def test_real_image_library_is_read():
    resources._platform_images.cache_clear()
    library = resources._platform_images()
    assert len(library) > 100
    assert {"Настройки.svg", "ГалочкаВКруге.svg", "Грузовик.svg"} <= library
