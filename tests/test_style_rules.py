"""Правила соглашений по написанию кода (CODE_STYLE, разделы 1-8).

У каждого правила проверяется и срабатывание на "плохом" примере, и молчание на "хорошем"
(примеры взяты из самого CODE_STYLE), а у правил-исключений – что исключение не ловится.
"""

from xbsl import engine


def _lint(content, rule_id, name="М.xbsl"):
    return engine.run_sources([engine.load_text(name, content)], select={rule_id})


def _clean(content, rule_id, name="М.xbsl"):
    return _lint(content, rule_id, name) == []


# --- 1. Оформление -------------------------------------------------------------------

def test_tab_indent_flagged():
    d = _lint("метод Ф()\n\tвозврат 1\n;\n", "style/tab-indent")
    assert len(d) == 1 and d[0].line == 2


def test_spaces_indent_ok():
    assert _clean("метод Ф()\n    возврат 1\n;\n", "style/tab-indent")


def test_tab_inside_string_literal_ok():
    assert _clean('метод Ф(): Строка\n    возврат "перенос\n\tи таб"\n;\n', "style/tab-indent")


def test_line_length_flagged():
    long_call = "    Вызвать(" + ", ".join(f"Параметр{i}" for i in range(15)) + ")\n"
    d = _lint("метод Ф()\n" + long_call + ";\n", "style/line-length")
    assert len(d) == 1 and d[0].severity.value == "info"


def test_line_length_string_literal_ok():
    literal = '    знч Разметка = "' + "x" * 200 + '"\n'
    assert _clean("метод Ф()\n" + literal + ";\n", "style/line-length")


def test_line_length_off_by_default():
    long_call = "    Вызвать(" + ", ".join(f"Параметр{i}" for i in range(15)) + ")\n"
    diags = engine.run_sources([engine.load_text("М.xbsl", "метод Ф()\n" + long_call + ";\n")])
    # Только про длину строки: вызов несуществующего метода в фикстуре честно ловит
    # code/undefined-name, он здесь не предмет проверки.
    assert [d for d in diags if d.rule_id == "style/line-length"] == []


def test_semicolon_on_own_line_ok():
    assert _clean("метод Ф()\n    Метод1()\n;\n", "style/semicolon-line")


def test_semicolon_after_statement_flagged():
    d = _lint("метод Ф()\n    Метод1();\n;\n", "style/semicolon-line")
    assert len(d) == 1 and d[0].line == 2


# --- 2. Именование -------------------------------------------------------------------

def test_lower_camel_case_flagged():
    d = _lint("метод Ф()\n    знч входящееСообщение = 1\n    возврат входящееСообщение\n;\n",
              "style/camel-case")
    assert len(d) == 1 and "входящееСообщение" in d[0].message


def test_underscore_in_name_flagged():
    d = _lint("метод Ф()\n    знч Степень_Важности = 1\n;\n", "style/camel-case")
    assert len(d) == 1 and "подчёркивание" in d[0].message.lower()


def test_upper_camel_case_ok():
    assert _clean("метод ВходящееСообщение()\n    знч Итог = 1\n;\n", "style/camel-case")


def test_structure_field_name_not_flagged():
    # имена полей задаёт контракт сериализации (ключи JSON) – их не проверяем
    content = "структура Токен\n    пер access_token: Строка\n    пер apptype_id: Число\n;\n"
    assert _clean(content, "style/camel-case")


def test_method_parameter_name_not_flagged():
    assert _clean("метод Ф(state: Строка)\n;\n", "style/camel-case")


def test_const_lower_case_flagged():
    d = _lint("конст ВерсияСервера = 1\n", "style/const-case")
    assert len(d) == 1 and "ВерсияСервера" in d[0].message


def test_const_upper_snake_ok():
    assert _clean("конст ВЕРСИЯ_СЕРВЕРА = 1\n", "style/const-case")


def test_exception_without_prefix_flagged():
    d = _lint("исключение ЧтениеФайла\n;\n", "style/exception-prefix")
    assert len(d) == 1 and "ИсключениеЧтениеФайла" in d[0].message


