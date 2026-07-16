"""Совместимость: пакет переименован в `xbsl`, это имя осталось псевдонимом.

Импорт `xbsllint` (и любого подмодуля `xbsllint.X`) отдаёт ТОТ ЖЕ объект модуля, что и
`xbsl` / `xbsl.X`: finder ниже перехватывает имена `xbsllint*` и подкладывает уже
импортированные модули нового пакета. Общие объекты принципиальны – отдельная копия
модуля повторно выполнила бы регистрацию правил (@rule в xbsl.engine) и раздвоила
реестр. Новому коду импортировать `xbsl`.
"""

from __future__ import annotations

import importlib
import importlib.abc
import importlib.machinery
import sys

_PREFIX = "xbsllint"


class _AliasLoader(importlib.abc.Loader):
    """Возвращает существующий модуль xbsl.* вместо создания нового."""

    def __init__(self, target: str) -> None:
        self._target = target

    def create_module(self, spec):  # noqa: ANN001 - сигнатура протокола импорта
        return importlib.import_module(self._target)

    def exec_module(self, module) -> None:  # noqa: ANN001 - модуль уже выполнен
        pass


class _AliasFinder(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path=None, target=None):  # noqa: ANN001
        if fullname != _PREFIX and not fullname.startswith(_PREFIX + "."):
            return None
        if fullname.endswith(".__main__"):
            # runpy (python -m xbsllint) должен получить обычный спек с исходником:
            # штатный поиск найдёт xbsl/__main__.py через __path__ подменённого пакета.
            return None
        real = "xbsl" + fullname[len(_PREFIX):]
        return importlib.machinery.ModuleSpec(fullname, _AliasLoader(real))


if not any(isinstance(f, _AliasFinder) for f in sys.meta_path):
    sys.meta_path.insert(0, _AliasFinder())

# Сам пакет-псевдоним тоже подменяется на настоящий: `import xbsllint; xbsllint.engine`
# работает после `import xbsllint.engine` и атрибуты (__version__ и пр.) берутся из xbsl.
_real = importlib.import_module("xbsl")
sys.modules[__name__] = _real
