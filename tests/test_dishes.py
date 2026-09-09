import pytest

from app import dishes
from app.config import CATEGORIES


@pytest.mark.unit
def test_seed_from_schedule_unions_all_options(storage):
    db = dishes.seed_from_schedule(storage)
    assert set(db) == set(CATEGORIES)
    # "Гуляш" appears on several weekdays -> exactly once
    assert db["Вторые блюда"].count("Гуляш") == 1
    # sorted case-insensitively
    assert db["Первые блюда"] == sorted(db["Первые блюда"], key=str.lower)
    # the "-" placeholder is dropped
    assert "-" not in db["Первые блюда"]


@pytest.mark.unit
def test_ensure_seeded_persists_once(storage):
    db1 = dishes.ensure_seeded(storage)
    assert storage.load_dishes() == db1
    # second call returns the persisted copy unchanged
    assert dishes.ensure_seeded(storage) == db1


@pytest.mark.unit
def test_add_and_remove_dish(storage):
    dishes.ensure_seeded(storage)
    assert dishes.add_dish(storage, "Гарниры", "Булгур") is True
    assert "Булгур" in dishes.list_dishes(storage, "Гарниры")
    # duplicate (case-insensitive) rejected
    assert dishes.add_dish(storage, "Гарниры", "  булгур ") is False
    # unknown category rejected
    assert dishes.add_dish(storage, "Напитки", "Чай") is False
    assert dishes.remove_dish(storage, "Гарниры", "булгур") is True
    assert "Булгур" not in dishes.list_dishes(storage, "Гарниры")
    assert dishes.remove_dish(storage, "Гарниры", "Булгур") is False


@pytest.mark.unit
def test_ensure_seeded_repairs_missing_category(storage):
    storage.save_dishes({"Первые блюда": ["Щи"]})
    db = dishes.ensure_seeded(storage)
    for cat in CATEGORIES:
        assert cat in db
