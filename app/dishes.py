"""Global dish database.

``dishes.json`` holds every dish the admin can pick from, grouped by category::

    {"Первые блюда": ["Куриный", "Щи", ...], "Вторые блюда": [...], ...}

It is seeded once from the union of everything in ``schedule.json`` and then
grown/pruned through the admin panel.
"""

from .config import CATEGORIES
from .storage import Storage


def _clean(name: str) -> str:
    return " ".join(str(name).split()).strip()


def seed_from_schedule(storage: Storage) -> dict:
    """Build a fresh dish DB from the union of all options in schedule.json."""
    schedule = storage.load_schedule()
    db: dict[str, list[str]] = {cat: [] for cat in CATEGORIES}
    for day in schedule:
        for poll in day:
            cat = poll.get("question")
            if cat not in db:
                continue
            for opt in poll.get("options", []):
                name = _clean(opt)
                if name and name != "-" and name not in db[cat]:
                    db[cat].append(name)
    for cat in db:
        db[cat].sort(key=str.lower)
    return db


def ensure_seeded(storage: Storage) -> dict:
    """Return the dish DB, seeding + persisting it on first use."""
    db = storage.load_dishes()
    if not db or not any(db.get(cat) for cat in CATEGORIES):
        db = seed_from_schedule(storage)
        storage.save_dishes(db)
        return db
    # make sure every category key exists
    missing = [cat for cat in CATEGORIES if cat not in db]
    if missing:
        for cat in missing:
            db[cat] = []
        storage.save_dishes(db)
    return db


def get_db(storage: Storage) -> dict:
    return ensure_seeded(storage)


def list_dishes(storage: Storage, category: str) -> list[str]:
    return list(get_db(storage).get(category, []))


def add_dish(storage: Storage, category: str, name: str) -> bool:
    """Add a dish to a category. Returns True if it was actually added."""
    name = _clean(name)
    if not name or category not in CATEGORIES:
        return False
    db = get_db(storage)
    bucket = db.setdefault(category, [])
    if any(name.lower() == existing.lower() for existing in bucket):
        return False
    bucket.append(name)
    bucket.sort(key=str.lower)
    storage.save_dishes(db)
    return True


def remove_dish(storage: Storage, category: str, name: str) -> bool:
    """Remove a dish from a category. Returns True if it was present."""
    name = _clean(name)
    db = get_db(storage)
    bucket = db.get(category, [])
    for existing in list(bucket):
        if existing.lower() == name.lower():
            bucket.remove(existing)
            storage.save_dishes(db)
            return True
    return False
