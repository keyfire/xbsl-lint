"""Скаффолдинг метаданных (xbsl/scaffold.py): правки текста, шаблоны, операции.

Каждый сгенерированный yaml дополнительно прогоняется через PyYAML: шаблон, который
не разбирается парсером, не должен пройти тесты независимо от точечных проверок.
"""

from pathlib import Path

import pytest
import yaml as pyyaml

from xbsl import scaffold
from xbsl.scaffold import (
    ScaffoldError,
    TextEdit,
    apply_edit,
    apply_result,
    find_section_item_offset,
    insert_item_edit,
    insert_nested_item_edit,
    section_items,
)

CATALOG = """\
ВидЭлемента: Справочник
Ид: 6f0b6a44-0000-4000-8000-000000000001
Имя: Товары
ОбластьВидимости: ВПроекте
Реквизиты:
    -
        Ид: 6f0b6a44-0000-4000-8000-000000000002
        Имя: Артикул
        Тип: Строка
ТабличныеЧасти:
    -
        Ид: 6f0b6a44-0000-4000-8000-000000000003
        Имя: Состав
        Реквизиты:
            -
                Ид: 6f0b6a44-0000-4000-8000-000000000004
                Имя: Компонент
                Тип: Строка
"""


def _valid_yaml(text: str) -> object:
    return pyyaml.safe_load(text)


# --- правки текста -------------------------------------------------------------------


def test_insert_item_into_existing_section():
    edit = insert_item_edit(CATALOG, "Реквизиты", ["Ид: х", "Имя: Цвет", "Тип: Строка"])
    out = apply_edit(CATALOG, edit)
    names = [i["Имя"] for i in section_items(out, "Реквизиты")]
    assert names == ["Артикул", "Цвет"]
    # Вставка точечная: секция ТабличныеЧасти не сдвинулась по содержимому.
    assert out.count("ТабличныеЧасти:") == 1
    assert _valid_yaml(out)


def test_insert_item_creates_missing_section():
    text = "ВидЭлемента: Перечисление\nИмя: Статус\n"
    out = apply_edit(text, insert_item_edit(text, "Элементы", ["Ид: х", "Имя: Новый"]))
    assert [i["Имя"] for i in section_items(out, "Элементы")] == ["Новый"]
    assert _valid_yaml(out)


def test_insert_item_respects_crlf():
    text = CATALOG.replace("\n", "\r\n")
    edit = insert_item_edit(text, "Реквизиты", ["Имя: Цвет"], nl="\r\n")
    assert "\r\n" in edit.new_text and "\n\n" not in edit.new_text.replace("\r\n", "")


def test_insert_nested_item_into_tabular():
    offset = find_section_item_offset(CATALOG, "ТабличныеЧасти", "Состав")
    assert offset is not None
    edit = insert_nested_item_edit(CATALOG, offset, "Реквизиты", ["Имя: Количество", "Тип: Число"])
    out = apply_edit(CATALOG, edit)
    parsed = _valid_yaml(out)
    tc = parsed["ТабличныеЧасти"][0]
    assert [f["Имя"] for f in tc["Реквизиты"]] == ["Компонент", "Количество"]
    # Реквизиты верхнего уровня не пострадали.
    assert [i["Имя"] for i in section_items(out, "Реквизиты")] == ["Артикул"]


def test_section_items_inline_form():
    text = "Использование:\nЭлементы:\n    - Имя: Один\n    -\n        Имя: Два\n"
    assert [i["Имя"] for i in section_items(text, "Элементы")] == ["Один", "Два"]


# --- объекты ---------------------------------------------------------------------------


def test_new_object_catalog(tmp_path):
    result = scaffold.op_new_object(tmp_path, "Справочник", "Товары")
    written = apply_result(result)
    assert written == [str(tmp_path / "Товары.yaml")]
    text = (tmp_path / "Товары.yaml").read_text(encoding="utf-8")
    parsed = _valid_yaml(text)
    assert parsed["ВидЭлемента"] == "Справочник"
    assert parsed["ОбластьВидимости"] == "ВПроекте"
    assert parsed["Ид"]


def test_new_object_rejects_duplicates_and_bad_names(tmp_path):
    apply_result(scaffold.op_new_object(tmp_path, "Справочник", "Товары"))
    with pytest.raises(ScaffoldError, match="уже существует"):
        scaffold.op_new_object(tmp_path, "Справочник", "Товары")
    with pytest.raises(ScaffoldError, match="Недопустимое имя"):
        scaffold.op_new_object(tmp_path, "Справочник", "Плохое имя")
    with pytest.raises(ScaffoldError, match="не поддерживается"):
        scaffold.op_new_object(tmp_path, "НеВид", "Имя")


