"""Checks of versioned data access (self-containedness, version selection)."""

import pytest

from xbsl import dataset


def test_default_is_available():
    assert dataset.available_versions()
    assert dataset.default_version() in dataset.available_versions()


def test_load_language_and_stdlib():
    lang = dataset.load_json("language.json")
    assert lang["keywords"]["METHOD"]["forms"]
    std = dataset.load_json("stdlib.json")
    assert "Массив" in std["names"]


def test_data_stamped_with_element_version():
    lang = dataset.load_json("language.json")
    assert lang["meta"]["element_version"] == dataset.default_version()


def test_invalid_version_raises():
    with pytest.raises(dataset.DatasetError):
        dataset.resolve_version("0.0.0-нет-такой")


# --- inheritance expansion (dataset._expand_inherited), no distribution data needed --------

def _own_dataset():
    """A tiny stdlib.json in the own-members form: Наследник extends База extends Объект."""
    return {
        "meta": {"members": "own"},
        "bases": {"Наследник": ["База", "Объект"], "База": ["Объект"], "Объект": []},
        "type_members": {
            "Объект": {"methods": ["ВСтроку"]},
            "База": {"properties": ["Поле"], "methods": ["Метод"]},
            "Наследник": {"properties": ["Своё"]},
        },
        "member_types": {
            "Объект": {"ВСтроку": "Строка"},
            "База": {"Поле": "Число"},
            "Наследник": {"Своё": "Булево"},
        },
    }


def test_expand_inherited_completes_members_by_hierarchy():
    full = dataset._expand_inherited(_own_dataset())["type_members"]
    # Наследник gets its own member plus every ancestor's own.
    assert set(full["Наследник"]["properties"]) == {"Своё", "Поле"}
    assert set(full["Наследник"]["methods"]) == {"Метод", "ВСтроку"}
    assert set(full["База"]["methods"]) == {"Метод", "ВСтроку"}


def test_expand_inherited_completes_member_types():
    full = dataset._expand_inherited(_own_dataset())["member_types"]
    assert full["Наследник"] == {"Своё": "Булево", "Поле": "Число", "ВСтроку": "Строка"}


def test_expand_inherited_keeps_an_overridden_result_type():
    data = _own_dataset()
    data["member_types"]["Наследник"]["ВСтроку"] = "Представление"  # override the object's
    full = dataset._expand_inherited(data)["member_types"]
    assert full["Наследник"]["ВСтроку"] == "Представление"  # own wins over the ancestor's


def test_expand_inherited_leaves_full_datasets_untouched():
    full_form = {
        "meta": {},  # no "members": "own" marker - an older, already-full dataset
        "bases": {"Наследник": ["Объект"]},
        "type_members": {"Наследник": {"properties": ["Своё"]}},
    }
    assert dataset._expand_inherited(full_form)["type_members"] == {"Наследник": {"properties": ["Своё"]}}
