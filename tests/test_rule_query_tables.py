"""query/unknown-table: таблицы блоков Запрос{...} против объектов проекта."""

from xbsl import engine
from xbsl.cli import discover

_RULE = "query/unknown-table"


def _project(tmp_path, body):
    (tmp_path / "Товар.yaml").write_text(
        "ВидЭлемента: Справочник\n"
        "Имя: Товар\n"
        "ТабличныеЧасти:\n"
        "  - Имя: Цены\n",
        encoding="utf-8",
    )
    (tmp_path / "Остаток.yaml").write_text(
        "ВидЭлемента: РегистрСведений\nИмя: Остаток\n",
        encoding="utf-8",
    )
    (tmp_path / "Модуль.xbsl").write_text(body, encoding="utf-8")
    return engine.run(discover([str(tmp_path)]), select={_RULE})


def _query(inner):
    return (
        "метод Ф(): Число\n"
        "    знч Р = Запрос{\n"
        f"{inner}\n"
        "    }.Выполнить()\n"
        "    возврат 1\n"
        ";\n"
    )


def test_known_tables_are_silent(tmp_path):
    diags = _project(tmp_path, _query(
        "        ВЫБРАТЬ ПЕРВЫЕ 1 Т.Ссылка КАК Ссылка\n"
        "        ИЗ Товар КАК Т\n"
        "        ВНУТРЕННЕЕ СОЕДИНЕНИЕ Товар.Цены КАК Ц ПО Ц.Ссылка = Т.Ссылка\n"
        "        ГДЕ Т.Наименование = \"х\""
    ))
    assert diags == []


def test_unknown_bare_table(tmp_path):
    diags = _project(tmp_path, _query("        ВЫБРАТЬ 1 ИЗ Тавар"))
    assert len(diags) == 1
    assert "Тавар" in diags[0].message
    assert diags[0].rule_id == _RULE


def test_unknown_tabular_section(tmp_path):
    diags = _project(tmp_path, _query("        ВЫБРАТЬ 1 ИЗ Товар.Цены2 КАК Ц"))
    assert len(diags) == 1
    assert "Цены2" in diags[0].message and "Товар" in diags[0].message


def test_join_with_unknown_section(tmp_path):
    diags = _project(tmp_path, _query(
        "        ВЫБРАТЬ 1 ИЗ Товар КАК Т\n"
        "        СОЕДИНЕНИЕ Товар.Нет КАК Н ПО Н.Ссылка = Т.Ссылка"
    ))
    assert len(diags) == 1


def test_unknown_root_of_dotted_table_is_skipped(tmp_path):
    # корень не из проекта: возможно, объект внешней библиотеки - молчание
    diags = _project(tmp_path, _query("        ВЫБРАТЬ 1 ИЗ Библиотека.Таблица КАК Т"))
    assert diags == []


def test_virtual_table_is_skipped(tmp_path):
    diags = _project(tmp_path, _query("        ВЫБРАТЬ 1 ИЗ Остаток.СрезПоследних КАК С"))
    assert diags == []


def test_deep_chain_is_skipped(tmp_path):
    diags = _project(tmp_path, _query("        ВЫБРАТЬ 1 ИЗ Товар.Цены.Что КАК Т"))
    assert diags == []


def test_unsupported_block_is_skipped_whole(tmp_path):
    diags = _project(tmp_path, _query(
        "        ВЫБРАТЬ 1 ПОМЕСТИТЬ ВТ\n"
        "        ИЗ Тавар КАК Т"
    ))
    assert diags == []


def test_subquery_in_from_skips_block(tmp_path):
    diags = _project(tmp_path, _query(
        "        ВЫБРАТЬ 1 ИЗ (ВЫБРАТЬ 2 ИЗ Тавар) КАК Т"
    ))
    assert diags == []


def test_two_blocks_are_independent(tmp_path):
    body = (
        "метод А(): Число\n"
        "    знч Р = Запрос{ ВЫБРАТЬ 1 ПОМЕСТИТЬ ВТ ИЗ Тавар }.Выполнить()\n"
        "    возврат 1\n"
        ";\n"
        "метод Б(): Число\n"
        "    знч Р = Запрос{ ВЫБРАТЬ 1 ИЗ Нечто }.Выполнить()\n"
        "    возврат 1\n"
        ";\n"
    )
    diags = _project(tmp_path, body)
    assert len(diags) == 1 and "Нечто" in diags[0].message