def test_exception_with_prefix_ok():
    assert _clean("исключение ИсключениеЧтенияФайла\n;\n", "style/exception-prefix")


def test_abbreviation_uppercase_flagged():
    d = _lint("метод ТелоJSON(): Строка\n    возврат \"\"\n;\n", "style/abbreviation-case")
    assert len(d) == 1 and "ТелоJson" in d[0].message


def test_abbreviation_camel_ok():
    assert _clean("метод ТелоJson(): Строка\n    возврат \"\"\n;\n", "style/abbreviation-case")


def test_abbreviation_only_in_declarations():
    # обращение к чужому имени с аббревиатурой – не наше дело
    assert _clean("метод Ф()\n    Клиент.ОтправитьJSON()\n;\n", "style/abbreviation-case")


def test_abbreviation_in_parameter_flagged():
    d = _lint("метод Ф(ТелоJSON: Строка)\n;\n", "style/abbreviation-case")
    assert len(d) == 1 and "ТелоJson" in d[0].message


def test_enum_named_tip_flagged():
    d = _lint("перечисление ТипКнопки\n    Да\n;\n", "style/enum-name-vid")
    assert len(d) == 1 and "ВидКнопки" in d[0].message


def test_enum_named_vid_ok():
    assert _clean("перечисление ВидКнопки\n    Да\n;\n", "style/enum-name-vid")


# --- 3. Типы и инициализация ---------------------------------------------------------

def test_space_before_type_colon_flagged():
    d = _lint('метод Ф()\n    пер Переменная1 : Строка = ""\n;\n', "style/type-colon-space")
    assert len(d) == 1 and "перед" in d[0].message


def test_no_space_after_type_colon_flagged():
    d = _lint('метод Ф()\n    пер Переменная1:Строка = ""\n;\n', "style/type-colon-space")
    assert len(d) == 1 and "после" in d[0].message


def test_type_colon_ok():
    assert _clean('метод Ф()\n    пер Переменная1: Строка = Знач()\n;\n', "style/type-colon-space")


def test_ternary_colon_not_type_colon():
    content = 'метод Ф(А: Булево): Строка\n    возврат (А ? "да" : "нет")\n;\n'
    assert _clean(content, "style/type-colon-space")


def test_union_spaces_flagged():
    d = _lint("метод Ф(): Строка | Число\n;\n", "style/union-spaces")
    assert len(d) == 1


def test_union_without_spaces_ok():
    assert _clean("метод Ф(): Строка|Число|Булево\n;\n", "style/union-spaces")


def test_undefined_in_union_flagged():
    d = _lint("метод Ф(): Строка|Неопределено\n;\n", "style/nullable-shorthand")
    assert len(d) == 1 and "сокращением" in d[0].message


def test_pipe_question_for_two_types_flagged():
    d = _lint("метод Ф(): Строка|?\n;\n", "style/nullable-shorthand")
    assert len(d) == 1 and "слитно" in d[0].message


def test_question_on_last_type_flagged():
    d = _lint("метод Ф(): Строка|Число?\n;\n", "style/nullable-shorthand")
    assert len(d) == 1 and "'...|?'" in d[0].message


def test_nullable_shorthand_ok():
    assert _clean("метод Ф(): Строка?\n;\n", "style/nullable-shorthand")
    assert _clean("метод Ф(): Строка|Число|?\n;\n", "style/nullable-shorthand")


def test_redundant_type_on_literal_flagged():
    d = _lint('метод Ф()\n    пер Переменная1: Строка = "значение"\n;\n', "style/redundant-type")
    assert len(d) == 1


def test_redundant_type_on_constructor_flagged():
    d = _lint(
        "метод Ф()\n    пер Настройки: Массив<Объект> = новый Массив<Объект>()\n;\n",
        "style/redundant-type",
    )
    assert len(d) == 1


def test_type_for_empty_literal_ok():
    # исключение проекта: для пустого литерала вывод типа невозможен
    assert _clean("метод Ф()\n    пер Результат: Массив<Сводка> = []\n;\n", "style/redundant-type")