def test_new_common_module_with_environment(tmp_path):
    result = scaffold.op_new_object(
        tmp_path, "ОбщийМодуль", "Помощники", environment="КлиентИСервер"
    )
    apply_result(result)
    text = (tmp_path / "Помощники.yaml").read_text(encoding="utf-8")
    assert "Окружение: КлиентИСервер" in text
    assert (tmp_path / "Помощники.xbsl").is_file()


def test_new_object_access_control(tmp_path):
    apply_result(
        scaffold.op_new_object(tmp_path, "Справочник", "Заказы", access="РазрешеноАутентифицированным")
    )
    parsed = _valid_yaml((tmp_path / "Заказы.yaml").read_text(encoding="utf-8"))
    assert parsed["КонтрольДоступа"]["ПоУмолчанию"] == "РазрешеноАутентифицированным"


def test_new_http_service_routes(tmp_path):
    result = scaffold.op_new_object(
        tmp_path, "HttpСервис", "Каталог", access="РазрешеноВсем",
        routes="GET /, POST /, GET /{id}",
    )
    apply_result(result)
    text = (tmp_path / "Каталог.yaml").read_text(encoding="utf-8")
    parsed = _valid_yaml(text)
    templates = {t["Шаблон"]: t for t in parsed["ШаблоныUrl"]}
    assert set(templates) == {"/", "/{id}"}
    assert [m["Метод"] for m in templates["/"]["Методы"]] == ["GET", "POST"]
    module = (tmp_path / "Каталог.xbsl").read_text(encoding="utf-8")
    for handler in ("ПолучитьСписок", "Создать", "ПолучитьПоИд", "ОбработатьОшибку"):
        assert f"метод {handler}" in module


def test_http_handler_names_do_not_collide(tmp_path):
    result = scaffold.op_new_object(
        tmp_path, "HttpСервис", "Сервис", routes="GET /{id}, GET /{id}/items"
    )
    apply_result(result)
    parsed = _valid_yaml((tmp_path / "Сервис.yaml").read_text(encoding="utf-8"))
    handlers = [
        m["Обработчик"] for t in parsed["ШаблоныUrl"] for m in t["Методы"]
    ]
    assert len(handlers) == len(set(handlers))


def test_new_report_layout(tmp_path):
    result = scaffold.op_new_object(
        tmp_path, "Отчет", "Остатки",
        report={
            "source": "Регистр.Остатки",
            "rows": ["Номенклатура"],
            "columns": ["Склад"],
            "measures": [{"expr": "Количество", "title": "Количество"}],
        },
    )
    apply_result(result)
    parsed = _valid_yaml((tmp_path / "Остатки.yaml").read_text(encoding="utf-8"))
    fields = parsed["Макет"]["Поля"]
    kinds = [f["Вид"] for f in fields]
    assert kinds == ["Измерение", "Измерение", "Мера"]
    assert fields[2]["Выражение"] == "СУММА(Количество)"
    assert all(len(f["Ид"]) == 32 for f in fields)  # hex без дефисов

    with pytest.raises(ScaffoldError, match="источник"):
        scaffold.op_new_object(tmp_path, "Отчет", "Пустой")


# --- поля ------------------------------------------------------------------------------


@pytest.fixture()
def catalog_path(tmp_path) -> Path:
    path = tmp_path / "Товары.yaml"
    path.write_text(CATALOG, encoding="utf-8")
    return path


def test_add_field_attribute(catalog_path):
    result = scaffold.op_add_field(catalog_path, "реквизит", "Цвет", type_="Строка")
    apply_result(result)
    out = catalog_path.read_text(encoding="utf-8")
    items = section_items(out, "Реквизиты")
    assert [i["Имя"] for i in items] == ["Артикул", "Цвет"]
    assert len(items[1]["Ид"]) == 36
    assert _valid_yaml(out)


def test_add_field_rejects_duplicate_and_wrong_kind(catalog_path):
    with pytest.raises(ScaffoldError, match="уже есть"):
        scaffold.op_add_field(catalog_path, "реквизит", "Артикул")
    with pytest.raises(ScaffoldError, match="нет секции"):
        scaffold.op_add_field(catalog_path, "измерение", "Склад")
    with pytest.raises(ScaffoldError, match="Неизвестный вид"):
        scaffold.op_add_field(catalog_path, "колонка", "Икс")


def test_add_field_into_tabular(catalog_path):
    result = scaffold.op_add_field(
        catalog_path, "реквизит", "Количество", type_="Число", tabular="Состав"
    )
    apply_result(result)
    parsed = _valid_yaml(catalog_path.read_text(encoding="utf-8"))
    names = [f["Имя"] for f in parsed["ТабличныеЧасти"][0]["Реквизиты"]]
    assert names == ["Компонент", "Количество"]

    with pytest.raises(ScaffoldError, match="не найдена"):
        scaffold.op_add_field(catalog_path, "реквизит", "Х", tabular="Нет")


