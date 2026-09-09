import pytest

from app import menu_config
from app.config import CATEGORIES, DEFAULT_POLL_TIME


@pytest.mark.unit
@pytest.mark.parametrize("text,expected", [
    ("12:00", (12, 0)),
    (" 9:05 ", (9, 5)),
    ("23.59", (23, 59)),
    ("8 30", (8, 30)),
    ("24:00", None),
    ("12:60", None),
    ("noon", None),
    ("", None),
])
def test_parse_time(text, expected):
    assert menu_config.parse_time(text) == expected


@pytest.mark.unit
def test_poll_time_defaults_then_persists(storage):
    assert menu_config.get_poll_time_str(storage) == DEFAULT_POLL_TIME
    assert menu_config.set_poll_time(storage, "07:45") is True
    assert menu_config.get_poll_time_str(storage) == "07:45"
    assert menu_config.get_poll_time(storage) == (7, 45)
    assert menu_config.set_poll_time(storage, "bogus") is False
    assert menu_config.get_poll_time_str(storage) == "07:45"


@pytest.mark.unit
def test_get_day_menu_falls_back_to_schedule(storage):
    menu = menu_config.get_day_menu(storage, 0)
    assert set(menu) == set(CATEGORIES)
    assert "Куриный" in menu["Первые блюда"]  # from schedule.json row 0


@pytest.mark.unit
def test_set_day_category_overrides_and_dedupes(storage):
    menu_config.set_day_category(storage, 1, "Гарниры", ["Рис", " рис ", "Гречка", ""])
    menu = menu_config.get_day_menu(storage, 1)
    assert menu["Гарниры"] == ["Рис", "Гречка"]
    # other categories still come from the template
    assert menu["Первые блюда"]


@pytest.mark.unit
def test_set_day_category_rejects_unknown(storage):
    with pytest.raises(ValueError):
        menu_config.set_day_category(storage, 0, "Десерты", ["Торт"])


@pytest.mark.unit
def test_sync_from_schedule_rebuilds_menu_and_extends_dishes(storage):
    from app import dishes

    menu_config.set_day_category(storage, 0, "Первые блюда", ["ВыдуманныйСуп"])
    dishes.remove_dish(storage, "Первые блюда", "Щи")

    menu = menu_config.sync_from_schedule(storage)

    assert set(menu) == {"0", "1", "2", "3", "4"}
    # override wiped by the sync
    assert "ВыдуманныйСуп" not in menu_config.get_day_menu(storage, 0)["Первые блюда"]
    # dish DB re-extended from the template
    assert "Щи" in dishes.list_dishes(storage, "Первые блюда")
