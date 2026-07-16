"""Инвариант: реальный корпус проходит линтер без замечаний по умолчанию.

Тест пропускается, если корпус недоступен (переносимость).
Путь задаётся переменной окружения XBSL_CORPUS.
"""

import os
from pathlib import Path

import pytest

from xbsl import engine
from xbsl.cli import discover

_CORPUS = os.environ.get("XBSL_CORPUS")


# Правила, чьи находки на корпусе допустимы: это НАСТОЯЩИЕ находки, а не ложные.
# code/unused-loop-var – их же выдаёт серверная компиляция. Любое срабатывание ДРУГОГО
# правила на корпусе – признак ложного и должно ловиться этим тестом.
_KNOWN_FINDING_RULES = {"code/unused-loop-var"}


@pytest.mark.skipif(not (_CORPUS and Path(_CORPUS).exists()), reason="корпус недоступен (задайте XBSL_CORPUS)")
def test_corpus_no_errors_and_only_known_warnings():
    # Корпус – валидный задеплоенный код: ошибок линтера быть не должно.
    diags = engine.run(discover([str(_CORPUS)]))
    errors = [d for d in diags if d.severity.value == "error"]
    assert not errors, f"неожиданные ошибки: {[d.format() for d in errors[:5]]}"
    unexpected = [d for d in diags if d.rule_id not in _KNOWN_FINDING_RULES]
    assert not unexpected, f"неожиданные замечания: {[d.format() for d in unexpected[:5]]}"
