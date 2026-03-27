import asyncio

import pytest


@pytest.mark.integration
@pytest.mark.asyncio
async def test_race_two_users_parallel_votes_keep_all_sides(telegram_bot, poll_answer_obj):
    date = "01.01"
    telegram_bot.polls_dict[date] = {
        "Вторые блюда": {"options": ["Котлета", "Рыба"], "votes": [0, 0]},
        "Гарниры": {"options": ["Рис", "Пюре"], "votes": [0, 0]},
        "set_dish": {},
    }
    telegram_bot.poll_info_by_id["main_poll"] = {"poll_question": "Вторые блюда", "poll_date": date}
    telegram_bot.poll_info_by_id["side_poll"] = {"poll_question": "Гарниры", "poll_date": date}

    async def vote_user(uid: int, main_idx: int, side_idx: int):
        await asyncio.gather(
            telegram_bot.handle_poll_answer(poll_answer_obj(uid, f"U{uid}", "main_poll", [main_idx])),
            telegram_bot.handle_poll_answer(poll_answer_obj(uid, f"U{uid}", "side_poll", [side_idx])),
        )

    await asyncio.gather(vote_user(1, 0, 0), vote_user(2, 1, 1))

    assert telegram_bot.polls_dict[date]["set_dish"][1]["Гарниры"] == ["Рис"]
    assert telegram_bot.polls_dict[date]["set_dish"][2]["Гарниры"] == ["Пюре"]


@pytest.mark.integration
@pytest.mark.asyncio
async def test_answer_before_poll_info_does_not_write_partial(telegram_bot, poll_answer_obj):
    date = "01.01"
    telegram_bot.polls_dict[date] = {
        "Вторые блюда": {"options": ["Котлета"], "votes": [0]},
        "Гарниры": {"options": ["Рис"], "votes": [0]},
        "set_dish": {},
    }
    # poll_info_by_id отсутствует -> событие игнорируется в текущей реализации
    await telegram_bot.handle_poll_answer(poll_answer_obj(1, "U1", "unknown_poll", [0]))
    assert telegram_bot.polls_dict[date]["set_dish"] == {}
