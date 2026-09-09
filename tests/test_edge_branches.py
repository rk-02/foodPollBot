"""Defensive / rarely-hit branches."""

from datetime import date, datetime, timedelta
from unittest.mock import AsyncMock

import pytest
from aiogram.exceptions import TelegramBadRequest, TelegramForbiddenError

from app import admin, polls, scheduler, stats
from app.config import TIMEZONE
from app.timeutil import current_poll_date

pytestmark = pytest.mark.integration


def _bad(*_a, **_k):
    raise TelegramBadRequest(method=None, message="boom")


# --- timeutil -----------------------------------------------------

@pytest.mark.unit
def test_current_poll_date_before_poll_time_is_today(storage):
    moment = TIMEZONE.localize(datetime(2026, 9, 9, 7, 0))  # before 12:00
    d, iso = current_poll_date(storage, moment)
    assert d == "09.09" and iso == "2026-09-09"


# --- stats migration edge keys --------------------------------

@pytest.mark.unit
def test_migrate_history_skips_non_dict_and_invalid_date(storage):
    storage.save_history({
        "1": "not-a-dict",
        "2": {"32.13": {"Гарниры": "Рис"}, "2025-05-05": {"Гарниры": "Рис"}},
    })
    stats.migrate_history(storage, assume_year=2025)
    hist = storage.load_history()
    assert hist["1"] == "not-a-dict"
    assert list(hist["2"]) == ["2025-05-05"]


@pytest.mark.unit
def test_usual_picks_ignores_bad_iso_values(storage):
    storage.save_history({"5": {"oops": {"Гарниры": "Рис"}}})
    assert stats.usual_picks(storage, 5) == {
        "enough": False, "picks": {}, "span_days": 0, "records": 0, "counts": {},
    }


# --- polls guards --------------------------------------------

@pytest.mark.unit
def test_set_vote_and_user_votes_without_day(storage):
    assert polls.set_vote(storage, "01.01", "Гарниры", "Рис", 1) is False
    assert polls.user_votes(storage, "01.01") == {}


# --- bot._safe_dm real exception path -----------------------

@pytest.mark.asyncio
async def test_safe_dm_swallows_forbidden(app):
    app.bot.send_message = AsyncMock(side_effect=TelegramForbiddenError(method=None, message="blocked"))
    assert await app._safe_dm(123, "hi") is False


@pytest.mark.asyncio
async def test_refresh_action_menu_deletes_previous_and_survives_error(app):
    app.action_menu_msgs[-100] = 42
    app.bot.delete_message = AsyncMock(side_effect=_bad)
    await app._refresh_action_menu(-100, private=False)
    app.bot.delete_message.assert_awaited()          # tried to delete #42
    assert app.action_menu_msgs[-100] != 42          # replaced anyway


@pytest.mark.asyncio
async def test_poll_vote_survives_keyboard_edit_error(app, seeded_poll, make_cq):
    cq = make_cq("poll:10.09:2:0", chat_id=-100, chat_type="supergroup", user_id=1)
    cq.message.edit_reply_markup = AsyncMock(side_effect=_bad)
    await app.on_poll_vote(cq)
    cq.answer.assert_awaited_once()


@pytest.mark.asyncio
async def test_menu_results_survives_delete_error(app, make_cq):
    app.last_results_msg[-100] = 999
    app.bot.delete_message = AsyncMock(side_effect=_bad)
    cq = make_cq("menu:results", chat_id=-100, chat_type="supergroup")
    await app.on_menu_results(cq)
    cq.answer.assert_awaited_once()


