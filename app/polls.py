"""Custom poll engine.

Telegram's native polls can't do single-select-per-category with server-side
vote bookkeeping, "vote for me", or live option edits, so every poll is just a
normal message with an inline keyboard:

    one button per option  ->  callback_data "poll:<dd.mm>:<cat_idx>:<opt_idx>"

Votes are stored server-side in ``poll_state.json`` as ``option -> [user_id]``.
Voting is single-select inside one category (a second tap on your choice clears
it, a tap on another option switches).
"""

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from .config import CATEGORIES, CATEGORY_EMOJI
from .dishes import _clean
from .storage import Storage

VOTE_MARK = "🟢 "


# --- state helpers ---------------------------------------------------

def _state(storage: Storage) -> dict:
    return storage.load_poll_state()


def get_day(storage: Storage, date: str):
    return _state(storage).get(date)


def start_day(storage: Storage, date: str, iso: str, menu_weekday: int) -> dict:
    """(Re)initialise the poll set for a date, wiping any previous votes."""
    state = _state(storage)
    state[date] = {
        "iso": iso,
        "menu_weekday": menu_weekday,
        "action_menu_message_id": None,
        "names": {},
        "categories": {},
    }
    storage.save_poll_state(state)
    return state[date]


def register_poll(storage: Storage, date: str, category: str,
                  message_id: int, options: list) -> dict:
    state = _state(storage)
    day = state.setdefault(date, {
        "iso": date, "menu_weekday": None,
        "action_menu_message_id": None, "names": {}, "categories": {},
    })
    day["categories"][category] = {
        "message_id": message_id,
        "options": [_clean(o) for o in options],
        "votes": {},
    }
    storage.save_poll_state(state)
    return day["categories"][category]


def set_action_menu_message(storage: Storage, date: str, message_id: int) -> None:
    state = _state(storage)
    if date in state:
        state[date]["action_menu_message_id"] = message_id
        storage.save_poll_state(state)


def remember_name(storage: Storage, date: str, user_id: int, name: str) -> None:
    state = _state(storage)
    day = state.get(date)
    if day is None:
        return
    day.setdefault("names", {})[str(user_id)] = name or f"ID{user_id}"
    storage.save_poll_state(state)


# --- rendering -----------------------------------------------------

def poll_header(category: str, date: str) -> str:
    emoji = CATEGORY_EMOJI.get(category, "🍴")
    return (
        f"{emoji} {category} — {date}\n"
        f"Нажмите вариант, чтобы проголосовать. "
        f"Повторное нажатие снимает голос."
    )


def _voted_option(entry: dict, user_id: int):
    for opt, users in entry.get("votes", {}).items():
        if user_id in users:
            return opt
    return None


def poll_keyboard(entry: dict, category: str, date: str, user_id: int | None = None) -> InlineKeyboardMarkup:
    cat_idx = CATEGORIES.index(category)
    mine = _voted_option(entry, user_id) if user_id is not None else None
    rows = []
    for opt_idx, opt in enumerate(entry["options"]):
        count = len(entry.get("votes", {}).get(opt, []))
        label = f"{VOTE_MARK if opt == mine else ''}{opt}"
        if count:
            label += f" · {count}"
        rows.append([InlineKeyboardButton(
            text=label,
            callback_data=f"poll:{date}:{cat_idx}:{opt_idx}",
        )])
    return InlineKeyboardMarkup(inline_keyboard=rows)


# --- voting -------------------------------------------------------

def _remove_user(votes: dict, user_id: int):
    previous = None
    for opt in list(votes.keys()):
        if user_id in votes[opt]:
            previous = opt
            votes[opt] = [u for u in votes[opt] if u != user_id]
    return previous


def toggle_vote(storage: Storage, date: str, cat_idx: int, opt_idx: int, user_id: int):
    """Returns (action, entry) where action is
    'added' | 'switched' | 'removed' | None (invalid)."""
    state = _state(storage)
    day = state.get(date)
    if day is None or not (0 <= cat_idx < len(CATEGORIES)):
        return None, None
    category = CATEGORIES[cat_idx]
    entry = day["categories"].get(category)
    if entry is None or not (0 <= opt_idx < len(entry["options"])):
        return None, entry
    option = entry["options"][opt_idx]
    votes = entry.setdefault("votes", {})
    previous = _remove_user(votes, user_id)
    if previous == option:
        action = "removed"
    else:
        votes.setdefault(option, []).append(user_id)
        action = "switched" if previous is not None else "added"
    entry["votes"] = {o: u for o, u in votes.items() if u}
    storage.save_poll_state(state)
    return action, entry


