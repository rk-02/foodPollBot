"""Order history + the "Мне как обычно" computation.

``orders_history.json`` maps ``user_id -> ISO-date -> {category: option}``.

"Мне как обычно" is **weekday-aware**: it looks at what the user usually takes
on *this* day of the week, and only falls back to their all-days history when a
weekday favourite is missing from today's menu.

The button itself is hidden until every weekday (Mon-Fri) has collected at
least ``USUAL_MIN_ROUNDS`` poll rounds (~2 weeks) — counted in
``config.json["poll_rounds"]``.
"""

import re
from collections import Counter
from datetime import date, datetime, timedelta

from .config import CATEGORIES, USUAL_WINDOW_DAYS
from .storage import Storage

_ISO_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_DDMM_RE = re.compile(r"^(\d{1,2})[.\-/](\d{1,2})$")

USUAL_MIN_ROUNDS = 2          # per weekday, before the button appears
USUAL_MIN_WEEKDAY_RECORDS = 2  # personal same-weekday orders for a confident answer


# --- history migration / recording ---------------------------------

def migrate_history(storage: Storage, assume_year: int | None = None) -> bool:
    """Re-key legacy ``dd.mm`` history entries to full ISO dates. Idempotent."""
    assume_year = assume_year or date.today().year
    history = storage.load_history()
    changed = False
    for user_id, entries in list(history.items()):
        if not isinstance(entries, dict):
            continue
        new_entries: dict[str, dict] = {}
        for key, value in entries.items():
            if _ISO_RE.match(key):
                new_entries[key] = value
                continue
            m = _DDMM_RE.match(key)
            if m:
                day_, month = int(m.group(1)), int(m.group(2))
                try:
                    new_entries[date(assume_year, month, day_).isoformat()] = value
                    changed = True
                    continue
                except ValueError:
                    pass
            changed = True  # unparseable legacy key -> drop it
        history[user_id] = new_entries
    if changed:
        storage.save_history(history)
    return changed


def record_orders(storage: Storage, iso_date: str, votes_by_user: dict,
                  names: dict | None = None) -> None:
    """Persist the final per-user picks for a day into the history."""
    history = storage.load_history()
    for user_id, picks in votes_by_user.items():
        clean = {c: picks[c] for c in CATEGORIES if picks.get(c)}
        if not clean:
            continue
        history.setdefault(str(user_id), {})[iso_date] = clean
    storage.save_history(history)


# --- poll-round counter (gates the "Мне как обычно" button) ------

def record_poll_round(storage: Storage, weekday: int) -> None:
    cfg = storage.load_config()
    rounds = cfg.setdefault("poll_rounds", {})
    rounds[str(weekday)] = int(rounds.get(str(weekday), 0)) + 1
    storage.save_config(cfg)


def poll_rounds(storage: Storage) -> dict:
    raw = storage.load_config().get("poll_rounds", {})
    return {wd: int(raw.get(str(wd), 0)) for wd in range(5)}


def usual_button_ready(storage: Storage) -> bool:
    return all(n >= USUAL_MIN_ROUNDS for n in poll_rounds(storage).values())


# --- "Мне как обычно" ------------------------------------------

def _parse_iso(key: str):
    try:
        return datetime.strptime(key, "%Y-%m-%d").date()
    except ValueError:
        return None


def _ranked(source: dict, category: str) -> list:
    counter = Counter(v[category] for v in source.values() if v.get(category))
    return [opt for opt, _ in counter.most_common()]


def usual_picks(storage: Storage, user_id: int, weekday: int | None = None,
                available: dict | None = None, today: date | None = None) -> dict:
    """Resolve the user's "usual" pick per category for a given weekday.

    Per category the candidate order is: most frequent on *this weekday* first,
    then most frequent across all days.  With ``available`` given, the first
    candidate that is actually on today's poll wins; a category with no usable
    candidate is left out.

    Returns ``{"picks": {cat: opt}, "weekday_records": int, "enough": bool,
    "fallbacks": [cat, ...]}`` where ``fallbacks`` lists categories whose
    weekday favourite was unavailable and a runner-up was taken instead.
    """
    today = today or date.today()
    raw = storage.load_history().get(str(user_id), {})
    dated = {}
    for key, value in raw.items():
        parsed = _parse_iso(key)
        if parsed and isinstance(value, dict):
            dated[parsed] = value
    if not dated:
        return {"picks": {}, "weekday_records": 0, "enough": False, "fallbacks": []}

    window_start = today - timedelta(days=USUAL_WINDOW_DAYS)
    windowed = {d: v for d, v in dated.items() if d >= window_start} or dated
    same_wd = {
        d: v for d, v in windowed.items()
        if weekday is None or d.weekday() == weekday
    }

    picks: dict[str, str] = {}
    fallbacks: list[str] = []
    for category in CATEGORIES:
        wd_ranked = _ranked(same_wd, category)
        all_ranked = _ranked(windowed, category)
        ordered = wd_ranked + [o for o in all_ranked if o not in wd_ranked]
        if not ordered:
            continue
        if available is None:
            picks[category] = ordered[0]
            continue
        menu_options = available.get(category) or []
        chosen = next((o for o in ordered if o in menu_options), None)
        if chosen is None:
            continue
        picks[category] = chosen
        if wd_ranked and chosen != wd_ranked[0]:
            fallbacks.append(category)

    return {
        "picks": picks,
        "weekday_records": len(same_wd),
        "enough": len(same_wd) >= USUAL_MIN_WEEKDAY_RECORDS,
        "fallbacks": fallbacks,
    }


def format_picks(picks: dict) -> str:
    if not picks:
        return "— (вы ещё ничего не выбирали)"
    return "\n".join(f"• {cat}: {picks[cat]}" for cat in CATEGORIES if picks.get(cat))
