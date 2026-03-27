from unittest.mock import AsyncMock

import pytest


@pytest.mark.integration
@pytest.mark.asyncio
async def test_handle_text_message_question(telegram_bot):
    msg = AsyncMock()
    msg.text = "?"
    msg.sticker = None
    await telegram_bot.handle_text_message(msg)
    msg.answer.assert_awaited_once()


@pytest.mark.integration
@pytest.mark.asyncio
async def test_handle_text_message_sticker(telegram_bot):
    msg = AsyncMock()
    msg.text = None
    msg.sticker = type("S", (), {"file_unique_id": "AgADMAADr8ZRGg"})()
    await telegram_bot.handle_text_message(msg)
    msg.answer.assert_awaited_once()


@pytest.mark.integration
@pytest.mark.asyncio
async def test_get_poll_results_no_message_id(telegram_bot):
    res = await telegram_bot.get_poll_results(telegram_bot.bot, 123)
    assert res is None


@pytest.mark.integration
@pytest.mark.asyncio
async def test_get_poll_results_success_and_fail(telegram_bot):
    telegram_bot.last_polls[1] = 10
    telegram_bot.bot.edit_message_reply_markup = AsyncMock(
        return_value=type("M", (), {"poll": "ok"})()
    )
    res = await telegram_bot.get_poll_results(telegram_bot.bot, 1)
    assert res == "ok"

    telegram_bot.bot.edit_message_reply_markup = AsyncMock(side_effect=RuntimeError("fail"))
    res2 = await telegram_bot.get_poll_results(telegram_bot.bot, 1)
    assert res2 is None


@pytest.mark.integration
@pytest.mark.asyncio
async def test_start_poll_scheduler_reuses_task(telegram_bot, monkeypatch):
    class TaskStub:
        def __init__(self, done_value):
            self._done = done_value
        def done(self):
            return self._done

    created = []
    def _fake_create_task(coro):
        coro.close()
        created.append("created")
        return TaskStub(False)

    monkeypatch.setattr("bot.asyncio.create_task", _fake_create_task)
    telegram_bot.poll_task = None
    await telegram_bot.start_poll_scheduler(5)
    assert 5 in telegram_bot.poll_chats
    assert len(created) == 1

    telegram_bot.poll_task = TaskStub(False)
    await telegram_bot.start_poll_scheduler(6)
    assert len(created) == 1


@pytest.mark.integration
@pytest.mark.asyncio
async def test_send_scheduled_poll_weekday_and_weekend(telegram_bot, bot_module, monkeypatch):
    class DTWeekday:
        @classmethod
        def now(cls, tz=None):
            class _Now:
                def weekday(self): return 0
                def strftime(self, fmt): return "01.01"
                def __add__(self, td): return self
            return _Now()

    monkeypatch.setattr("bot.datetime", DTWeekday)
    telegram_bot.bot.send_poll = AsyncMock(return_value=type("SP", (), {"poll": type("P", (), {"id": "pid"})()})())
    await telegram_bot._send_scheduled_poll()
    assert telegram_bot.bot.send_poll.await_count >= 1
    assert "pid" in telegram_bot.poll_ids

    class DTWeekend:
        @classmethod
        def now(cls, tz=None):
            class _Now:
                def weekday(self): return 5
                def strftime(self, fmt): return "01.01"
                def __add__(self, td): return self
            return _Now()

    monkeypatch.setattr("bot.datetime", DTWeekend)
    before = telegram_bot.bot.send_poll.await_count
    await telegram_bot._send_scheduled_poll()
    assert telegram_bot.bot.send_poll.await_count == before


@pytest.mark.integration
@pytest.mark.asyncio
async def test_callback_get_results_paths(telegram_bot, callback_query_obj, computed_date):
    cq = callback_query_obj(chat_id=1, chat_type="private")
    telegram_bot.post_main_menu_buttons = AsyncMock()
    telegram_bot.last_results_message["1"] = AsyncMock(delete=AsyncMock())
    telegram_bot.polls_dict[computed_date] = {
        "Вторые блюда": {"options": ["Котлета"], "votes": [1]},
        "set_dish": {},
    }
    await telegram_bot.callback_get_results(cq)
    assert cq.message.answer.await_count >= 1

    cq2 = callback_query_obj(chat_id=2, chat_type="private")
    telegram_bot.post_main_menu_buttons = AsyncMock()
    telegram_bot.polls_dict = {}
    await telegram_bot.callback_get_results(cq2)
    assert cq2.message.answer.await_count >= 1


@pytest.mark.integration
@pytest.mark.asyncio
async def test_callback_edit_poll_and_menu(telegram_bot, callback_query_obj):
    cq = callback_query_obj(chat_id=3, chat_type="private")
    telegram_bot.post_main_menu_buttons = AsyncMock()
    telegram_bot.last_get_poll_message = AsyncMock(delete=AsyncMock())
    await telegram_bot.callback_edit_poll(cq)
    telegram_bot.post_main_menu_buttons.assert_awaited_once()


