"""Private-chat admin panel.

Everything is driven by ``adm:*`` callback buttons on a single message that
gets edited in place, plus a couple of free-text prompts (poll time, new dish
name) tracked through ``app.pending``.

    root
     ├─ ⏰ Время опроса            -> text prompt "HH:MM"
     ├─ 📋 Меню по дням           -> weekday -> category -> toggle dishes
     ├─ 🍽 База блюд              -> category -> add / delete dishes
     └─ 🔄 Синхронизировать из schedule.json
"""

from aiogram.exceptions import TelegramBadRequest
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from . import dishes, menu_config, polls
from .config import CATEGORIES, WEEKDAYS
from .menu_config import get_day_menu, get_poll_time_str
from .timeutil import current_poll_date

ADMIN_PREFIX = "adm:"


# --- keyboard helpers ---------------------------------------------

def _btn(text, data):
    return InlineKeyboardButton(text=text, callback_data=data)


def _kb(rows):
    return InlineKeyboardMarkup(inline_keyboard=rows)


def render_root(app):
    text = (
        "⚙️ *Админ-панель*\n\n"
        f"⏰ Время опроса: {get_poll_time_str(app.storage)}\n"
        "Выберите раздел."
    )
    kb = _kb([
        [_btn("⏰ Время опроса", "adm:time")],
        [_btn("📋 Меню по дням", "adm:days")],
        [_btn("🍽 База блюд", "adm:dishes")],
        [_btn("👁 Предпросмотр изменений", "adm:preview")],
        [_btn("📣 Отправить изменения опроса", "adm:notify")],
        [_btn("➕ Добавить голос", "adm:vote")],
        [_btn("🔄 Синхронизировать из schedule.json", "adm:sync")],
        [_btn("✖ Закрыть", "adm:close")],
    ])
    return text, kb


def render_manual_vote(app, draft):
    day = polls.get_day(app.storage, draft["date"])
    rows = []
    for ci, category in enumerate(CATEGORIES):
        entry = day["categories"].get(category)
        if not entry:
            continue
        for oi, option in enumerate(entry["options"]):
            mark = "✅ " if draft["picks"].get(category) == option else ""
            rows.append([_btn(f"{mark}{category}: {option}", f"adm:vpick:{ci}:{oi}")])
    rows.append([_btn("💾 Добавить голос", "adm:vsave")])
    rows.append([_btn("✖ Отмена", "adm:root")])
    return f"Голос за {draft['name']} ({draft['date']}). Выберите по одному блюду в каждой категории.", _kb(rows)


def render_days(app):
    rows = [[_btn(name, f"adm:day:{i}")] for i, name in enumerate(WEEKDAYS)]
    rows.append([_btn("⬅️ Назад", "adm:root")])
    return "📋 *Меню по дням*\nВыберите день недели.", _kb(rows)


def render_day(app, weekday: int):
    menu = get_day_menu(app.storage, weekday)
    rows = []
    for ci, cat in enumerate(CATEGORIES):
        n = len(menu.get(cat, []))
        rows.append([_btn(f"{cat} ({n})", f"adm:cat:{weekday}:{ci}")])
    rows.append([_btn("⬅️ Назад", "adm:days")])
    return f"📋 *{WEEKDAYS[weekday]}*\nВыберите категорию для настройки.", _kb(rows)


def _draft_dishes(app, category: str, selected: list):
    base = dishes.list_dishes(app.storage, category)
    extra = [s for s in selected if s not in base]
    return base + extra


def render_cat_edit(app, draft: dict):
    weekday, category = draft["weekday"], draft["category"]
    selected = draft["options"]
    all_dishes = _draft_dishes(app, category, selected)
    rows = []
    for idx, name in enumerate(all_dishes):
        mark = "✅" if name in selected else "⬜"
        rows.append([_btn(f"{mark} {name}", f"adm:tog:{idx}")])
    rows.append([_btn("💾 Сохранить", "adm:msave"), _btn("✖ Отмена", "adm:mcancel")])
    text = (
        f"*{WEEKDAYS[weekday]} — {category}*\n"
        f"Отмечено: {len(selected)}. Нажмите блюдо, чтобы включить/убрать его "
        f"из опроса этого дня.\n"
        f"Новые блюда добавляются в разделе «База блюд»."
    )
    return text, _kb(rows)


