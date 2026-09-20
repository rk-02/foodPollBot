from datetime import datetime
from unittest.mock import AsyncMock

import pytest

from app import scheduler
from app.config import POLL_SHIFT


def _at(day):
    # 2026-09-20 is a Sunday
    return datetime(2026, 9, day, 12, 0)


@pytest.mark.asyncio
@pytest.mark.parametrize("day,expected", [(20, True), (21, True), (25, False), (26, False)])
async def test_tick_runs_on_days_before_a_weekday(app, monkeypatch, day, expected):
    if POLL_SHIFT != 1:
        pytest.skip("assumes POLL_SHIFT=1")
    monkeypatch.setattr(scheduler, "get_poll_time", lambda s: (12, 0))
    send = AsyncMock()
    monkeypatch.setattr(scheduler, "send_poll_set", send)
    app._last_poll_day = None
    await scheduler.tick(app, _at(day))
    assert send.called is expected