def test_add_tabular_with_starter_attribute(catalog_path):
    apply_result(scaffold.op_add_field(catalog_path, "табличная-часть", "Склады"))
    parsed = _valid_yaml(catalog_path.read_text(encoding="utf-8"))
    new_tc = parsed["ТабличныеЧасти"][1]
    assert new_tc["Имя"] == "Склады"
    assert new_tc["Реквизиты"][0]["Имя"] == "Реквизит1"


# --- подсистема и проект ----------------------------------------------------------------


def test_add_subsystem_blocks(tmp_path):
    apply_result(
        scaffold.op_add_subsystem(
            tmp_path, "Задачи", representation="Мои задачи", uses=["Основное"]
        )
    )
    text = (tmp_path / "Задачи" / "Подсистема.yaml").read_text(encoding="utf-8")
    parsed = _valid_yaml(text)
    assert parsed["Использование"] == ["Основное"]
    assert parsed["Интерфейс"]["Представление"] == "Мои задачи"


def test_new_project_files(tmp_path):
    result = scaffold.op_new_project(tmp_path, "vendor", "Приложение")
    apply_result(result)
    project_dir = tmp_path / "vendor" / "Приложение"
    parsed = _valid_yaml((project_dir / "Проект.yaml").read_text(encoding="utf-8"))
    assert parsed["Поставщик"] == "vendor"
    assert parsed["РежимСовместимости"] == 9.0 or str(parsed["РежимСовместимости"]) == "9.0"
    assert (project_dir / "Проект.xbsl").is_file()
    assert (project_dir / "Основное" / "Подсистема.yaml").is_file()

    with pytest.raises(ScaffoldError, match="уже существует"):
        scaffold.op_new_project(tmp_path, "vendor", "Приложение")


# --- маршруты в существующий сервис ------------------------------------------------------


def test_add_route_extends_service(tmp_path):
    apply_result(scaffold.op_new_object(tmp_path, "HttpСервис", "Апи", routes="GET /, GET /{id}"))
    yaml_path = tmp_path / "Апи.yaml"
    result = scaffold.op_add_route(yaml_path, "DELETE /{id}, GET /")
    apply_result(result)
    parsed = _valid_yaml(yaml_path.read_text(encoding="utf-8"))
    by_template = {t["Шаблон"]: [m["Метод"] for m in t["Методы"]] for t in parsed["ШаблоныUrl"]}
    assert by_template["/{id}"] == ["GET", "DELETE"]
    assert by_template["/"] == ["GET"]  # дубль не добавился
    assert any("уже есть" in note for note in result.notes)
    module = (tmp_path / "Апи.xbsl").read_text(encoding="utf-8")
    assert module.count("метод Удалить") == 1
    assert module.count("метод ОбработатьОшибку") == 1


def test_add_route_new_template(tmp_path):
    apply_result(scaffold.op_new_object(tmp_path, "HttpСервис", "Апи", routes="GET /"))
    apply_result(scaffold.op_add_route(tmp_path / "Апи.yaml", "GET /users"))
    parsed = _valid_yaml((tmp_path / "Апи.yaml").read_text(encoding="utf-8"))
    assert {t["Шаблон"] for t in parsed["ШаблоныUrl"]} == {"/", "/users"}


# --- формы -------------------------------------------------------------------------------


def _make_project(tmp_path) -> Path:
    """Мини-проект: vendor/Приложение/Основное с иерархией папок как в реальных исходниках."""
    apply_result(scaffold.op_new_project(tmp_path, "vendor", "Приложение"))
    return tmp_path / "vendor" / "Приложение" / "Основное"


def test_add_forms_for_catalog(tmp_path):
    subsystem = _make_project(tmp_path)
    apply_result(scaffold.op_new_object(subsystem, "Справочник", "Товары"))
    yaml_path = subsystem / "Товары.yaml"
    apply_result(scaffold.op_add_field(yaml_path, "реквизит", "Цвет"))
    apply_result(scaffold.op_add_field(yaml_path, "реквизит", "Вес", type_="Число"))

    result = scaffold.op_add_form(tmp_path, name="Товары")
    apply_result(result)

    form_obj = (subsystem / "ТоварыФормаОбъекта.yaml").read_text(encoding="utf-8")
    parsed = _valid_yaml(form_obj)
    assert parsed["Наследует"]["Тип"] == "ФормаОбъекта<Товары.Объект>"
    assert "ПолеВвода<Строка>" in form_obj and "Значение: =Объект.Наименование" in form_obj
    assert "Значение: =Объект.Вес" in form_obj

    form_list = (subsystem / "ТоварыФормаСписка.yaml").read_text(encoding="utf-8")
    parsed_list = _valid_yaml(form_list)
    ns_type = "ДинамическийСписок<vendor::Приложение::Основное::ТоварыФормаСписка.ДанныеСтрокиСписка>"
    assert parsed_list["Свойства"][0]["Тип"] == ns_type
    assert "Значение: =ДанныеСтроки.Данные.Наименование" in form_list

    owner = _valid_yaml(yaml_path.read_text(encoding="utf-8"))
    assert owner["Интерфейс"]["Объект"]["Форма"] == "ТоварыФормаОбъекта"
    assert owner["Интерфейс"]["Список"]["Форма"] == "ТоварыФормаСписка"
    assert owner["Интерфейс"]["ИспользоватьСозданиеПриВводе"] is True or owner["Интерфейс"]["ИспользоватьСозданиеПриВводе"] == "Истина"


