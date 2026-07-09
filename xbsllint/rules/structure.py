"""Тир A: структурные проверки файлов (без разбора кода)."""

from __future__ import annotations

from collections.abc import Iterable

from xbsllint.diagnostics import Diagnostic, Severity
from xbsllint.engine import SourceFile, rule

# Модуль объекта пишется отдельным файлом `Имя.Объект.xbsl` (обработчики событий записи)
# и собственного .yaml не имеет – его описывает `Имя.yaml`.
_MODULE_SUFFIXES = ("Объект", "Object")


def _owner_yaml(source: SourceFile):
    """Файл описания, которому принадлежит модуль: для `Имя.Объект.xbsl` – это `Имя.yaml`."""
    stem = source.path.stem  # 'Полезное.Объект' или 'Полезное'
    base, _, suffix = stem.rpartition(".")
    if base and suffix in _MODULE_SUFFIXES:
        return source.path.with_name(base + ".yaml")
    return source.path.with_suffix(".yaml")


@rule("structure/xbsl-pair", "Модуль .xbsl без парного .yaml", "A", severity=Severity.WARNING)
def xbsl_pair(source: SourceFile) -> Iterable[Diagnostic]:
    # Модуль (.xbsl) – это код элемента, описанного парным .yaml. Одиночный .xbsl осиротел.
    # Проверка о файлах на диске: для контента в памяти (lint_source) парность не проверяем.
    if source.kind != "xbsl" or not source.path.exists():
        return
    yaml_path = _owner_yaml(source)
    if not yaml_path.exists():
        yield Diagnostic(
            source.rel, 1, 1, "structure/xbsl-pair", Severity.WARNING,
            f"Нет парного описания {yaml_path.name} для модуля.",
        )
