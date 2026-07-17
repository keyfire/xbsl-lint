"""Правило security/hardcoded-secret: секрет в литерале против строки, которая на него похожа."""

from __future__ import annotations

import pytest

from xbsl import engine


def check(code: str) -> list:
    src = engine.load_text("Проба.xbsl", code)
    return engine.run_sources([src], select={"security/hardcoded-secret"}, scopes=("file",))


def messages(code: str) -> list[str]:
    return [d.message for d in check(code)]


pytestmark = pytest.mark.needs_data  # правило идёт по токенам – нужен каталог языка


# --------------------------------------------------------------------------- находки

def test_vendor_key_is_caught_by_its_prefix():
    # Ключ Яндекс SmartCaptcha, записанный в константу, - ровно то, что правило искало.
    (msg,) = messages('конст СерверныйКлючКапчи = "ysc2_Qw7Er9Ty2Ui4Op6As8Df1Gh3Jk5Lz0Xc7Vb9Nm2Qw4Er6Ty8"')
    assert "ysc2_" in msg and "SmartCaptcha" in msg


def test_vendor_key_fires_even_with_an_innocent_name():
    # Префикс вендора – доказательство сам по себе, имя переменной ни при чём.
    assert messages('знч Х = "AKIAIOSFODNN7EXAMPLE12"')


@pytest.mark.parametrize("code", [
    'конст АпиКлюч = "Zt4kQ9wLm2Xb7Nc5Vp8Rj3Hd6Fs1Gy0"',
    'знч Пароль = "Xy7Kd92Lm4Qw8Zr5Tn3Vb6Hs1"',
    'пер СекретКлиента = "aB3xY7zQ9mN2pL5kR8vT4wS6"',
    'знч ApiToken = "Kj8Hs2Ld9Xm4Qw7Zr3Nv6Tb1"',
])
def test_secret_name_plus_random_looking_value(code):
    assert messages(code), code


def test_the_finding_names_the_variable():
    (msg,) = messages('конст СерверныйКлюч = "Zt4kQ9wLm2Xb7Nc5Vp8Rj3Hd6Fs1Gy0"')
    assert "СерверныйКлюч" in msg


# ------------------------------------------------------- НЕ находки (ловушки живого кода)

def test_setting_name_is_not_a_secret():
    # Имя говорит "Ключ", а значение - имя параметра приложения, не сам ключ.
    assert not check('конст ИмяПараметраСерверногоКлюча = "СмартКапча.СерверныйКлюч"')


def test_secret_taken_from_settings_is_the_right_way():
    assert not check('знч Секрет = Параметры.ПолучитьПараметр(ИмяПараметраСерверногоКлюча)')


def test_interpolated_string_is_usage_not_a_value():
    # "secret=%{Секрет}&token=%СмартТокен" – это ПРИМЕНЕНИЕ секрета, ровно как надо.
    assert not check('знч Тело = "secret=%{Секрет}&token=%СмартТокен"')


@pytest.mark.parametrize("code", [
    'знч Урл = "https://smartcaptcha.yandexcloud.net/validate"',
    'знч ТипСодержимого = "application/x-www-form-urlencoded"',
    'знч Заголовок = "Content-Type"',
    'знч ИмяКлюча = "СмартКапча.СерверныйКлюч"',
])
def test_ordinary_strings_around_a_key_are_left_alone(code):
    assert not check(code), code


@pytest.mark.parametrize("value", [
    "xxxxxxxxxxxxxxxx",          # заглушка
    "changeme",
    "0000000000000000",
    "abcdefghijklmnopqrst",      # один регистр – не случайная строка
    "ABCDEFGHIJKLMNOPQRST",
    "1234567890123456",
])
def test_placeholders_and_flat_strings_are_not_secrets(value):
    assert not check(f'конст Ключ = "{value}"'), value


def test_short_value_is_not_a_secret():
    assert not check('конст Ключ = "Ab3Xy7Zq"')


def test_uuid_literal_is_not_a_secret():
    assert not check('конст КлючЗаписи = "109a9378-783f-48bd-a052-8a5edd30cb51"')


def test_word_containing_a_secret_word_does_not_count():
    # "Ключевая"/"Токенизация" – не про секреты; иначе правило кричало бы на пол-проекта.
    assert not check('знч КлючеваяСтавка = "Zt4kQ9wLm2Xb7Nc5Vp8Rj3Hd6Fs1Gy0"')


def test_yaml_is_not_checked():
    src = engine.load_text("Проба.yaml", 'Ключ: "ysc2_Qw7Er9Ty2Ui4Op6As8Df1Gh3Jk5Lz0Xc7Vb9Nm2Qw4Er6Ty8"')
    assert not engine.run_sources([src], select={"security/hardcoded-secret"}, scopes=("file",))
