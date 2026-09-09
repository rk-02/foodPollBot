"""Editable runtime configuration: poll time + per-weekday menu.

The menu the polls are actually built from lives in ``config.json`` and is
edited through the admin panel.  On first run (or on "Синхронизировать из
schedule.json") it is copied from the ``schedule.json`` template.
"""

import re

from .config import CATEGORIES, DEFAULT_POLL_TIME
from .dishes import _clean
from .storage import Storage

_TIME_RE = re.compile(r"^\s*(\d{1,2})[:.\s](\d{2})\s*$")


# --- poll time ---------------------------------------------------------

def parse_time(text: str):
    """"12:00" / "9.5" style -> (hour, minute) or None."""
    if not text:
        return None
    m = _TIME_RE.match(text)
    if not m:
        return None
    hour, minute = int(m.group(1)), int(m.group(2))
    if 0 <= hour <= 23 and 0 <= minute <= 59:
        return hour, minute
    return None


def get_poll_time_str(storage: Storage) -> str:
    return storage.load_config().get("poll_time", DEFAULT_POLL_TIME)


def get_poll_time(storage: Storage):
    parsed = parse_time(get_poll_time_str(storage))
    return parsed or parse_time(DEFAULT_POLL_TIME)


def set_poll_time(storage: Storage, text: str) -> bool:
    parsed = parse_time(text)
    if not parsed:
        return False
    cfg = storage.load_config()
    cfg["poll_time"] = f"{parsed[0]:02d}:{parsed[1]:02d}"
    storage.save_config(cfg)
    return True


# --- per-weekday menu ------------------------------------------------

def _schedule_day_menu(storage: Storage, weekday_idx: int) -> dict:
    schedule = storage.load_schedule()
    menu = {cat: [] for cat in CATEGORIES}
    if 0 <= weekday_idx < len(schedule):
        for poll in schedule[weekday_idx]:
            cat = poll.get("question")
            if cat in menu:
                menu[cat] = [
                    _clean(o) for o in poll.get("options", [])
                    if _clean(o) and _clean(o) != "-"
                ]
    return menu


def get_day_menu(storage: Storage, weekday_idx: int) -> dict:
    """Active menu for a weekday (0=Mon .. 4=Fri).

    Falls back to the schedule.json template for any category the admin has
    never touched.
    """
    cfg = storage.load_config()
    stored = cfg.get("menu", {}).get(str(weekday_idx), {})
    fallback = _schedule_day_menu(storage, weekday_idx)
    return {cat: list(stored.get(cat, fallback.get(cat, []))) for cat in CATEGORIES}


def set_day_category(storage: Storage, weekday_idx: int, category: str, options: list) -> None:
    if category not in CATEGORIES:
        raise ValueError(f"unknown category: {category}")
    cfg = storage.load_config()
    menu = cfg.setdefault("menu", {})
    day = menu.setdefault(str(weekday_idx), {})
    # keep a stable, de-duplicated order
    seen, cleaned = set(), []
    for opt in options:
        name = _clean(opt)
        if name and name.lower() not in seen:
            seen.add(name.lower())
            cleaned.append(name)
    day[category] = cleaned
    storage.save_config(cfg)


def sync_from_schedule(storage: Storage) -> dict:
    """Overwrite the whole per-day menu from schedule.json and re-seed dishes.

    Returns the freshly written menu block.
    """
    from . import dishes

    schedule = storage.load_schedule()
    cfg = storage.load_config()
    menu: dict[str, dict] = {}
    for idx in range(min(len(schedule), 5)):
        menu[str(idx)] = _schedule_day_menu(storage, idx)
    cfg["menu"] = menu
    storage.save_config(cfg)

    # re-seed / extend the global dish DB with the union of the template
    seeded = dishes.seed_from_schedule(storage)
    current = storage.load_dishes()
    for cat, names in seeded.items():
        bucket = current.setdefault(cat, [])
        for name in names:
            if not any(name.lower() == e.lower() for e in bucket):
                bucket.append(name)
        bucket.sort(key=str.lower)
    storage.save_dishes(current)
    return menu
