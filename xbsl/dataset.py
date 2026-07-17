"""Versioned access to the language and type data (self-contained, no distribution needed).

The data lives in <root>/<version>/{language.json, stdlib.json, metamodel.json}, and
<root>/index.json holds the list of available versions and the default one.

The data root is chosen by: set_data_root() (CLI --data-dir) > env XBSL_DATA_DIR >
a root from the "xbsl.data" entry point > a directory inside the package (xbsl/data/element).
An external root is for those who cannot publish the data with the package: the data is
extracted from their own distribution and supplied by a separate package (see xbsl/plugins.py).

The version is chosen by: an explicit argument/set_version > env XBSL_ELEMENT_VERSION >
the index default.
"""

from __future__ import annotations

import json
import os
from functools import lru_cache
from pathlib import Path

from xbsl import i18n, plugins

BUNDLED_DATA_ROOT = Path(__file__).parent / "data" / "element"
_ENV_VERSION = "XBSL_ELEMENT_VERSION"
_ENV_DATA_DIR = "XBSL_DATA_DIR"
# The pre-rename variable names keep working (checked after the new ones).
_ENV_VERSION_LEGACY = "XBSLLINT_ELEMENT_VERSION"
_ENV_DATA_DIR_LEGACY = "XBSLLINT_DATA_DIR"


def _env(name: str, legacy: str) -> str | None:
    return os.environ.get(name) or os.environ.get(legacy)

_selected: str | None = None
_root_override: Path | None = None

_MESSAGES = {
    "dataset.no-index": {
        "ru": "Нет индекса версий данных: {idx}. Сгенерируйте данные через tools/extract_*.py "
              "или укажите готовый корень: --data-dir / env {env}.",
        "en": "No data version index: {idx}. Generate the data via tools/extract_*.py "
              "or point at a ready root: --data-dir / env {env}.",
    },
    "dataset.no-default": {
        "ru": "В индексе версий не задан default",
        "en": "The version index has no default",
    },
    "dataset.version-unavailable": {
        "ru": "Версия данных '{version}' недоступна. Доступны: {available}",
        "en": "Data version '{version}' is unavailable. Available: {available}",
    },
    "dataset.no-file": {
        "ru": "Нет файла данных '{name}' для версии {version}: {path}",
        "en": "No data file '{name}' for version {version}: {path}",
    },
}
i18n.register(_MESSAGES)


class DatasetError(RuntimeError):
    pass


def set_data_root(path: str | os.PathLike[str] | None) -> None:
    """Pin the data root for the process (CLI --data-dir). Clears the cache."""
    global _root_override
    _root_override = Path(path) if path is not None else None
    _load_cached.cache_clear()


def data_root() -> Path:
    """The effective data root, by priority order (see the module description)."""
    if _root_override is not None:
        return _root_override
    env = _env(_ENV_DATA_DIR, _ENV_DATA_DIR_LEGACY)
    if env:
        return Path(env)
    for root in plugins.data_roots():
        if (root / "index.json").exists():
            return root
    return BUNDLED_DATA_ROOT


def data_root_source() -> str:
    """Where the data root came from (for the --where diagnostic): CLI / env / plugin / bundle."""
    if _root_override is not None:
        return "--data-dir"
    if _env(_ENV_DATA_DIR, _ENV_DATA_DIR_LEGACY):
        return f"env {_ENV_DATA_DIR}"
    for root in plugins.data_roots():
        if (root / "index.json").exists():
            return "плагин (точка расширения xbsl.data)"
    return "встроенные данные пакета"


def _read_index() -> dict:
    idx = data_root() / "index.json"
    if not idx.exists():
        raise DatasetError(i18n.t("dataset.no-index", idx=idx, env=_ENV_DATA_DIR))
    return json.loads(idx.read_text(encoding="utf-8"))


def available_versions() -> list[str]:
    try:
        return list(_read_index().get("available", []))
    except DatasetError:
        return []


def default_version() -> str:
    version = _read_index().get("default")
    if not version:
        raise DatasetError(i18n.t("dataset.no-default"))
    return version


def set_version(version: str | None) -> None:
    """Pin the data version for the process (CLI --element-version). Clears the cache."""
    global _selected
    _selected = version
    _load_cached.cache_clear()


def resolve_version(override: str | None = None) -> str:
    version = override or _selected or _env(_ENV_VERSION, _ENV_VERSION_LEGACY) or default_version()
    avail = available_versions()
    if version not in avail:
        raise DatasetError(
            i18n.t("dataset.version-unavailable", version=version, available=", ".join(avail) or "–")
        )
    return version


# The root is part of the cache key: otherwise switching roots would return data read from the old one.
@lru_cache(maxsize=None)
def _load_cached(root: str, version: str, name: str) -> dict:
    path = Path(root) / version / name
    if not path.exists():
        raise DatasetError(i18n.t("dataset.no-file", name=name, version=version, path=path))
    return json.loads(path.read_text(encoding="utf-8"))


def load_json(name: str, version: str | None = None) -> dict:
    return _load_cached(str(data_root()), resolve_version(version), name)


def data_file(name: str, version: str | None = None) -> Path:
    """Path to a data file of the version (for non-JSON files: docs.sqlite etc.). Raises when the file is missing."""
    ver = resolve_version(version)
    path = data_root() / ver / name
    if not path.exists():
        raise DatasetError(i18n.t("dataset.no-file", name=name, version=ver, path=path))
    return path


def has_data_file(name: str, version: str | None = None) -> bool:
    """Whether the data file exists (no exception) - for optional data such as the documentation."""
    try:
        return data_file(name, version).exists()
    except DatasetError:
        return False
