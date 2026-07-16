"""Совместимость после переименования пакета xbsllint -> xbsl.

Старое имя обязано остаться рабочим псевдонимом: импорт xbsllint (и подмодулей) отдаёт
те же объекты модулей, что и xbsl, старые переменные окружения читаются как запасные,
старые группы entry-points сканируются наравне с новыми. Отдельная копия модулей была бы
ошибкой – продублировала бы реестр правил, поэтому проверяем именно тождество объектов.
"""

import sys

from xbsl import dataset, i18n, plugins


def test_alias_package_is_same_module():
    import xbsl
    import xbsllint

    assert xbsllint is xbsl
    assert xbsllint.__version__ == xbsl.__version__


def test_alias_submodule_identity():
    import xbsl.engine
    import xbsllint.engine

    assert xbsllint.engine is xbsl.engine
    # И привычная форма from-import тоже отдаёт те же объекты.
    from xbsllint.engine import RULES as legacy_rules

    assert legacy_rules is xbsl.engine.RULES
    assert sys.modules["xbsllint.engine"] is sys.modules["xbsl.engine"]


def test_legacy_lang_env(monkeypatch):
    monkeypatch.delenv("XBSL_LANG", raising=False)
    monkeypatch.setenv("XBSLLINT_LANG", "en")
    i18n.set_lang(None)
    try:
        assert i18n.current_lang() == "en"
    finally:
        i18n.set_lang("ru")  # тесты других модулей сверяют русский текст


def test_new_lang_env_wins(monkeypatch):
    monkeypatch.setenv("XBSL_LANG", "ru")
    monkeypatch.setenv("XBSLLINT_LANG", "en")
    i18n.set_lang(None)
    try:
        assert i18n.current_lang() == "ru"
    finally:
        i18n.set_lang("ru")


def test_legacy_data_dir_env(tmp_path, monkeypatch):
    monkeypatch.delenv("XBSL_DATA_DIR", raising=False)
    monkeypatch.setenv("XBSLLINT_DATA_DIR", str(tmp_path))
    dataset.set_data_root(None)
    assert dataset.data_root() == tmp_path


def test_legacy_no_plugins_env(monkeypatch):
    monkeypatch.delenv("XBSL_NO_PLUGINS", raising=False)
    monkeypatch.setenv("XBSLLINT_NO_PLUGINS", "1")
    assert plugins.disabled()
    # Новое имя приоритетнее: явное "0" в нём отменяет легаси-единицу.
    monkeypatch.setenv("XBSL_NO_PLUGINS", "0")
    assert not plugins.disabled()


class _StubEP:
    def __init__(self, name, group, value="stub"):
        self.name = name
        self.group = group
        self.value = value

    def load(self):
        return lambda: None


def test_legacy_entry_point_group_scanned(monkeypatch):
    monkeypatch.delenv("XBSL_NO_PLUGINS", raising=False)
    monkeypatch.delenv("XBSLLINT_NO_PLUGINS", raising=False)
    new_ep = _StubEP("а-новый", "xbsl.rules")
    legacy_ep = _StubEP("б-старый", "xbsllint.rules")
    monkeypatch.setattr(
        plugins, "entry_points", lambda group: [ep for ep in (new_ep, legacy_ep) if ep.group == group]
    )
    assert [ep.name for ep in plugins._points(plugins.RULES_GROUP)] == ["а-новый", "б-старый"]


def test_legacy_group_deduplicated(monkeypatch):
    # Пакет переходного периода объявляет одну и ту же цель в обеих группах – грузим один раз.
    monkeypatch.delenv("XBSL_NO_PLUGINS", raising=False)
    monkeypatch.delenv("XBSLLINT_NO_PLUGINS", raising=False)
    new_ep = _StubEP("пакет", "xbsl.rules", value="pkg.rules")
    legacy_ep = _StubEP("пакет", "xbsllint.rules", value="pkg.rules")
    monkeypatch.setattr(
        plugins, "entry_points", lambda group: [ep for ep in (new_ep, legacy_ep) if ep.group == group]
    )
    assert plugins._points(plugins.RULES_GROUP) == [new_ep]
