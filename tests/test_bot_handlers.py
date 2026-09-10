from datetime import date, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app import polls

pytestmark = pytest.mark.integration


# --- /start ---------------------------------------------------------

@pytest.mark.asyncio
async def test_start_private_registers_dm_user_and_shows_menu(app, make_message):
    msg = make_message(text="/start", chat_id=42, chat_type="private",
                       user_id=7, first_name="Роман")
    await app.cmd_start(msg)

    assert app.storage.load_dm_users()["7"] == "Роман"
    app.bot.send_message.assert_awaited()
    assert app.bot.send_message.await_args.args[0] == 42


@pytest.mark.asyncio
async def test_start_group_starts_scheduler_and_posts_menu(app, make_message, no_scheduler):
    msg = make_message(text="/start", chat_id=-100, chat_type="supergroup")
    await app.cmd_start(msg)

    assert -100 in app.poll_chats
    assert app._scheduler_task is not None
    assert -100 in app.action_menu_msgs


# --- custom poll voting ------------------------------------------

@pytest.mark.asyncio
async def test_poll_vote_records_and_answers(app, seeded_poll, make_cq):
    cq = make_cq("poll:10.09:2:0", chat_id=-100, chat_type="supergroup",
                 user_id=5, first_name="Ира")
    await app.on_poll_vote(cq)

    entry = polls.get_day(app.storage, "10.09")["categories"]["Гарниры"]
    assert entry["votes"] == {"Рис": [5]}
    assert app.storage.load_poll_state()["10.09"]["names"]["5"] == "Ира"
    cq.message.edit_reply_markup.assert_awaited_once()
    cq.answer.assert_awaited_once()
    # the voter's own choice comes back highlighted
    kb = cq.message.edit_reply_markup.await_args.kwargs["reply_markup"]
    labels = [b.text for row in kb.inline_keyboard for b in row]
    assert any(t.startswith(polls.VOTE_MARK) for t in labels)


@pytest.mark.asyncio
async def test_poll_vote_bad_payload(app, make_cq):
    cq = make_cq("poll:garbage")
    await app.on_poll_vote(cq)
    cq.answer.assert_awaited_once()


@pytest.mark.asyncio
async def test_poll_vote_inactive_poll(app, make_cq):
    cq = make_cq("poll:01.01:0:0")
    await app.on_poll_vote(cq)
    cq.answer.assert_awaited_once_with("Опрос больше не активен.", show_alert=False)


# --- "мне как обычно" ------------------------------------------

@pytest.mark.asyncio
async def test_usual_button_locked_until_two_weeks(app, live_poll, make_cq, history_on_weekday):
    history_on_weekday(app, 9, {"Вторые блюда": "Гуляш"}, weekday=2, occurrences=3)
    cq = make_cq("menu:usual", chat_id=-100, chat_type="supergroup", user_id=9)
    await app.on_usual(cq)  # poll_rounds not set -> button not ready
    assert cq.answer.await_args.kwargs.get("show_alert") is True
    assert "2 недели" in cq.answer.await_args.args[0]
    assert polls.user_votes(app.storage, live_poll).get(9) is None


@pytest.mark.asyncio
async def test_usual_no_history_alerts(app, live_poll, usual_ready, make_cq):
    cq = make_cq("menu:usual", chat_id=-100, chat_type="supergroup", user_id=9)
    await app.on_usual(cq)
    cq.answer.assert_awaited_once()
    assert cq.answer.await_args.kwargs.get("show_alert") is True


@pytest.mark.asyncio
async def test_usual_votes_by_weekday_and_dms(app, live_poll, usual_ready, make_cq, history_on_weekday):
    history_on_weekday(app, 9, {"Вторые блюда": "Гуляш", "Гарниры": "Рис"},
                       weekday=2, occurrences=3)

    cq = make_cq("menu:usual", chat_id=-100, chat_type="supergroup", user_id=9)
    await app.on_usual(cq)

    votes = polls.user_votes(app.storage, live_poll).get(9, {})
    assert votes.get("Вторые блюда") == "Гуляш"
    assert votes.get("Гарниры") == "Рис"
    dm = [c for c in app.bot.send_message.await_args_list if c.args and c.args[0] == 9]
    assert dm and "обычный набор на" in dm[0].args[1]
    cq.answer.assert_awaited()


@pytest.mark.asyncio
async def test_usual_few_weekday_records_notes_overall_stats(app, live_poll, usual_ready,
                                                             make_cq, history_on_weekday):
    history_on_weekday(app, 4, {"Вторые блюда": "Гуляш"}, weekday=2, occurrences=1)

    cq = make_cq("menu:usual", chat_id=-100, chat_type="supergroup", user_id=4)
    await app.on_usual(cq)

    dm = [c for c in app.bot.send_message.await_args_list if c.args and c.args[0] == 4]
    assert dm and "общей статистики" in dm[0].args[1]
    assert polls.user_votes(app.storage, live_poll).get(4, {}).get("Вторые блюда") == "Гуляш"


@pytest.mark.asyncio
async def test_usual_dm_blocked_falls_back_to_alert(app, live_poll, usual_ready,
                                                    make_cq, monkeypatch, history_on_weekday):
    history_on_weekday(app, 3, {"Гарниры": "Рис"}, weekday=2, occurrences=3)
    monkeypatch.setattr(app, "_safe_dm", AsyncMock(return_value=False))

    cq = make_cq("menu:usual", chat_id=-100, chat_type="supergroup", user_id=3)
    await app.on_usual(cq)

    assert cq.answer.await_args.kwargs.get("show_alert") is True
    assert polls.user_votes(app.storage, live_poll).get(3, {}).get("Гарниры") == "Рис"