@pytest.mark.asyncio
async def test_usual_skips_category_without_live_entry(app, make_cq):
    # live poll exists but only for Гарниры; history also has Вторые блюда
    date_str, iso = current_poll_date(app.storage)
    polls.start_day(app.storage, date_str, iso, 0)
    polls.register_poll(app.storage, date_str, "Гарниры", 1, ["Рис", "Гречка"])
    today = date.today()
    app.storage.save_history({"6": {
        (today - timedelta(days=d)).isoformat(): {"Вторые блюда": "Гуляш", "Гарниры": "Рис"}
        for d in range(1, 21)
    }})
    cq = make_cq("menu:usual", chat_id=-100, chat_type="supergroup", user_id=6)
    await app.on_usual(cq)
    votes = polls.user_votes(app.storage, date_str).get(6, {})
    assert votes == {"Гарниры": "Рис"}               # Вторые блюда skipped, no crash


@pytest.mark.asyncio
async def test_usual_survives_keyboard_edit_error(app, make_cq):
    date_str, iso = current_poll_date(app.storage)
    polls.start_day(app.storage, date_str, iso, 0)
    polls.register_poll(app.storage, date_str, "Гарниры", 1, ["Рис"])
    today = date.today()
    app.storage.save_history({"6": {
        (today - timedelta(days=d)).isoformat(): {"Гарниры": "Рис"} for d in range(1, 21)
    }})
    app.bot.edit_message_reply_markup = AsyncMock(side_effect=_bad)
    cq = make_cq("menu:usual", chat_id=-100, chat_type="supergroup", user_id=6)
    await app.on_usual(cq)
    cq.answer.assert_awaited()


# --- admin _show fallback + propagate edit error -----------

@pytest.mark.asyncio
async def test_admin_show_falls_back_to_answer(app, make_cq):
    cq = make_cq("adm:root", chat_id=5, chat_type="private", user_id=5)
    cq.message.edit_text = AsyncMock(side_effect=_bad)
    await admin.handle_callback(app, cq)
    cq.message.answer.assert_awaited()


@pytest.mark.asyncio
async def test_admin_propagate_survives_markup_error(app, make_cq):
    from app import menu_config
    menu_config.set_day_category(app.storage, 1, "Гарниры", ["Рис", "Гречка"])
    polls.start_day(app.storage, "10.09", "2026-09-10", 1)
    polls.register_poll(app.storage, "10.09", "Гарниры", 900, ["Рис", "Гречка"])
    app.bot.edit_message_reply_markup = AsyncMock(side_effect=_bad)

    cq = make_cq("adm:cat:1:2", chat_id=5, chat_type="private", user_id=5)
    await admin.handle_callback(app, cq)
    app.pending[5]["options"] = ["Рис"]
    cq2 = make_cq("adm:msave", chat_id=5, chat_type="private", user_id=5)
    await admin.handle_callback(app, cq2)

    warn = [c for c in app.bot.send_message.await_args_list
            if c.args and c.args[0] == app.chat_id]
    assert warn and "Изменения в меню" in warn[0].args[1]


@pytest.mark.asyncio
async def test_admin_mcancel_without_draft(app, make_cq):
    cq = make_cq("adm:mcancel", chat_id=5, chat_type="private", user_id=5)
    await admin.handle_callback(app, cq)
    cq.message.edit_text.assert_awaited()


@pytest.mark.asyncio
async def test_admin_msave_without_draft_returns_root(app, make_cq):
    cq = make_cq("adm:msave", chat_id=5, chat_type="private", user_id=5)
    await admin.handle_callback(app, cq)
    assert "Админ-панель" in cq.message.edit_text.await_args.args[0]


@pytest.mark.asyncio
async def test_scheduler_loop_swallows_tick_errors(app, monkeypatch):
    import asyncio
    calls = []

    async def _boom(_app):
        calls.append(1)
        if len(calls) == 1:
            raise RuntimeError("first tick fails")
        raise asyncio.CancelledError

    monkeypatch.setattr(scheduler, "tick", _boom)
    monkeypatch.setattr("app.scheduler.asyncio.sleep", AsyncMock())
    with pytest.raises(asyncio.CancelledError):
        await scheduler.scheduler_loop(app)
    assert len(calls) == 2
