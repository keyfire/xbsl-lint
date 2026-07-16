"""Безопасное обновление установленного xbsl распаковкой колеса (`xbsl self-update`).

Штатный `pip install --upgrade` на Windows ломает установку, если один из exe пакета
занят работающим процессом (типовой случай: `xbsl-lsp.exe` держит LSP-сервер VS Code,
`xbsl-mcp.exe` – MCP-сессия агента): pip не может перезаписать точку входа, падает с
WinError 32 и оставляет пакет полуснесённым. Эта команда обновляет ТОЛЬКО содержимое
site-packages (файлы `.py` не блокируются, в отличие от `.exe`), а стабы в Scripts при
следующем запуске вызовут уже новый код. Занятые exe не трогаются.

Из колеса приходит и пакет xbsl, и пакет-псевдоним xbsllint – сносятся и заменяются оба.
dist-info переходного МЕТАпакета `xbsllint` (отдельная поставка без кода) не трогается.
Обновляется только сам xbsl, не его extras ([mcp]/[lsp] и их зависимости).

Качаем и распаковываем стандартной библиотекой (urllib + zipfile) – команда обязана
работать даже в установке без extras.
"""

from __future__ import annotations

import json
import shutil
import urllib.error
import urllib.request
import zipfile
from io import BytesIO
from pathlib import Path

from xbsl import __version__

PYPI_VERSION = "https://pypi.org/pypi/xbsl/{version}/json"
PYPI_LATEST = "https://pypi.org/pypi/xbsl/json"

# Что принадлежит колесу xbsl в site-packages. Шаблон xbsl-*.dist-info не заденет
# xbsllint-*.dist-info метапакета: glob сопоставляет префикс буквально.
_OWNED_PATTERNS = ("xbsl", "xbsllint", "xbsl-*.dist-info")


class SelfUpdateError(RuntimeError):
    """Ошибка самообновления; текст показывается пользователю как есть."""


def _site_packages() -> Path:
    """Каталог, куда установлен пакет (site-packages в боевой установке)."""
    return Path(__file__).resolve().parent.parent


def _ensure_regular_install(site: Path) -> None:
    """Гард от editable-установки: там обновляет git, а распаковка колеса испортила бы репозиторий."""
    if site.name.lower() not in ("site-packages", "dist-packages"):
        raise SelfUpdateError(
            f"пакет импортируется из {site} – это editable-установка из репозитория; "
            "обновляйте её через git (pip install -e не требуется повторно)"
        )


def _fetch_json(url: str) -> dict:
    try:
        with urllib.request.urlopen(url, timeout=30) as resp:
            return json.load(resp)
    except urllib.error.HTTPError as error:
        if error.code == 404:
            raise SelfUpdateError("версия не найдена на PyPI") from error
        raise SelfUpdateError(f"PyPI ответил {error.code}") from error
    except OSError as error:
        raise SelfUpdateError(f"не удалось обратиться к PyPI: {error}") from error


def _wheel_url(version: str | None) -> tuple[str, str]:
    """URL и точная версия колеса py3-none-any с PyPI (latest или указанной)."""
    data = _fetch_json(PYPI_VERSION.format(version=version) if version else PYPI_LATEST)
    resolved = data["info"]["version"]
    for entry in data["urls"]:
        if entry["filename"].endswith("-py3-none-any.whl"):
            return entry["url"], resolved
    raise SelfUpdateError(f"на PyPI нет wheel для xbsl {resolved}")


def self_update(version: str | None = None, log=print) -> tuple[str, str]:
    """Обновить xbsl в site-packages распаковкой колеса. Вернуть (было, стало)."""
    site = _site_packages()
    _ensure_regular_install(site)

    url, target = _wheel_url(version)
    if version is None and target == __version__:
        log(f"уже актуально: xbsl {__version__}")
        return __version__, __version__

    log(f"скачиваю xbsl {target} с PyPI...")
    try:
        with urllib.request.urlopen(url, timeout=60) as resp:
            blob = resp.read()
    except OSError as error:
        raise SelfUpdateError(f"не удалось скачать колесо: {error}") from error

    # Снести пакет, псевдоним и dist-info; exe в Scripts не трогаем (могут быть заняты).
    for pattern in _OWNED_PATTERNS:
        for path in site.glob(pattern):
            if path.is_dir():
                shutil.rmtree(path, ignore_errors=True)

    log(f"распаковываю в {site}...")
    with zipfile.ZipFile(BytesIO(blob)) as archive:
        archive.extractall(site)

    _update_pipx_metadata(site, target, log)
    log(
        f"готово: xbsl {__version__} -> {target}. Перезапустите долгоживущие процессы "
        "(LSP-сервер VS Code, MCP-сессии) – они продолжают работать на старом коде."
    )
    return __version__, target


def _update_pipx_metadata(site: Path, version: str, log) -> None:
    """Поправить package_version в pipx_metadata.json (иначе pipx list покажет старую версию)."""
    meta = site.parent.parent / "pipx_metadata.json"  # <venv>/Lib/site-packages -> <venv>
    if not meta.is_file():
        return
    try:
        data = json.loads(meta.read_text(encoding="utf-8"))
        main = data.get("main_package") or {}
        if main.get("package") == "xbsl":
            main["package_version"] = version
            meta.write_text(json.dumps(data, indent=4), encoding="utf-8")
            log("обновлён pipx_metadata.json")
    except (OSError, ValueError):
        pass
