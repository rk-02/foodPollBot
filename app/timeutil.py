"""Small time helpers shared by the scheduler and the menu handlers."""

from datetime import datetime, timedelta

from .config import POLL_SHIFT, TIMEZONE
from .menu_config import get_poll_time
from .storage import Storage


def now(tz=None) -> datetime:
    return datetime.now(tz or TIMEZONE)


def current_poll_date(storage: Storage, moment: datetime | None = None):
    """('dd.mm', 'YYYY-MM-DD') the active poll set refers to.

    Before today's poll time  -> today's own date (yesterday's poll is still
    the current one).  At/after poll time -> today + POLL_SHIFT (the poll that
    was just sent).  Poll-send and results-read therefore always agree.
    """
    moment = moment or now()
    hour, minute = get_poll_time(storage)
    if (moment.hour, moment.minute) < (hour, minute):
        target = moment
    else:
        target = moment + timedelta(days=POLL_SHIFT)
    return target.strftime("%d.%m"), target.date().isoformat()