def test_nullable_annotation_with_literal_ok():
    assert _clean('метод Ф()\n    пер Х: Строка? = ""\n;\n', "style/redundant-type")


def test_wider_annotation_with_literal_ok():
    assert _clean("метод Ф()\n    пер Х: Строка|Число = 0\n;\n", "style/redundant-type")


def test_no_annotation_ok():
    assert _clean('метод Ф()\n    пер Переменная1 = "значение"\n;\n', "style/redundant-type")


# --- 4. Коллекции --------------------------------------------------------------------

def test_manual_collection_fill_flagged():
    content = (
        "метод Ф(): Массив<Число>\n"
        "    пер Кнопки = новый Массив<Число>()\n"
        "    Кнопки.Добавить(1)\n"
        "    Кнопки.Добавить(2)\n"
        "    возврат Кнопки\n"
        ";\n"
    )
    d = _lint(content, "style/collection-literal")
    assert len(d) == 1 and "Кнопки" in d[0].message


def test_collection_fill_in_loop_ok():
    content = (
        "метод Ф(): Массив<Строка>\n"
        "    пер Тексты = новый Массив<Строка>()\n"
        "    для Счетчик = 1 по 3\n"
        '        Тексты.Добавить("текст")\n'
        "    ;\n"
        "    возврат Тексты\n"
        ";\n"
    )
    assert _clean(content, "style/collection-literal")


def test_collection_literal_ok():
    content = "метод Ф(): Массив<Число>\n    возврат [1, 2, 3]\n;\n"
    assert _clean(content, "style/collection-literal")


# --- 5. Строки -----------------------------------------------------------------------

def test_tostring_in_concat_flagged():
    d = _lint('метод Ф()\n    знч Р = "Итерация №" + Счетчик.ВСтроку()\n;\n', "style/redundant-tostring")
    assert len(d) == 1


def test_tostring_without_concat_ok():
    assert _clean("метод Ф(): Строка\n    возврат Счетчик.ВСтроку()\n;\n", "style/redundant-tostring")


def test_concat_with_value_flagged():
    d = _lint('метод Ф()\n    знч Р = "Итерация №" + Счетчик\n;\n', "style/interpolation")
    assert len(d) == 1


def test_concat_chain_reported_once():
    d = _lint('метод Ф()\n    знч Р = "а" + Х + "б" + У\n;\n', "style/interpolation")
    assert len(d) == 1


def test_concat_of_two_literals_ok():
    assert _clean('метод Ф()\n    знч Р = "начало "\n        + "продолжение"\n;\n', "style/interpolation")


def test_interpolation_ok():
    assert _clean('метод Ф()\n    знч Р = "Итерация №%Счетчик из %Всего"\n;\n', "style/interpolation")


# --- 6. Переносы ---------------------------------------------------------------------

def test_operator_at_line_end_flagged():
    content = (
        "метод Ф(П1: Число, П2: Число): Булево\n"
        "    если П1 > 5 или\n"
        "        П2 < 3\n"
        "        возврат Истина\n"
        "    ;\n"
        "    возврат Ложь\n"
        ";\n"
    )
    d = _lint(content, "style/wrap-operator")
    assert len(d) == 1 and d[0].line == 2


def test_operator_at_line_start_ok():
    content = (
        "метод Ф(П1: Число, П2: Число): Булево\n"
        "    если П1 > 5\n"
        "        или П2 < 3\n"
        "        возврат Истина\n"
        "    ;\n"
        "    возврат Ложь\n"
        ";\n"
    )
    assert _clean(content, "style/wrap-operator")


def test_plus_at_line_end_ok():
    # исключение: при конкатенации '+' допускается в конце строки
    content = 'метод Ф(): Строка\n    возврат "начало " +\n        "продолжение"\n;\n'
    assert _clean(content, "style/wrap-operator")