def test_add_forms_skips_existing(tmp_path):
    subsystem = _make_project(tmp_path)
    apply_result(scaffold.op_new_object(subsystem, "Справочник", "Товары"))
    apply_result(scaffold.op_add_form(tmp_path, name="Товары"))
    repeat = scaffold.op_add_form(tmp_path, name="Товары")
    assert any("уже существует" in note for note in repeat.notes)
    assert not repeat.changes


def test_add_form_layout_with_tabulars(tmp_path):
    subsystem = _make_project(tmp_path)
    apply_result(scaffold.op_new_object(subsystem, "Документ", "Заказ"))
    yaml_path = subsystem / "Заказ.yaml"
    apply_result(scaffold.op_add_field(yaml_path, "табличная-часть", "Строки"))
    apply_result(scaffold.op_add_form(tmp_path, name="Заказ", forms=["object"]))
    form = (subsystem / "ЗаказФормаОбъекта.yaml").read_text(encoding="utf-8")
    assert "ШаблонФормыСРазделами" in form
    assert "Таблица<ИсточникДанныхМассив<Заказ.Строки>>" in form
    assert "=Компоненты.Строки.ДобавитьСтроку" in form
    assert _valid_yaml(form)
    # Стандартные реквизиты документа попали в форму, хоть их и нет в yaml.
    assert "Значение: =Объект.Номер" in form and "Значение: =Объект.Дата" in form


def test_add_report_form(tmp_path):
    subsystem = _make_project(tmp_path)
    apply_result(
        scaffold.op_new_object(
            subsystem, "Отчет", "Продажи",
            report={"source": "Заказы", "rows": ["Товар"], "measures": ["Сумма"]},
        )
    )
    apply_result(scaffold.op_add_form(tmp_path, name="Продажи"))
    form = (subsystem / "ПродажиФормаОтчета.yaml").read_text(encoding="utf-8")
    parsed = _valid_yaml(form)
    assert parsed["Наследует"]["Тип"] == "ФормаОтчета"
    owner = _valid_yaml((subsystem / "Продажи.yaml").read_text(encoding="utf-8"))
    assert owner["Интерфейс"]["Форма"] == "ПродажиФормаОтчета"


def test_hierarchical_list_form(tmp_path):
    subsystem = _make_project(tmp_path)
    apply_result(scaffold.op_new_object(subsystem, "Справочник", "Разделы"))
    yaml_path = subsystem / "Разделы.yaml"
    text = yaml_path.read_text(encoding="utf-8")
    yaml_path.write_text(text + "Иерархический: Истина\n", encoding="utf-8")
    apply_result(scaffold.op_add_form(tmp_path, name="Разделы", forms=["list"]))
    form = (subsystem / "РазделыФормаСписка.yaml").read_text(encoding="utf-8")
    row = "vendor::Приложение::Основное::РазделыФормаСписка.ДанныеСтрокиСписка"
    assert f"ДинамическийСписок<{row}, {row}>" in form
    assert "Значение: Иерархия" in form
    assert "Выражение: Родитель" in form
    assert _valid_yaml(form)


# --- разведка ----------------------------------------------------------------------------


def test_object_info_and_project_info(tmp_path):
    subsystem = _make_project(tmp_path)
    apply_result(scaffold.op_new_object(subsystem, "Справочник", "Товары"))
    apply_result(scaffold.op_add_field(subsystem / "Товары.yaml", "реквизит", "Цвет"))

    info = scaffold.object_info(tmp_path, name="Товары")
    assert info["kind"] == "Справочник"
    assert info["namespace"] == "vendor::Приложение::Основное"
    assert [f["name"] for f in info["fields"]] == ["Наименование", "Цвет"]
    assert info["suggested_layout"] == "simple"
    assert info["existing_forms"] == {"ФормаОбъекта": None, "ФормаСписка": None}

    overview = scaffold.project_info(tmp_path)
    assert overview["projects"][0]["name"] == "Приложение"
    assert any(o["name"] == "Товары" for o in overview["objects"])

    with pytest.raises(ScaffoldError, match="не найден"):
        scaffold.object_info(tmp_path, name="Нет")
