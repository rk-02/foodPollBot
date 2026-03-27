from unittest.mock import AsyncMock

import pytest


@pytest.mark.e2e
@pytest.mark.asyncio
async def test_e2e_start_in_private_shows_main_menu(telegram_bot):
    msg = AsyncMock()
    msg.chat.type = "private"
    msg.chat.id = 77
    telegram_bot.post_main_menu_buttons = AsyncMock()

    await telegram_bot.cmd_start(msg)

    telegram_bot.post_main_menu_buttons.assert_awaited_once_with(77)


@pytest.mark.e2e
@pytest.mark.asyncio
async def test_e2e_start_in_group_starts_scheduler(telegram_bot):
    msg = AsyncMock()
    msg.chat.type = "supergroup"
    msg.chat.id = -100
    telegram_bot.start_poll_scheduler = AsyncMock()
    telegram_bot.post_group_menu_buttons = AsyncMock()

    await telegram_bot.cmd_start(msg)

    telegram_bot.start_poll_scheduler.assert_awaited_once_with(-100)
    msg.answer.assert_awaited_once()
    telegram_bot.post_group_menu_buttons.assert_awaited_once_with(-100)


@pytest.mark.e2e
@pytest.mark.asyncio
async def test_e2e_grouped_results_flow(telegram_bot, callback_query_obj, computed_date):
    cq = callback_query_obj(chat_id=-100, chat_type="supergroup", user_id=42, first_name="Roman")
    telegram_bot.post_group_menu_buttons = AsyncMock()
    telegram_bot.polls_dict[computed_date] = {
        "set_dish": {42: {"Вторые блюда": ["Котлета"], "Гарниры": ["Рис"]}}
    }

    await telegram_bot.callback_get_joint_results(cq)

    # 1) grouped result, 2) "кто и когда обновил"
    assert cq.message.answer.await_count >= 2
    telegram_bot.post_group_menu_buttons.assert_awaited_once_with(-100)