def test_comma_at_line_start_flagged():
    content = "метод Ф()\n    Массив.Добавить(Параметр1\n        , Параметр2)\n;\n"
    d = _lint(content, "style/wrap-comma")
    assert len(d) == 1 and d[0].line == 3


def test_comma_at_line_end_ok():
    content = "метод Ф()\n    Массив.Добавить(Параметр1,\n        Параметр2)\n;\n"
    assert _clean(content, "style/wrap-comma")


# --- 7. Методы -----------------------------------------------------------------------

def test_required_after_optional_param_flagged():
    d = _lint('метод НовоеСообщение(Дата = "", Вид: Строка)\n;\n', "style/optional-params-last")
    assert len(d) == 1 and "Вид" in d[0].message


def test_optional_params_last_ok():
    assert _clean('метод НовоеСообщение(Вид: Строка, Дата = "")\n;\n', "style/optional-params-last")


# --- 8. Условия и проверки -----------------------------------------------------------

def test_compare_with_true_flagged():
    d = _lint("метод Ф(Флаг: Булево)\n    если Флаг == Истина\n        Метод1()\n    ;\n;\n",
              "style/boolean-compare")
    assert len(d) == 1 and "nullable" in d[0].message


def test_boolean_check_without_compare_ok():
    assert _clean("метод Ф(Флаг: Булево)\n    если не Флаг\n        Метод1()\n    ;\n;\n",
                  "style/boolean-compare")


def test_is_undefined_flagged():
    d = _lint("метод Ф(Значение: Строка?)\n    если Значение это Неопределено\n        Метод1()\n    ;\n;\n",
              "style/undefined-is")
    assert len(d) == 1 and "== Неопределено" in d[0].message


def test_is_not_undefined_flagged():
    d = _lint("метод Ф(Значение: Строка?)\n    если Значение это не Неопределено\n        Метод1()\n    ;\n;\n",
              "style/undefined-is")
    assert len(d) == 1 and "!= Неопределено" in d[0].message


def test_compare_with_undefined_ok():
    assert _clean("метод Ф(Значение: Строка?)\n    если Значение != Неопределено\n        Метод1()\n    ;\n;\n",
                  "style/undefined-is")


def test_is_type_not_flagged_by_undefined_rule():
    assert _clean("метод Ф(Значение: Объект)\n    если Значение это Строка\n        Метод1()\n    ;\n;\n",
                  "style/undefined-is")


def test_outer_negation_of_is_flagged():
    d = _lint("метод Ф(Значение: Объект)\n    если не (Значение это Строка)\n        Метод1()\n    ;\n;\n",
              "style/negated-is")
    assert len(d) == 1


def test_inner_negation_of_is_ok():
    assert _clean("метод Ф(Значение: Объект)\n    если Значение это не Строка\n        Метод1()\n    ;\n;\n",
                  "style/negated-is")


def test_compound_negation_not_flagged():
    content = (
        "метод Ф(Значение: Объект, Флаг: Булево)\n"
        "    если не (Значение это Строка и Флаг)\n"
        "        Метод1()\n"
        "    ;\n"
        ";\n"
    )
    assert _clean(content, "style/negated-is")


# --- Область действия: блоки Запрос{...} ---------------------------------------------

def test_select_by_group():
    # группа правил – часть id до '/': --select style включает все соглашения сразу
    content = 'метод Ф()\n    пер Переменная1 : Строка = ""\n;\n'
    d = engine.run_sources([engine.load_text("М.xbsl", content)], select={"style"})
    assert {x.rule_id for x in d} >= {"style/type-colon-space", "style/redundant-type"}


def test_query_block_excluded_from_code_rules():
    long_condition = " или ".join(f"Поле{i} == 1" for i in range(12))
    content = (
        "метод Ф()\n"
        "    знч З = Запрос{\n"
        "        ВЫБРАТЬ Поле ИЗ Таблица ГДЕ " + long_condition + " или\n"
        "            Поле13 == 2\n"
        "    }\n"
        ";\n"
    )
    assert _clean(content, "style/wrap-operator")
    assert _clean(content, "style/line-length")