def render_dish_categories(app):
    db = dishes.get_db(app.storage)
    rows = [
        [_btn(f"{cat} ({len(db.get(cat, []))})", f"adm:dcat:{ci}")]
        for ci, cat in enumerate(CATEGORIES)
    ]
    rows.append([_btn("⬅️ Назад", "adm:root")])
    return "🍽 *База блюд*\nВыберите категорию.", _kb(rows)


def render_dish_cat(app, ci: int):
    category = CATEGORIES[ci]
    items = dishes.list_dishes(app.storage, category)
    rows = [[_btn(f"🗑 {name}", f"adm:ddel:{ci}:{idx}")] for idx, name in enumerate(items)]
    rows.append([_btn("➕ Добавить блюдо", f"adm:dadd:{ci}")])
    rows.append([_btn("⬅️ Назад", "adm:dishes")])
    text = f"🍽 *{category}* — {len(items)} блюд.\n🗑 удаляет блюдо из базы."
    return text, _kb(rows)


def render_sync_confirm(app):
    text = (
        "🔄 *Синхронизация из schedule.json*\n\n"
        "Меню всех дней будет перезаписано из шаблона, а база блюд дополнена. "
        "Продолжить?"
    )
    return text, _kb([
        [_btn("✅ Да, синхронизировать", "adm:sync!")],
        [_btn("⬅️ Назад", "adm:root")],
    ])


# --- editing the message in place -------------------------------

async def _show(cq, rendered):
    text, kb = rendered
    try:
        await cq.message.edit_text(text, reply_markup=kb, parse_mode="Markdown")
    except TelegramBadRequest:
        # "message is not modified" or the message is gone — send a fresh one
        await cq.message.answer(text, reply_markup=kb, parse_mode="Markdown")


# --- live-poll propagation -------------------------------------

async def _propagate_menu_change(app, weekday: int, category: str, new_options: list):
    """Apply an edited category to any live poll for that weekday and warn the
    group so people re-vote."""
    state = app.storage.load_poll_state()
    current_date, current_iso = current_poll_date(app.storage)
    for date, day in state.items():
        if date != current_date or day.get("iso") != current_iso:
            continue
        if day.get("menu_weekday") != weekday:
            continue
        if category not in day.get("categories", {}):
            continue
        original_options = list(day["categories"][category]["options"])
        diff = polls.apply_menu_change(app.storage, date, category, new_options)
        if not diff["live"] or (not diff["removed"] and not diff["added"]):
            continue
        entry = polls.get_day(app.storage, date)["categories"][category]
        try:
            await app.bot.edit_message_reply_markup(
                chat_id=app.chat_id,
                message_id=entry["message_id"],
                reply_markup=polls.poll_keyboard(entry, category, date),
            )
        except TelegramBadRequest:
            pass
        state = app.storage.load_poll_state()
        day = state[date]
        changes = day.setdefault("pending_changes", {})
        changes[category] = {"before": changes.get(category, {}).get("before", original_options),
                             "after": list(new_options)}
        app.storage.save_poll_state(state)


# --- entry points ---------------------------------------------

def pending_notification(app):
    """Return the exact group message for the active poll, or an empty string."""
    date, iso = current_poll_date(app.storage)
    day = app.storage.load_poll_state().get(date, {})
    changes = day.get("pending_changes", {}) if day.get("iso") == iso else {}
    lines = []
    for category, change in changes.items():
        before, after = change["before"], change["after"]
        diff = {"removed": [x for x in before if x not in after],
                "added": [x for x in after if x not in before]}
        if diff["removed"] or diff["added"]:
            lines.append(polls.describe_change(category, date, diff))
    return "\n\n".join(lines)

