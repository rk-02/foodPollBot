"""Daily loop: send the poll set at poll time, post + record results at 18:00.

Weekends are completely silent.  Everything is dedup-keyed by calendar day so
the 20-second tick can fire several times in the target minute harmlessly.
"""

import asyncio
import logging

from . import polls, stats
from .config import CATEGORIES, POLL_SHIFT, RESULTS_HOUR, RESULTS_MINUTE
from .menu_config import get_day_menu, get_poll_time
from .timeutil import current_poll_date, now

log = logging.getLogger(__name__)


async def send_poll_set(app, moment=None):
    """Post the four custom polls for the upcoming meal day + the action menu."""
    moment = moment or now()
    poll_index = (moment.weekday() + POLL_SHIFT) % 7
    if poll_index >= 5:  # meal day falls on Sat/Sun
        log.info("skipping poll — target day is a weekend (%s)", poll_index)
        return None

    date, iso = current_poll_date(app.storage, moment)
    day_menu = get_day_menu(app.storage, poll_index)
    polls.start_day(app.storage, date, iso, poll_index)

    sent_any = False
    for category in CATEGORIES:
        options = day_menu.get(category, [])
        if not options:
            continue
        msg = await app.bot.send_message(
            app.chat_id,
            polls.poll_header(category, date),
            reply_markup=polls.poll_keyboard(
                {"options": list(options), "votes": {}}, category, date,
            ),
        )
        polls.register_poll(app.storage, date, category, msg.message_id, options)
        sent_any = True

    if sent_any:
        stats.record_poll_round(app.storage, poll_index)

    menu_msg = await app._refresh_action_menu(app.chat_id, private=False)
    polls.set_action_menu_message(app.storage, date, menu_msg.message_id)
    return date


async def send_results(app, moment=None):
    """Post the grouped result to the group and snapshot picks into history."""
    moment = moment or now()
    date, iso = current_poll_date(app.storage, moment)
    text = polls.results_text(app.storage, date)
    await app.bot.send_message(app.chat_id, text)

    day = polls.get_day(app.storage, date)
    if day:
        votes_by_user = polls.user_votes(app.storage, date)
        stats.record_orders(
            app.storage, day.get("iso", iso), votes_by_user, day.get("names", {}),
        )
    return date


async def tick(app, moment=None):
    moment = moment or now()
    if moment.weekday() >= 5:
        return
    hour, minute = get_poll_time(app.storage)
    day_key = moment.date().isoformat()

    if (moment.hour, moment.minute) == (hour, minute) and app._last_poll_day != day_key:
        app._last_poll_day = day_key
        await send_poll_set(app, moment)

    if (moment.hour, moment.minute) == (RESULTS_HOUR, RESULTS_MINUTE) \
            and app._last_results_day != day_key:
        app._last_results_day = day_key
        await send_results(app, moment)


async def scheduler_loop(app):
    log.info("scheduler started")
    while True:
        try:
            await tick(app)
        except asyncio.CancelledError:
            raise
        except Exception:
            log.exception("scheduler tick failed")
        await asyncio.sleep(app.tick_seconds)