@pytest.mark.integration
@pytest.mark.asyncio
async def test_post_main_menu_buttons_and_run(telegram_bot):
    telegram_bot.bot.send_message = AsyncMock()
    await telegram_bot.post_main_menu_buttons(88)
    telegram_bot.bot.send_message.assert_awaited_once()
    sent_markup = telegram_bot.bot.send_message.await_args.kwargs["reply_markup"]
    button_texts = [
        button.text
        for row in sent_markup.inline_keyboard
        for button in row
    ]
    assert "Обновить результаты" not in button_texts

    telegram_bot.dp.start_polling = AsyncMock()
    await telegram_bot.run()
    telegram_bot.dp.start_polling.assert_awaited_once()


@pytest.mark.integration
@pytest.mark.asyncio
async def test_post_group_menu_buttons_has_single_refresh(telegram_bot):
    telegram_bot.bot.send_message = AsyncMock()
    await telegram_bot.post_group_menu_buttons(-100)
    sent_markup = telegram_bot.bot.send_message.await_args.kwargs["reply_markup"]
    assert len(sent_markup.inline_keyboard) == 1
    assert len(sent_markup.inline_keyboard[0]) == 1
    assert sent_markup.inline_keyboard[0][0].text == "Обновить результаты"


@pytest.mark.integration
@pytest.mark.asyncio
async def test_handle_poll_update_unknown_id_branch(telegram_bot, poll_obj):
    telegram_bot.poll_ids = []
    poll = poll_obj("unknown", "Гарниры 01.01", [("Рис", 1)])
    await telegram_bot.handle_poll_update(poll)
    assert telegram_bot.polls_dict == {}


@pytest.mark.integration
@pytest.mark.asyncio
async def test_save_poll_id_and_change_start_poll_time(telegram_bot, callback_query_obj):
    await telegram_bot.save_poll_id(10, 20)
    assert telegram_bot.last_polls[10] == 20

    cq = callback_query_obj(chat_id=1, chat_type="private")
    await telegram_bot.callback_change_start_poll_time(cq)
    cq.message.answer.assert_awaited()


@pytest.mark.integration
@pytest.mark.asyncio
async def test_callback_get_results_exception_branches(telegram_bot, callback_query_obj, computed_date):
    cq = callback_query_obj(chat_id=4, chat_type="private")
    cq.message.delete = AsyncMock(side_effect=RuntimeError("x"))
    telegram_bot.post_main_menu_buttons = AsyncMock()
    telegram_bot.last_results_message["4"] = AsyncMock(delete=AsyncMock(side_effect=RuntimeError("x")))
    telegram_bot.polls_dict[computed_date] = {
        "Вторые блюда": {"options": ["Котлета"], "votes": [0]},
        "set_dish": {},
    }
    await telegram_bot.callback_get_results(cq)
    assert cq.message.answer.await_count >= 1


@pytest.mark.integration
@pytest.mark.asyncio
async def test_get_joint_results_dash_branches(telegram_bot, computed_date):
    telegram_bot.polls_dict[computed_date] = {
        "set_dish": {
            1: {"Вторые блюда": ["—"], "Гарниры": ["Рис"]},
            2: {"Вторые блюда": ["Котлета"], "Гарниры": ["—"]},
        }
    }
    res = await telegram_bot.get_joint_results()
    assert "Рис" in res
    assert "Котлета" in res


@pytest.mark.integration
@pytest.mark.asyncio
async def test_callback_get_joint_results_exception_branches(telegram_bot, callback_query_obj, computed_date):
    cq = callback_query_obj(chat_id=5, chat_type="private")
    cq.message.delete = AsyncMock(side_effect=RuntimeError("x"))
    telegram_bot.post_main_menu_buttons = AsyncMock()
    telegram_bot.last_results_message["5"] = AsyncMock(delete=AsyncMock(side_effect=RuntimeError("x")))
    telegram_bot.polls_dict[computed_date] = {"set_dish": {}}
    await telegram_bot.callback_get_joint_results(cq)
    assert cq.message.answer.await_count >= 1


@pytest.mark.integration
@pytest.mark.asyncio
async def test_callback_edit_poll_exception_branches(telegram_bot, callback_query_obj):
    cq = callback_query_obj(chat_id=6, chat_type="private")
    cq.message.delete = AsyncMock(side_effect=RuntimeError("x"))
    telegram_bot.post_main_menu_buttons = AsyncMock()
    telegram_bot.last_get_poll_message = AsyncMock(delete=AsyncMock(side_effect=RuntimeError("x")))
    await telegram_bot.callback_edit_poll(cq)
    telegram_bot.post_main_menu_buttons.assert_awaited_once()
