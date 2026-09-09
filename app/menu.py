"""The "Выберите действие" action menu.

Kept deliberately tiny — in the group the bot only ever shows polls, results
and this menu, nothing else.
"""

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

CB_RESULTS = "menu:results"
CB_GROUP_RESULTS = "menu:group_results"
CB_USUAL = "menu:usual"
CB_ADMIN = "adm:root"

MENU_CALLBACKS = {CB_RESULTS, CB_GROUP_RESULTS, CB_USUAL}


def action_menu_markup(private: bool, bot_username: str | None) -> InlineKeyboardMarkup:
    if private:
        rows = [
            [InlineKeyboardButton(text="📊 Получить результаты", callback_data=CB_RESULTS)],
            [InlineKeyboardButton(text="🗂 Сгруппированный результат", callback_data=CB_GROUP_RESULTS)],
            [InlineKeyboardButton(text="⚙️ Админ-панель", callback_data=CB_ADMIN)],
        ]
    else:
        rows = [
            [InlineKeyboardButton(text="🔄 Обновить результаты", callback_data=CB_RESULTS)],
            [InlineKeyboardButton(text="🔁 Мне как обычно", callback_data=CB_USUAL)],
        ]
        if bot_username:
            rows.append([InlineKeyboardButton(
                text="✍️ Написать боту",
                url=f"https://t.me/{bot_username}?start=dm",
            )])
    return InlineKeyboardMarkup(inline_keyboard=rows)


async def send_action_menu(app, chat_id: int, private: bool):
    return await app.bot.send_message(
        chat_id,
        "Выберите действие:",
        reply_markup=action_menu_markup(private, app.bot_username),
    )
