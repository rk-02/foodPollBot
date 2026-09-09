from datetime import datetime

import pytest

from app import polls, scheduler
from app.config import TIMEZONE

pytestmark = pytest.mark.integration


def _moment(y, m, d, hh, mm):
    return TIMEZONE.localize(datetime(y, m, d, hh, mm))


@pytest.mark.asyncio
async def test_send_poll_set_posts_four_polls_and_menu(app):
    # 2026-09-09 is a Wednesday -> poll_index (2+1)%7 = 3 (Thursday menu)
    date = await scheduler.send_poll_set(app, _moment(2026, 9, 9, 12, 0))
    assert date == "10.09"

    day = polls.get_day(app.storage, "10.09")
    assert set(day["categories"]) == {"Первые блюда", "Вторые блюда", "Гарниры", "Салаты"}
    assert day["menu_weekday"] == 3
    # 4 poll messages + 1 action menu
    assert app.bot.send_message.await_count == 5
    assert app.action_menu_msgs[app.chat_id] is not None
    assert day["action_menu_message_id"] is not None


@pytest.mark.asyncio
async def test_send_poll_set_skips_weekend_target(app):
    # Friday -> target Saturday -> nothing
    assert await scheduler.send_poll_set(app, _moment(2026, 9, 11, 12, 0)) is None
    app.bot.send_message.assert_not_awaited()


@pytest.mark.asyncio
async def test_send_poll_set_skips_empty_category(app):
    from app import menu_config
    menu_config.set_day_category(app.storage, 3, "Салаты", [])
    await scheduler.send_poll_set(app, _moment(2026, 9, 9, 12, 0))
    day = polls.get_day(app.storage, "10.09")
    assert "Салаты" not in day["categories"]
    assert app.bot.send_message.await_count == 4  # 3 polls + menu


@pytest.mark.asyncio
async def test_send_results_posts_and_records_history(app):
    await scheduler.send_poll_set(app, _moment(2026, 9, 9, 12, 0))
    # cast a couple of votes on the "10.09" set
    polls.toggle_vote(app.storage, "10.09", 1, 0, 77)      # Вторые
    polls.toggle_vote(app.storage, "10.09", 2, 0, 77)      # Гарниры
    polls.remember_name(app.storage, "10.09", 77, "Кот")

    app.bot.send_message.reset_mock()
    date = await scheduler.send_results(app, _moment(2026, 9, 9, 18, 0))
    assert date == "10.09"
    posted = app.bot.send_message.await_args.args
    assert posted[0] == app.chat_id and "🗓 10.09" in posted[1]

    hist = app.storage.load_history()
    assert "2026-09-10" in hist["77"]
    assert hist["77"]["2026-09-10"]  # picks recorded


@pytest.mark.asyncio
async def test_tick_fires_once_per_day(app, monkeypatch):
    calls = []

    async def _fake_send(_app, moment=None):
        calls.append(moment)

    monkeypatch.setattr(scheduler, "send_poll_set", _fake_send)
    monkeypatch.setattr(scheduler, "send_results", _fake_send)

    m = _moment(2026, 9, 9, 12, 0)
    await scheduler.tick(app, m)
    await scheduler.tick(app, m)   # same minute, must not double-fire
    assert len(calls) == 1

    await scheduler.tick(app, _moment(2026, 9, 9, 18, 0))
    assert len(calls) == 2


@pytest.mark.asyncio
async def test_tick_silent_on_weekend(app, monkeypatch):
    fired = []
    monkeypatch.setattr(scheduler, "send_poll_set",
                        lambda *_a, **_k: fired.append("poll"))
    monkeypatch.setattr(scheduler, "send_results",
                        lambda *_a, **_k: fired.append("res"))
    await scheduler.tick(app, _moment(2026, 9, 12, 12, 0))  # Saturday
    assert fired == []


@pytest.mark.asyncio
async def test_tick_ignores_off_schedule_minutes(app, monkeypatch):
    fired = []
    monkeypatch.setattr(scheduler, "send_poll_set",
                        lambda *_a, **_k: fired.append(1))
    monkeypatch.setattr(scheduler, "send_results",
                        lambda *_a, **_k: fired.append(1))
    await scheduler.tick(app, _moment(2026, 9, 9, 13, 17))
    assert fired == []
