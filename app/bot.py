"""FoodPollBot — wires the handlers to the modules and owns shared state."""

import asyncio
import logging

from aiogram import Bot, Dispatcher, F
from aiogram.exceptions import TelegramBadRequest, TelegramForbiddenError
from aiogram.filters import Command
from aiogram.types import CallbackQuery, Message

from . import admin, dishes, menu, polls, scheduler, stats
from .config import BOT_TOKEN, CATEGORIES, CHAT_ID, TIMEZONE
from .menu_config import get_day_menu  # noqa: F401  (re-exported for convenience)
from .storage import Storage
from .timeutil import current_poll_date, now

log = logging.getLogger(__name__)

_VOTE_TOAST = {
    "added": "Голос учтён ✅",
    "switched": "Голос изменён 🔁",
    "removed": "Голос снят ❌",
}


class FoodPollBot:
    def __init__(self, storage: Storage | None = None, bot: Bot | None = None):
        self.storage = storage or Storage()
        self.bot = bot or Bot(token=BOT_TOKEN)
        self.dp = Dispatcher()
        self.tz = TIMEZONE
        self.chat_id = CHAT_ID
        self.bot_username: str | None = None

        self.pending: dict[int, dict] = {}
        self.poll_chats: set[int] = set()
        self.last_results_msg: dict[int, int] = {}
        self.action_menu_msgs: dict[int, int] = {}

        self.tick_seconds = 20
        self._last_poll_day: str | None = None
        self._last_results_day: str | None = None
        self._scheduler_task: asyncio.Task | None = None

        dishes.ensure_seeded(self.storage)
        self._register()

    # -- helpers -----------------------------------------------------
    @staticmethod
    def _display_name(user) -> str:
        name = user.first_name or getattr(user, "username", None) or f"ID{user.id}"
        if getattr(user, "last_name", None):
            name = f"{name} {user.last_name}"
        return name

    def _register_dm_user(self, user) -> None:
        users = self.storage.load_dm_users()
        users[str(user.id)] = self._display_name(user)
        self.storage.save_dm_users(users)

    async def _safe_dm(self, user_id: int, text: str) -> bool:
        try:
            await self.bot.send_message(user_id, text)
            return True
        except (TelegramForbiddenError, TelegramBadRequest):
            return False

    async def _refresh_action_menu(self, chat_id: int, private: bool):
        prev = self.action_menu_msgs.get(chat_id)
        if prev:
            try:
                await self.bot.delete_message(chat_id, prev)
            except TelegramBadRequest:
                pass
        sent = await menu.send_action_menu(self, chat_id, private)
        self.action_menu_msgs[chat_id] = sent.message_id
        return sent

    async def start_scheduler(self) -> None:
        if self._scheduler_task is None or self._scheduler_task.done():
            self._scheduler_task = asyncio.create_task(scheduler.scheduler_loop(self))

    # -- registration ----------------------------------------------
    def _register(self) -> None:
        dp = self.dp
        dp.message.register(self.cmd_start, Command("start"))
        dp.callback_query.register(self.on_poll_vote, F.data.startswith("poll:"))
        dp.callback_query.register(self.on_usual, F.data == menu.CB_USUAL)
        dp.callback_query.register(
            self.on_menu_results, F.data.in_({menu.CB_RESULTS, menu.CB_GROUP_RESULTS})
        )
        dp.callback_query.register(self.on_admin_callback, F.data.startswith(admin.ADMIN_PREFIX))
        dp.message.register(self.on_text)

    # -- handlers ------------------------------------------------
    async def cmd_start(self, message: Message) -> None:
        chat = message.chat
        if chat.type == "private":
            self._register_dm_user(message.from_user)
            await menu.send_action_menu(self, chat.id, private=True)
        else:
            self.poll_chats.add(chat.id)
            await self.start_scheduler()
            await self._refresh_action_menu(chat.id, private=False)

    async def on_poll_vote(self, cq: CallbackQuery) -> None:
        try:
            _, date, cidx, oidx = cq.data.split(":")
            cidx, oidx = int(cidx), int(oidx)
        except ValueError:
            await cq.answer()
            return

        action, entry = polls.toggle_vote(self.storage, date, cidx, oidx, cq.from_user.id)
        if action is None:
            await cq.answer("Опрос больше не активен.", show_alert=False)
            return

        polls.remember_name(self.storage, date, cq.from_user.id,
                            self._display_name(cq.from_user))
        category = CATEGORIES[cidx]
        try:
            await cq.message.edit_reply_markup(
                reply_markup=polls.poll_keyboard(entry, category, date, cq.from_user.id)
            )
        except TelegramBadRequest:
            pass
        await cq.answer(_VOTE_TOAST.get(action, "Готово"))

    async def on_usual(self, cq: CallbackQuery) -> None:
        user = cq.from_user
        date, iso = current_poll_date(self.storage)
        res = stats.usual_picks(self.storage, user.id, now(self.tz).date())
        picks = res["picks"]
        if not picks:
            await cq.answer(
                "Пока нет истории заказов. Проголосуйте вручную — бот запомнит выбор.",
                show_alert=True,
            )
            return

        applied = []
        for category, option in picks.items():
            if polls.set_vote(self.storage, date, category, option, user.id):
                applied.append(category)
        polls.remember_name(self.storage, date, user.id, self._display_name(user))

        day = polls.get_day(self.storage, date) or {"categories": {}}
        for category in applied:
            entry = day["categories"].get(category)
            if not entry:
                continue
            try:
                await self.bot.edit_message_reply_markup(
                    chat_id=cq.message.chat.id,
                    message_id=entry["message_id"],
                    reply_markup=polls.poll_keyboard(entry, category, date, user.id),
                )
            except TelegramBadRequest:
                pass

        if res["enough"]:
            head = "🔁 Готово! Ваш обычный набор:"
        else:
            head = (
                f"ℹ️ Пока недостаточно данных для «как обычно» "
                f"(история {res['span_days']} дн., нужно {stats.USUAL_MIN_DAYS}). "
                f"Проголосовал(а) по тому, что есть:"
            )
        body = [head, stats.format_picks(picks)]
        not_in_menu = [picks[c] for c in picks if c not in applied
                       and picks[c] not in _current_options(day, c)]
        if not_in_menu:
            body.append("\nСегодня нет в меню: " + ", ".join(not_in_menu))

        if await self._safe_dm(user.id, "\n".join(body)):
            await cq.answer("Детали отправил(а) в личку.")
        else:
            await cq.answer(
                "Готово. Нажмите «Написать боту», чтобы получать детали в личке.",
                show_alert=True,
            )

    async def on_menu_results(self, cq: CallbackQuery) -> None:
        chat = cq.message.chat
        private = chat.type == "private"
        date, _ = current_poll_date(self.storage)
        text = polls.results_text(self.storage, date)
        if not private:
            hhmm = now(self.tz).strftime("%H:%M")
            text += f"\n\nОбновил(а) {self._display_name(cq.from_user)} в {hhmm}"

        prev = self.last_results_msg.get(chat.id)
        if prev:
            try:
                await self.bot.delete_message(chat.id, prev)
            except TelegramBadRequest:
                pass
        sent = await self.bot.send_message(chat.id, text)
        self.last_results_msg[chat.id] = sent.message_id
        await cq.answer()
        await self._refresh_action_menu(chat.id, private=private)

    async def on_admin_callback(self, cq: CallbackQuery) -> None:
        if cq.message.chat.type != "private":
            await cq.answer("Админ-панель доступна только в личке с ботом.", show_alert=True)
            return
        await cq.answer()
        await admin.handle_callback(self, cq)

    async def on_text(self, message: Message) -> None:
        # In the group the bot never chats — only polls / results / action menu.
        if message.chat.type != "private":
            return
        await admin.handle_text(self, message)

    # -- lifecycle -------------------------------------------------
    async def run(self) -> None:  # pragma: no cover - needs a live network
        try:
            me = await self.bot.get_me()
            self.bot_username = me.username
        except Exception:
            log.warning("could not fetch bot username")
        stats.migrate_history(self.storage)
        dishes.ensure_seeded(self.storage)
        if self.chat_id:
            self.poll_chats.add(self.chat_id)
            await self.start_scheduler()
        await self.dp.start_polling(self.bot)


def _current_options(day: dict, category: str) -> list:
    entry = day.get("categories", {}).get(category)
    return entry["options"] if entry else []
