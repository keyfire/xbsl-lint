"""Guard: the toolkit's published version has its own section in the changelog.

`xbsl.__version__` is the single source of the toolkit version (pyproject.toml reads it from
there). A release bumps it; the changelog must gain the matching `## X.Y.Z` section, or the
version ships with no record of what changed. The extension changelog learned this the hard way -
0.24.0 shipped without a section and nobody noticed until later (see the sibling guard in
test_metadata_sync.py), so the toolkit changelog gets the same guard, in both locales.

The toolkit changelog (CHANGELOG.md + .ru.md) is mirrored onto the documentation site by
scripts/sync-docs.mjs; guarding the source keeps the published page honest too.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

import xbsl

ROOT = Path(__file__).resolve().parent.parent


@pytest.mark.parametrize("name", ["CHANGELOG.md", "CHANGELOG.ru.md"])
def test_toolkit_version_is_described_in_changelog(name: str):
    version = xbsl.__version__
    text = (ROOT / name).read_text(encoding="utf-8")
    assert re.search(rf"^##\s+{re.escape(version)}\s*$", text, re.M), (
        f"{name}: нет раздела '## {version}' – версия тулкита поднята (xbsl/__init__.py), "
        "а история изменений о ней молчит"
    )
