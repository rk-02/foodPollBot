from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest


@pytest.mark.integration
@pytest.mark.asyncio
async def test_handle_poll_update_stores_poll(telegram_bot, poll_obj):
    telegram_bot.poll_ids = ["p1"]
    poll = poll_obj("p1", "Гарниры 01.01", [("Рис", 2), ("Пюре", 1)])
    await telegram_bot.handle_poll_update(poll)

    assert "01.01" in telegram_bot.polls_dict
    assert "Гарниры" in telegram_bot.polls_dict["01.01"]
    assert telegram_bot.polls_dict["01.01"]["Гарниры"]["options"] == ["Рис", "Пюре"]
    assert telegram_bot.poll_info_by_id["p1"]["poll_question"] == "Гарниры"


@pytest.mark.integration
@pytest.mark.asyncio
async def test_handle_poll_answer_updates_set_dish(telegram_bot, poll_answer_obj):
    date = "01.01"
    telegram_bot.polls_dict[date] = {
        "Вторые блюда": {"options": ["Котлета", "Рыба"], "votes": [0, 0]},
        "Гарниры": {"options": ["Рис", "Пюре"], "votes": [0, 0]},
        "set_dish": {},
    }
    telegram_bot.poll_info_by_id["main_poll"] = {"poll_question": "Вторые блюда", "poll_date": date}
    telegram_bot.poll_info_by_id["side_poll"] = {"poll_question": "Гарниры", "poll_date": date}

    await telegram_bot.handle_poll_answer(poll_answer_obj(7, "Roman", "main_poll", [0]))
    await telegram_bot.handle_poll_answer(poll_answer_obj(7, "Roman", "side_poll", [1]))

    entry = telegram_bot.polls_dict[date]["set_dish"][7]
    assert entry["Вторые блюда"] == ["Котлета"]
    assert entry["Гарниры"] == ["Пюре"]


@pytest.mark.integration
@pytest.mark.asyncio
async def test_callback_get_joint_results_sends_message(telegram_bot, callback_query_obj, computed_date):
    cq = callback_query_obj(chat_id=111, chat_type="private")
    telegram_bot.post_main_menu_buttons = AsyncMock()
    telegram_bot.polls_dict[computed_date] = {
        "set_dish": {1: {"Вторые блюда": ["Котлета"], "Гарниры": ["Рис"]}}
    }

    await telegram_bot.callback_get_joint_results(cq)

    assert cq.message.answer.await_count >= 1