async def handle_callback(app, cq) -> None:
    data = cq.data
    user_id = cq.from_user.id
    parts = data.split(":")
    action = parts[1] if len(parts) > 1 else ""

    if action == "root":
        app.pending.pop(user_id, None)
        await _show(cq, render_root(app))

    elif action == "close":
        app.pending.pop(user_id, None)
        try:
            await cq.message.delete()
        except TelegramBadRequest:
            pass

    elif action == "preview":
        preview = pending_notification(app)
        await _show(cq, (
            ("👁 Предпросмотр сообщения в группу:\n\n" + preview)
            if preview else "Новых изменений для текущего опроса нет.",
            _kb(([[_btn("📣 Отправить", "adm:notify")]] if preview else [])
                + [[_btn("⬅️ Назад", "adm:root")]]),
        ))

    elif action == "notify":
        date, iso = current_poll_date(app.storage)
        state = app.storage.load_poll_state()
        day = state.get(date, {})
        notification = pending_notification(app)
        if notification:
            await app.bot.send_message(app.chat_id, notification)
            day["pending_changes"] = {}
            app.storage.save_poll_state(state)
        await cq.answer("Изменения отправлены." if notification else "Новых изменений нет.", show_alert=True)
        if cq.message.chat.type == "private":
            await _show(cq, render_root(app))

    elif action == "vote":
        date, iso = current_poll_date(app.storage)
        day = polls.get_day(app.storage, date)
        if not day or day.get("iso") != iso or not day.get("categories"):
            await cq.answer("Сейчас нет активного опроса.", show_alert=True)
        else:
            app.pending[user_id] = {"kind": "manual_name", "date": date, "iso": iso}
            await cq.message.answer("Введите имя человека, за которого добавляете голос.")

    elif action == "vpick":
        draft = app.pending.get(user_id)
        if not draft or draft.get("kind") != "manual_pick":
            await cq.answer("Начните с кнопки «Добавить голос».", show_alert=True)
        else:
            ci, oi = int(parts[2]), int(parts[3])
            category = CATEGORIES[ci]
            entry = polls.get_day(app.storage, draft["date"])["categories"][category]
            draft["picks"][category] = entry["options"][oi]
            await _show(cq, render_manual_vote(app, draft))

    elif action == "vsave":
        draft = app.pending.get(user_id)
        date, iso = current_poll_date(app.storage)
        if not draft or draft.get("kind") != "manual_pick" or (date, iso) != (draft["date"], draft["iso"]):
            await cq.answer("Опрос уже не активен.", show_alert=True)
        elif not draft["picks"]:
            await cq.answer("Выберите хотя бы одно блюдо.", show_alert=True)
        else:
            uid = polls.add_guest_vote(app.storage, date, draft["name"], draft["picks"])
            app.pending.pop(user_id, None)
            day = polls.get_day(app.storage, date)
            for category in draft["picks"]:
                entry = day["categories"][category]
                try:
                    await app.bot.edit_message_reply_markup(chat_id=app.chat_id,
                        message_id=entry["message_id"], reply_markup=polls.poll_keyboard(entry, category, date))
                except TelegramBadRequest:
                    pass
            await _show(cq, render_root(app))
            await cq.answer(f"Голос {draft['name']} добавлен.", show_alert=True)

    elif action == "time":
        app.pending[user_id] = {"kind": "time"}
        prompt = await cq.message.answer(
            "Отправьте время начала опроса в формате ЧЧ:ММ (например 12:00).",
        )
        app.pending[user_id]["prompt_msg_id"] = prompt.message_id

    elif action == "days":
        app.pending.pop(user_id, None)
        await _show(cq, render_days(app))

    elif action == "day":
        await _show(cq, render_day(app, int(parts[2])))

    elif action == "cat":
        weekday, ci = int(parts[2]), int(parts[3])
        category = CATEGORIES[ci]
        current = get_day_menu(app.storage, weekday).get(category, [])
        app.pending[user_id] = {
            "kind": "menu_edit",
            "weekday": weekday,
            "category": category,
            "options": list(current),
        }
        await _show(cq, render_cat_edit(app, app.pending[user_id]))

    elif action == "tog":
        draft = app.pending.get(user_id)
        if not draft or draft.get("kind") != "menu_edit":
            await _show(cq, render_root(app))
            return
        idx = int(parts[2])
        all_dishes = _draft_dishes(app, draft["category"], draft["options"])
        if 0 <= idx < len(all_dishes):
            name = all_dishes[idx]
            if name in draft["options"]:
                draft["options"].remove(name)
            else:
                draft["options"].append(name)
        await _show(cq, render_cat_edit(app, draft))

    elif action == "msave":
        draft = app.pending.pop(user_id, None)
        if not draft or draft.get("kind") != "menu_edit":
            await _show(cq, render_root(app))
            return
        # persist in dish-DB order
        ordered = [
            d for d in _draft_dishes(app, draft["category"], draft["options"])
            if d in draft["options"]
        ]
        menu_config.set_day_category(app.storage, draft["weekday"], draft["category"], ordered)
        await _propagate_menu_change(app, draft["weekday"], draft["category"], ordered)
        await _show(cq, render_day(app, draft["weekday"]))

    elif action == "mcancel":
        draft = app.pending.pop(user_id, None)
        weekday = draft["weekday"] if draft else 0
        await _show(cq, render_day(app, weekday))

    elif action == "dishes":
        app.pending.pop(user_id, None)
        await _show(cq, render_dish_categories(app))

    elif action == "dcat":
        await _show(cq, render_dish_cat(app, int(parts[2])))

    elif action == "ddel":
        ci, idx = int(parts[2]), int(parts[3])
        items = dishes.list_dishes(app.storage, CATEGORIES[ci])
        if 0 <= idx < len(items):
            dishes.remove_dish(app.storage, CATEGORIES[ci], items[idx])
        await _show(cq, render_dish_cat(app, ci))

    elif action == "dadd":
        ci = int(parts[2])
        app.pending[user_id] = {"kind": "dish", "category": CATEGORIES[ci], "ci": ci}
        prompt = await cq.message.answer(
            f"Отправьте название нового блюда для категории «{CATEGORIES[ci]}».",
        )
        app.pending[user_id]["prompt_msg_id"] = prompt.message_id

    elif action == "sync":
        await _show(cq, render_sync_confirm(app))

    elif action == "sync!":
        menu_config.sync_from_schedule(app.storage)
        text, kb = render_root(app)
        await _show(cq, ("✅ Синхронизировано из schedule.json.\n\n" + text, kb))


