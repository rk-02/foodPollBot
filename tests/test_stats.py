from datetime import date, timedelta

import pytest

from app import stats

pytestmark = pytest.mark.unit


# --- history migration -------------------------------------------

def test_migrate_history_rekeys_to_iso(storage, legacy_history):
    assert stats.migrate_history(storage, assume_year=2025) is True
    hist = storage.load_history()
    assert "2025-03-18" in hist["111"]
    assert hist["111"]["2025-03-18"]["Вторые блюда"] == "Гуляш"
    assert stats.migrate_history(storage, assume_year=2025) is False  # idempotent


def test_migrate_history_drops_unparseable(storage):
    storage.save_history({"1": {"garbage": {"Гарниры": "Рис"}, "2025-01-01": {"Гарниры": "Рис"}}})
    stats.migrate_history(storage, assume_year=2025)
    assert list(storage.load_history()["1"]) == ["2025-01-01"]


# --- poll-round gate ----------------------------------------

def test_usual_button_hidden_until_two_rounds_each_weekday(storage):
    assert stats.usual_button_ready(storage) is False
    for _ in range(2):
        for wd in range(5):
            stats.record_poll_round(storage, wd)
    assert stats.poll_rounds(storage) == {0: 2, 1: 2, 2: 2, 3: 2, 4: 2}
    assert stats.usual_button_ready(storage) is True


def test_usual_button_still_hidden_if_one_weekday_short(storage):
    for _ in range(2):
        for wd in range(4):          # skip weekday 4
            stats.record_poll_round(storage, wd)
    stats.record_poll_round(storage, 4)  # only 1 round for Friday
    assert stats.usual_button_ready(storage) is False


# --- usual_picks ------------------------------------------

def test_usual_picks_empty(storage):
    assert stats.usual_picks(storage, 42) == {
        "picks": {}, "weekday_records": 0, "enough": False, "fallbacks": [],
    }


def test_usual_picks_prefers_the_same_weekday(storage):
    # Wednesdays -> Гуляш ; other days -> Тефтели (should be ignored for Wed)
    hist = {}
    d = date(2026, 9, 2)  # a Wednesday
    for k in range(3):
        hist[(d - timedelta(weeks=k)).isoformat()] = {"Вторые блюда": "Гуляш"}
    for k in range(1, 4):
        hist[(d - timedelta(days=k)).isoformat()] = {"Вторые блюда": "Тефтели"}
    storage.save_history({"7": hist})

    res = stats.usual_picks(storage, 7, weekday=2, today=date(2026, 9, 9))
    assert res["picks"]["Вторые блюда"] == "Гуляш"
    assert res["weekday_records"] == 3
    assert res["enough"] is True


def test_usual_picks_falls_back_to_overall_when_favourite_not_in_menu(storage):
    d = date(2026, 9, 2)  # Wednesday
    hist = {}
    for k in range(3):
        hist[(d - timedelta(weeks=k)).isoformat()] = {"Гарниры": "Картофель фри"}
    # an all-days second choice
    hist[(d - timedelta(days=1)).isoformat()] = {"Гарниры": "Рис"}
    storage.save_history({"7": hist})

    available = {"Гарниры": ["Рис", "Гречка"]}  # "Картофель фри" not offered today
    res = stats.usual_picks(storage, 7, weekday=2, available=available, today=date(2026, 9, 9))
    assert res["picks"]["Гарниры"] == "Рис"
    assert res["fallbacks"] == ["Гарниры"]


def test_usual_picks_skips_category_with_no_usable_option(storage):
    d = date(2026, 9, 2)
    storage.save_history({"7": {d.isoformat(): {"Гарниры": "Экзотика"}}})
    available = {"Гарниры": ["Рис", "Гречка"]}
    res = stats.usual_picks(storage, 7, weekday=2, available=available, today=date(2026, 9, 9))
    assert "Гарниры" not in res["picks"]


def test_usual_picks_not_enough_same_weekday_records(storage):
    d = date(2026, 9, 2)
    storage.save_history({"7": {d.isoformat(): {"Вторые блюда": "Гуляш"}}})
    res = stats.usual_picks(storage, 7, weekday=2, today=date(2026, 9, 9))
    assert res["weekday_records"] == 1
    assert res["enough"] is False
    assert res["picks"]["Вторые блюда"] == "Гуляш"


def test_usual_picks_without_weekday_uses_all_history(storage):
    d = date(2026, 9, 8)
    storage.save_history({"7": {
        d.isoformat(): {"Салаты": "Зимний"},
        (d - timedelta(days=1)).isoformat(): {"Салаты": "Зимний"},
    }})
    res = stats.usual_picks(storage, 7, weekday=None, today=date(2026, 9, 9))
    assert res["picks"]["Салаты"] == "Зимний"


def test_usual_picks_ignores_bad_iso_values(storage):
    storage.save_history({"5": {"oops": {"Гарниры": "Рис"}}})
    assert stats.usual_picks(storage, 5) == {
        "picks": {}, "weekday_records": 0, "enough": False, "fallbacks": [],
    }


# --- record + format --------------------------------------

def test_record_orders_appends(storage):
    stats.record_orders(storage, "2026-09-10", {
        1: {"Вторые блюда": "Гуляш", "Гарниры": "Рис"},
        2: {"Первые блюда": ""},          # nothing real -> skipped
    })
    hist = storage.load_history()
    assert hist["1"]["2026-09-10"] == {"Вторые блюда": "Гуляш", "Гарниры": "Рис"}
    assert "2" not in hist


def test_format_picks():
    assert "ничего не выбирали" in stats.format_picks({})
    text = stats.format_picks({"Вторые блюда": "Гуляш", "Гарниры": "Рис"})
    assert text == "• Вторые блюда: Гуляш\n• Гарниры: Рис"
