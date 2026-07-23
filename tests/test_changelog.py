"""Guard: the toolkit's published version has its own entry in the changelog.

`xbsl.__version__` is the single source of the toolkit version (pyproject.toml reads it from
there). A release bumps it; the changelog must gain a day heading that names the version, or the
version ships with no record of what changed. Headings are grouped by day and list the versions
released that day ("## 2026-07-22 – 0.28.0, 0.29.0, 0.30.0, 0.30.1"), so the guard looks for the
version as a whole token in any "## " heading rather than pinning one spelling. The extension
changelog carries the same discipline in test_metadata_sync.py.

The changelog (CHANGELOG.md + .ru.md) is mirrored onto the documentation site by
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
    headings = [
        line
        for line in (ROOT / name).read_text(encoding="utf-8").splitlines()
        if line.startswith("## ")
    ]
    token = re.compile(rf"(?<![\d.]){re.escape(version)}(?![\d.])")
    assert any(token.search(h) for h in headings), (
        f"{name}: версия {version} (xbsl.__version__) не встречается ни в одном заголовке '## ' – "
        "версия тулкита поднята, а история изменений о ней молчит"
    )
