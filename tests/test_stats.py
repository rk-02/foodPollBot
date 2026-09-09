from datetime import date, timedelta

import pytest

from app import stats


@pytest.mark.unit
def test_migrate_history_rekeys_to_iso(storage, legacy_history):
    assert stats.migrate_history(storage, assume_year=2025) is True
    hist = storage.load_history()
    assert "2025-03-18" in hist["111"]
    assert hist["111"]["2025-03-18"]["Вторые блюда"] == "Гуляш"
    # idempotent
    assert stats.migrate_history(storage, assume_year=2025) is False


@pytest.mark.unit
def test_migrate_history_drops_unparseable(storage):
    storage.save_history({"1": {"garbage": {"Гарниры": "Рис"}, "2025-01-01": {"Гарниры": "Рис"}}})
    stats.migrate_history(storage, assume_year=2025)
    assert list(storage.load_history()["1"]) == ["2025-01-01"]


@pytest.mark.unit
def test_usual_picks_empty(storage):
    res = stats.usual_picks(storage, 42)
    assert res == {"enough": False, "picks": {}, "span_days": 0, "records": 0, "counts": {}}


@pytest.mark.unit
def test_usual_picks_not_enough_data(storage):
    today = date(2026, 9, 9)
    storage.save_history({"7": {
        (today - timedelta(days=3)).isoformat(): {"Вторые блюда": "Гуляш", "Гарниры": "Рис"},
        (today - timedelta(days=1)).isoformat(): {"Вторые блюда": "Гуляш", "Гарниры": "Гречка"},
    }})
    res = stats.usual_picks(storage, 7, today)
    assert res["enough"] is False
    assert res["span_days"] == 2
    assert res["picks"]["Вторые блюда"] == "Гуляш"     # 2x Гуляш
    assert res["picks"]["Гарниры"] in {"Рис", "Гречка"}  # tie -> first seen


@pytest.mark.unit
def test_usual_picks_enough_data_and_window(storage):
    today = date(2026, 9, 9)
    hist = {
        # old, outside the 28-day window -> ignored for the pick itself
        "2026-01-01": {"Вторые блюда": "Тефтели", "Гарниры": "Пюре"},
    }
    for d in range(20, 0, -2):
        hist[(today - timedelta(days=d)).isoformat()] = {
            "Вторые блюда": "Гуляш", "Гарниры": "Рис", "Первые блюда": "Щи",
        }
    storage.save_history({"9": hist})
    res = stats.usual_picks(storage, 9, today)
    assert res["enough"] is True                       # span 251 days
    assert res["picks"]["Вторые блюда"] == "Гуляш"
    assert res["picks"]["Гарниры"] == "Рис"
    assert "Тефтели" not in res["counts"].get("Вторые блюда", {})


@pytest.mark.unit
def test_record_orders_appends(storage):
    stats.record_orders(storage, "2026-09-10", {
        1: {"Вторые блюда": "Гуляш", "Гарниры": "Рис"},
        2: {"Первые блюда": ""},          # nothing real -> skipped
    })
    hist = storage.load_history()
    assert hist["1"]["2026-09-10"] == {"Вторые блюда": "Гуляш", "Гарниры": "Рис"}
    assert "2" not in hist


@pytest.mark.unit
def test_format_picks():
    assert "ничего не выбирали" in stats.format_picks({})
    text = stats.format_picks({"Вторые блюда": "Гуляш", "Гарниры": "Рис"})
    assert text == "• Вторые блюда: Гуляш\n• Гарниры: Рис"
