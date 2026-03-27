import importlib
from datetime import datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest


@pytest.fixture
def bot_module(monkeypatch):
    monkeypatch.setenv("BOT_TOKEN", "123456:TESTTOKEN")
    monkeypatch.setenv("CHAT_ID", "-1001234567890")
    monkeypatch.setenv("POLL_START_HOUR", "12")
    monkeypatch.setenv("POLL_START_MINUTES", "0")
    monkeypatch.setenv("POLL_SHIFT", "1")
    mod = importlib.import_module("bot")
    return importlib.reload(mod)


@pytest.fixture
def telegram_bot(bot_module):
    tb = bot_module.TelegramBot()
    tb.bot = AsyncMock()
    return tb


@pytest.fixture
def computed_date(bot_module):
    now = datetime.now(bot_module.TIMEZONE)
    if now.hour < bot_module.POLL_START_HOUR and now.minute < bot_module.POLL_START_MINUTES:
        return now.strftime("%d.%m")
    now += timedelta(days=bot_module.POLL_SHIFT)
    return now.strftime("%d.%m")


@pytest.fixture
def poll_obj():
    def _mk(poll_id: str, question: str, options_and_votes):
        options = [
            SimpleNamespace(text=text, voter_count=votes)
            for text, votes in options_and_votes
        ]
        return SimpleNamespace(id=poll_id, question=question, options=options)

    return _mk


@pytest.fixture
def poll_answer_obj():
    def _mk(user_id: int, first_name: str, poll_id: str, option_ids):
        return SimpleNamespace(
            user=SimpleNamespace(id=user_id, first_name=first_name),
            poll_id=poll_id,
            option_ids=option_ids,
        )

    return _mk


@pytest.fixture
def callback_query_obj():
    def _mk(chat_id: int, chat_type: str = "private", user_id: int = 1, first_name: str = "User"):
        msg = AsyncMock()
        msg.chat = SimpleNamespace(id=chat_id, type=chat_type)
        msg.answer = AsyncMock(return_value=AsyncMock())
        msg.delete = AsyncMock()
        return SimpleNamespace(
            message=msg,
            from_user=SimpleNamespace(id=user_id, first_name=first_name, last_name=None, username="user"),
            data="get_group_results",
            answer=AsyncMock(),
        )

    return _mk
