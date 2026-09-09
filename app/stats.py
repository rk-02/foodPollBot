"""Order history + the "Мне как обычно" computation.

``orders_history.json`` maps ``user_id -> ISO-date -> {category: option}``.
"""

import re
from collections import Counter
from datetime import date, datetime, timedelta

from .config import CATEGORIES, USUAL_MIN_DAYS, USUAL_WINDOW_DAYS
from .storage import Storage

_ISO_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_DDMM_RE = re.compile(r"^(\d{1,2})[.\-/](\d{1,2})$")


def migrate_history(storage: Storage, assume_year: int | None = None) -> bool:
    """Re-key legacy ``dd.mm`` history entries to full ISO dates.

    Idempotent; returns True if anything changed.
    """
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
                    iso = date(assume_year, month, day_).isoformat()
                    new_entries[iso] = value
                    changed = True
                    continue
                except ValueError:
                    pass
            # unparseable legacy key -> drop it
            changed = True
        history[user_id] = new_entries
    if changed:
        storage.save_history(history)
    return changed


def record_orders(storage: Storage, iso_date: str, votes_by_user: dict,
                  names: dict | None = None) -> None:
    """Persist the final per-user picks for a day into the history."""
    names = names or {}
    history = storage.load_history()
    for user_id, picks in votes_by_user.items():
        clean = {c: picks[c] for c in CATEGORIES if picks.get(c)}
        if not clean:
            continue
        bucket = history.setdefault(str(user_id), {})
        bucket[iso_date] = clean
    storage.save_history(history)


def _parse_iso(key: str):
    try:
        return datetime.strptime(key, "%Y-%m-%d").date()
    except ValueError:
        return None


def usual_picks(storage: Storage, user_id: int, today: date | None = None) -> dict:
    """Most frequent pick per category for a user.

    Returns::

        {"enough": bool, "picks": {category: option}, "span_days": int,
         "records": int, "counts": {category: {option: n}}}

    ``enough`` is False when we have less than ``USUAL_MIN_DAYS`` between the
    first and last recorded order (spec: "меньше 2 недель").
    """
    today = today or date.today()
    raw = storage.load_history().get(str(user_id), {})
    dated = {d: v for d, v in raw.items() if _parse_iso(d) and isinstance(v, dict)}
    if not dated:
        return {"enough": False, "picks": {}, "span_days": 0, "records": 0, "counts": {}}

    days = sorted(_parse_iso(d) for d in dated)
    span_days = (days[-1] - days[0]).days

    window_start = today - timedelta(days=USUAL_WINDOW_DAYS)
    recent = {d: v for d, v in dated.items() if _parse_iso(d) >= window_start}
    source = recent or dated

    counts: dict[str, Counter] = {}
    picks: dict[str, str] = {}
    for cat in CATEGORIES:
        c = Counter(v[cat] for v in source.values() if v.get(cat))
        if c:
            counts[cat] = dict(c)
            picks[cat] = c.most_common(1)[0][0]

    return {
        "enough": span_days >= USUAL_MIN_DAYS,
        "picks": picks,
        "span_days": span_days,
        "records": len(dated),
        "counts": counts,
    }


def format_picks(picks: dict) -> str:
    if not picks:
        return "— (вы ещё ничего не выбирали)"
    return "\n".join(f"• {cat}: {picks[cat]}" for cat in CATEGORIES if picks.get(cat))