@pytest.mark.asyncio
async def test_usual_favourite_not_in_menu_uses_fallback(app, live_poll, usual_ready,
                                                         make_cq, history_on_weekday):
    # 3 Wednesdays of "Картофель фри" (not on today's poll) + 1 other day "Рис"
    hist = history_on_weekday(app, 8, {"Гарниры": "Картофель фри"}, weekday=2, occurrences=3)
    from datetime import date, timedelta
    other = (date.today() - timedelta(days=1)).isoformat()
    store = app.storage.load_history()
    store["8"][other] = {"Гарниры": "Рис"}
    app.storage.save_history(store)

    cq = make_cq("menu:usual", chat_id=-100, chat_type="supergroup", user_id=8)
    await app.on_usual(cq)

    assert polls.user_votes(app.storage, live_poll).get(8, {}).get("Гарниры") == "Рис"
    dm = [c for c in app.bot.send_message.await_args_list if c.args and c.args[0] == 8]
    assert dm and "взял ближайшее" in dm[0].args[1]


@pytest.mark.asyncio
async def test_usual_no_live_poll(app, usual_ready, make_cq):
    cq = make_cq("menu:usual", chat_id=-100, chat_type="supergroup", user_id=9)
    await app.on_usual(cq)
    assert cq.answer.await_args.kwargs.get("show_alert") is True


# --- results ---------------------------------------------------

@pytest.mark.asyncio
async def test_menu_results_posts_and_refreshes(app, make_cq):
    from app.timeutil import current_poll_date

    date_str, _ = current_poll_date(app.storage)
    polls.start_day(app.storage, date_str, "2026-01-01", 0)
    polls.register_poll(app.storage, date_str, "Гарниры", 9, ["Рис"])
    polls.toggle_vote(app.storage, date_str, 2, 0, 1)

    cq = make_cq("menu:results", chat_id=-100, chat_type="supergroup")
    await app.on_menu_results(cq)

    assert -100 in app.last_results_msg
    assert -100 in app.action_menu_msgs
    cq.answer.assert_awaited_once()


@pytest.mark.asyncio
async def test_menu_results_deletes_previous(app, make_cq):
    app.last_results_msg[-100] = 777
    cq = make_cq("menu:results", chat_id=-100, chat_type="supergroup")
    await app.on_menu_results(cq)
    app.bot.delete_message.assert_any_await(-100, 777)


@pytest.mark.asyncio
async def test_menu_results_in_group_names_who_updated(app, make_cq):
    from app.timeutil import current_poll_date
    date_str, _ = current_poll_date(app.storage)
    polls.start_day(app.storage, date_str, "2026-01-01", 0)
    polls.register_poll(app.storage, date_str, "Гарниры", 9, ["Рис"])
    polls.toggle_vote(app.storage, date_str, 2, 0, 1)

    cq = make_cq("menu:results", chat_id=-100, chat_type="supergroup",
                 user_id=3, first_name="Женя")
    await app.on_menu_results(cq)

    posted = [c for c in app.bot.send_message.await_args_list
              if c.args and c.args[0] == -100]
    assert any("Обновил(а) Женя в " in c.args[1] for c in posted)


@pytest.mark.asyncio
async def test_menu_results_in_private_has_no_updater_line(app, make_cq):
    from app.timeutil import current_poll_date
    date_str, _ = current_poll_date(app.storage)
    polls.start_day(app.storage, date_str, "2026-01-01", 0)
    polls.register_poll(app.storage, date_str, "Гарниры", 9, ["Рис"])
    polls.toggle_vote(app.storage, date_str, 2, 0, 1)

    cq = make_cq("menu:results", chat_id=5, chat_type="private", user_id=5)
    await app.on_menu_results(cq)

    sent = [c for c in app.bot.send_message.await_args_list if c.args and c.args[0] == 5]
    assert sent and not any("Обновил" in c.args[1] for c in sent)


# --- admin gate + group silence ------------------------------

@pytest.mark.asyncio
async def test_admin_callback_denied_in_group(app, make_cq):
    cq = make_cq("adm:root", chat_id=-100, chat_type="supergroup")
    await app.on_admin_callback(cq)
    cq.answer.assert_awaited_once()
    assert cq.answer.await_args.kwargs.get("show_alert") is True


@pytest.mark.asyncio
async def test_admin_callback_allowed_in_private(app, make_cq):
    cq = make_cq("adm:root", chat_id=5, chat_type="private", user_id=5)
    await app.on_admin_callback(cq)
    cq.answer.assert_awaited_once()
    cq.message.edit_text.assert_awaited()  # root panel rendered


@pytest.mark.asyncio
async def test_text_in_group_is_ignored(app, make_message):
    msg = make_message(text="привет бот", chat_type="supergroup", chat_id=-100)
    await app.on_text(msg)
    msg.answer.assert_not_awaited()
    app.bot.send_message.assert_not_awaited()


@pytest.mark.asyncio
async def test_text_in_private_without_pending_is_noop(app, make_message):
    msg = make_message(text="просто текст", chat_type="private", chat_id=5, user_id=5)
    await app.on_text(msg)
    app.bot.send_message.assert_not_awaited()


@pytest.mark.asyncio
async def test_display_name_variants(app):
    assert app._display_name(
        SimpleNamespace(id=1, first_name="A", last_name="B", username="u")) == "A B"
    assert app._display_name(
        SimpleNamespace(id=1, first_name=None, last_name=None, username="nick")) == "nick"
    assert app._display_name(
        SimpleNamespace(id=1, first_name=None, last_name=None, username=None)) == "ID1"