def set_vote(storage: Storage, date: str, category: str, option: str, user_id: int) -> bool:
    """Force ``user_id``'s vote in ``category`` to ``option``.

    Used by "Мне как обычно". No-op (returns False) when the option is not on
    today's poll or the user already picked it.
    """
    state = _state(storage)
    day = state.get(date)
    if day is None:
        return False
    entry = day["categories"].get(category)
    if entry is None or option not in entry["options"]:
        return False
    votes = entry.setdefault("votes", {})
    if _voted_option(entry, user_id) == option:
        return False
    _remove_user(votes, user_id)
    votes.setdefault(option, []).append(user_id)
    entry["votes"] = {o: u for o, u in votes.items() if u}
    storage.save_poll_state(state)
    return True


# --- live menu edits ---------------------------------------------

def apply_menu_change(storage: Storage, date: str, category: str, new_options: list) -> dict:
    """Update a live poll's option list, dropping votes for removed options.

    Returns {"live": bool, "removed": [...], "added": [...]}.
    """
    new_options = [_clean(o) for o in new_options if _clean(o)]
    state = _state(storage)
    day = state.get(date)
    entry = day["categories"].get(category) if day else None
    if entry is None:
        return {"live": False, "removed": [], "added": []}
    old = list(entry["options"])
    removed = [o for o in old if o not in new_options]
    added = [o for o in new_options if o not in old]
    entry["options"] = new_options
    entry["votes"] = {
        o: u for o, u in entry.get("votes", {}).items() if o in new_options and u
    }
    storage.save_poll_state(state)
    return {"live": True, "removed": removed, "added": added}


def describe_change(category: str, date: str, diff: dict) -> str:
    removed, added = diff.get("removed", []), diff.get("added", [])
    if not removed and not added:
        return ""
    lines = []
    if len(removed) == 1 and len(added) == 1:
        lines.append(f"• заменено: «{removed[0]}» → «{added[0]}»")
    else:
        lines += [f"• удалено: «{r}»" for r in removed]
        lines += [f"• добавлено: «{a}»" for a in added]
    return (
        f"⚠️ Изменения в меню — {category} ({date}):\n"
        + "\n".join(lines)
        + "\n\nПожалуйста, переголосуйте."
    )


# --- reading results -------------------------------------------

def user_votes(storage: Storage, date: str) -> dict:
    day = get_day(storage, date)
    result: dict[int, dict] = {}
    if not day:
        return result
    for category, entry in day["categories"].items():
        for opt, users in entry.get("votes", {}).items():
            for uid in users:
                result.setdefault(uid, {})[category] = opt
    return result


def results_text(storage: Storage, date: str) -> str:
    day = get_day(storage, date)
    if not day or not day.get("categories"):
        return f"🗓 {date}\n\nПока нет опросов на эту дату."

    lines = [f"🗓 {date}", ""]
    any_votes = False
    for cat in CATEGORIES:
        entry = day["categories"].get(cat)
        if not entry:
            continue
        tallies = [
            (opt, len(entry.get("votes", {}).get(opt, [])))
            for opt in entry["options"]
        ]
        tallies = [t for t in tallies if t[1] > 0]
        if not tallies:
            continue
        any_votes = True
        lines.append(f"{CATEGORY_EMOJI.get(cat, '🍴')} {cat}:")
        for opt, n in sorted(tallies, key=lambda t: (-t[1], t[0].lower())):
            lines.append(f"  • {opt}: {n}")
        lines.append("")

    combos = user_votes(storage, date)
    if combos:
        any_votes = True
        names = day.get("names", {})
        lines.append("👥 По людям:")
        ordered = sorted(
            combos.items(),
            key=lambda kv: names.get(str(kv[0]), str(kv[0])).lower(),
        )
        for i, (uid, picks) in enumerate(ordered, 1):
            name = names.get(str(uid), f"ID{uid}")
            parts = [picks[c] for c in CATEGORIES if picks.get(c)]
            lines.append(f"{i}. {name} — " + " + ".join(parts))

    if not any_votes:
        return f"🗓 {date}\n\nНет голосов."
    return "\n".join(lines).rstrip()
