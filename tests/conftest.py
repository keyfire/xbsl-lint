"""Shared test setup.

The language/type data (xbsl/data/element/...) is extracted from a 1C:Element distribution
and may not have been generated (e.g. in a public checkout without a data bundle). Tests that
need the data are skipped rather than failed: either a whole module (_DATA_DEPENDENT) or a single
test marked `@pytest.mark.needs_data` - the latter keeps the data-free tests of a mixed module
running in a public checkout.

The output language is pinned to Russian: assertions elsewhere match Russian message text, and
without pinning the result would depend on the developer's system locale.
"""

import pytest

from xbsl import dataset, i18n

i18n.set_lang("ru")

_DATA_DEPENDENT = {
    "test_lexer",
    "test_language",
    "test_rule_ns_objects",
    "test_rules",
    "test_rule_environment",
    "test_style_rules",
    "test_mcp",
    "test_cli",
    "test_dataset",
    "test_corpus",
    "test_rule_reserved",
    "test_index",
    "test_baseline",
    "test_rule_query_tables",
    "test_rule_query_in_composite",
    "test_parser",  # парсер сидит на лексере, а тот – на language.json
    "test_statement_no_effect",  # правило разбирает код парсером
    "test_return_mismatch",  # правило разбирает код парсером
    "test_catch_exceptions",  # правилу нужен каталог stdlib
    "test_call_arity",  # правило разбирает код парсером
    "test_unknown_members",  # правилу нужен каталог stdlib
}


def _has_data() -> bool:
    try:
        return bool(dataset.available_versions())
    except Exception:  # noqa: BLE001
        return False


def pytest_configure(config):
    config.addinivalue_line("markers", "needs_data: тесту нужны данные Элемента (лексер, датасет)")


def pytest_collection_modifyitems(config, items):
    if _has_data():
        return
    skip = pytest.mark.skip(
        reason="нет данных Элемента – сгенерируйте tools/extract_grammar.py + extract_stdlib.py"
    )
    for item in items:
        module = getattr(item, "module", None)
        name = getattr(module, "__name__", "")
        if name in _DATA_DEPENDENT or item.get_closest_marker("needs_data"):
            item.add_marker(skip)
