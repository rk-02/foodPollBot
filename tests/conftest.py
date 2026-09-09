import itertools
import json
import os
import shutil
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

os.environ.setdefault("BOT_TOKEN", "123456:TESTTOKEN")
os.environ.setdefault("CHAT_ID", "-1001234567890")
os.environ.setdefault("POLL_START_HOUR", "12")
os.environ.setdefault("POLL_START_MINUTES", "0")
os.environ.setdefault("POLL_SHIFT", "1")
os.environ.setdefault("RESULTS_HOUR", "18")
os.environ.setdefault("RESULTS_MINUTE", "0")


@pytest.fixture
def storage(tmp_path):
    """A Storage rooted at a tmp dir, pre-populated with the schedule template."""
    from app.storage import Storage

    shutil.copy(os.path.join(REPO_ROOT, "schedule.json"), tmp_path / "schedule.json")
    return Storage(str(tmp_path))


@pytest.fixture
def legacy_history(storage):
    (storage._path("orders_history.json"))
    data = {
        "111": {"18.03": {"Вторые блюда": "Гуляш", "Гарниры": "Рис"}},
        "222": {"19.03": {"Вторые блюда": "Тефтели", "Гарниры": "Гречка"}},
    }
    storage.save_history(data)
    return data


@pytest.fixture
def app(storage):
    from app.bot import FoodPollBot

    counter = itertools.count(1000)

    def _sent(*_a, **_k):
        return SimpleNamespace(message_id=next(counter))

    bot = AsyncMock()
    bot.send_message = AsyncMock(side_effect=_sent)
    bot.edit_message_reply_markup = AsyncMock()
    bot.edit_message_text = AsyncMock()
    bot.delete_message = AsyncMock()

    instance = FoodPollBot(storage=storage, bot=bot)
    instance.bot_username = "foodpoll_bot"
    instance.chat_id = -100
    return instance


@pytest.fixture
def make_message():
    counter = itertools.count(1)

    def _mk(text=None, chat_id=1, chat_type="private", user_id=1,
            first_name="User", last_name=None, username="user", message_id=None):
        mid = message_id if message_id is not None else next(counter)
        msg = AsyncMock()
        msg.text = text
        msg.message_id = mid
        msg.chat = SimpleNamespace(id=chat_id, type=chat_type)
        msg.from_user = SimpleNamespace(
            id=user_id, first_name=first_name, last_name=last_name, username=username,
        )
        msg.answer = AsyncMock(return_value=SimpleNamespace(message_id=mid + 10000))
        msg.delete = AsyncMock()
        msg.edit_text = AsyncMock()
        msg.edit_reply_markup = AsyncMock()
        return msg

    return _mk


@pytest.fixture
def make_cq():
    counter = itertools.count(1)

    def _mk(data, chat_id=1, chat_type="private", user_id=1, first_name="User"):
        mid = next(counter)
        message = AsyncMock()
        message.message_id = mid
        message.chat = SimpleNamespace(id=chat_id, type=chat_type)
        message.answer = AsyncMock(return_value=SimpleNamespace(message_id=mid + 50000))
        message.delete = AsyncMock()
        message.edit_text = AsyncMock()
        message.edit_reply_markup = AsyncMock()
        return SimpleNamespace(
            data=data,
            message=message,
            from_user=SimpleNamespace(
                id=user_id, first_name=first_name, last_name=None, username="u",
            ),
            answer=AsyncMock(),
        )

    return _mk


@pytest.fixture
def seeded_poll(app):
    """A live poll set for date '10.09' (menu_weekday=2) with a couple of votes."""
    from app import polls

    polls.start_day(app.storage, "10.09", "2026-09-10", 2)
    polls.register_poll(app.storage, "10.09", "Первые блюда", 501, ["Куриный", "Щи"])
    polls.register_poll(app.storage, "10.09", "Вторые блюда", 502, ["Гуляш", "Тефтели"])
    polls.register_poll(app.storage, "10.09", "Гарниры", 503, ["Рис", "Гречка"])
    polls.register_poll(app.storage, "10.09", "Салаты", 504, ["Зимний", "Обжорка"])
    return "10.09"


@pytest.fixture
def live_poll(app):
    """A live poll set for whatever date current_poll_date() resolves to now."""
    from app import polls
    from app.timeutil import current_poll_date

    date, iso = current_poll_date(app.storage)
    polls.start_day(app.storage, date, iso, 0)
    polls.register_poll(app.storage, date, "Первые блюда", 601, ["Куриный", "Щи"])
    polls.register_poll(app.storage, date, "Вторые блюда", 602, ["Гуляш", "Тефтели"])
    polls.register_poll(app.storage, date, "Гарниры", 603, ["Рис", "Гречка"])
    polls.register_poll(app.storage, date, "Салаты", 604, ["Зимний", "Обжорка"])
    return date


@pytest.fixture
def no_scheduler(monkeypatch):
    """Neutralise the background scheduler loop for handler tests."""
    async def _noop(_app):
        return

    monkeypatch.setattr("app.scheduler.scheduler_loop", _noop)
    return _noop