async def handle_text(app, message) -> bool:
    """Consume a free-text admin prompt. Returns True if it was ours."""
    user_id = message.from_user.id
    pending = app.pending.get(user_id)
    if not pending:
        return False

    async def _cleanup():
        for mid in (pending.get("prompt_msg_id"), message.message_id):
            if mid:
                try:
                    await app.bot.delete_message(message.chat.id, mid)
                except TelegramBadRequest:
                    pass

    kind = pending.get("kind")
    if kind == "manual_name":
        name = (message.text or "").strip()
        if not name:
            await message.answer("Введите непустое имя.")
            return True
        date, iso = current_poll_date(app.storage)
        if (date, iso) != (pending["date"], pending["iso"]):
            app.pending.pop(user_id, None)
            await message.answer("Опрос уже не активен.")
            return True
        app.pending[user_id] = {"kind": "manual_pick", "date": date, "iso": iso,
                                "name": name, "picks": {}}
        text, kb = render_manual_vote(app, app.pending[user_id])
        await message.answer(text, reply_markup=kb)
        return True
    if kind == "time":
        ok = menu_config.set_poll_time(app.storage, message.text or "")
        app.pending.pop(user_id, None)
        await _cleanup()
        note = (
            f"⏰ Время опроса: {get_poll_time_str(app.storage)}"
            if ok else "Не понял время. Нужен формат ЧЧ:ММ, например 12:00."
        )
        text, kb = render_root(app)
        await app.bot.send_message(message.chat.id, note + "\n\n" + text,
                                   reply_markup=kb, parse_mode="Markdown")
        return True

    if kind == "dish":
        ci = pending.get("ci", 0)
        added = dishes.add_dish(app.storage, pending["category"], message.text or "")
        app.pending.pop(user_id, None)
        await _cleanup()
        note = "➕ Добавлено." if added else "Такое блюдо уже есть (или пустое имя)."
        text, kb = render_dish_cat(app, ci)
        await app.bot.send_message(message.chat.id, note + "\n\n" + text,
                                   reply_markup=kb, parse_mode="Markdown")
        return True

    return False
