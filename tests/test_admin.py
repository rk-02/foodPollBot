import pytest

from app import admin, menu_config, polls
from app.dishes import list_dishes

pytestmark = pytest.mark.integration


async def _cb(app, make_cq, data, user_id=5):
    cq = make_cq(data, chat_id=user_id, chat_type="private", user_id=user_id)
    await admin.handle_callback(app, cq)
    return cq


@pytest.mark.asyncio
async def test_root_and_close(app, make_cq):
    cq = await _cb(app, make_cq, "adm:root")
    text = cq.message.edit_text.await_args.args[0]
    assert "Админ-панель" in text and "Время опроса" in text

    cq2 = await _cb(app, make_cq, "adm:close")
    cq2.message.delete.assert_awaited_once()


@pytest.mark.asyncio
async def test_set_poll_time_via_text_prompt(app, make_cq, make_message):
    await _cb(app, make_cq, "adm:time", user_id=5)
    assert app.pending[5]["kind"] == "time"

    msg = make_message(text="07:30", chat_type="private", chat_id=5, user_id=5)
    handled = await admin.handle_text(app, msg)

    assert handled is True
    assert 5 not in app.pending
    assert menu_config.get_poll_time_str(app.storage) == "07:30"
    note = app.bot.send_message.await_args.args[1]
    assert "07:30" in note


@pytest.mark.asyncio
async def test_set_poll_time_rejects_bad_input(app, make_cq, make_message):
    await _cb(app, make_cq, "adm:time", user_id=5)
    msg = make_message(text="полдень", chat_type="private", chat_id=5, user_id=5)
    await admin.handle_text(app, msg)
    assert "ЧЧ:ММ" in app.bot.send_message.await_args.args[1]
    assert menu_config.get_poll_time_str(app.storage) == menu_config.DEFAULT_POLL_TIME


@pytest.mark.asyncio
async def test_handle_text_ignores_when_no_pending(app, make_message):
    msg = make_message(text="что-то", chat_type="private", chat_id=5, user_id=5)
    assert await admin.handle_text(app, msg) is False


@pytest.mark.asyncio
async def test_menu_edit_navigation_and_toggle(app, make_cq):
    await _cb(app, make_cq, "adm:days")
    await _cb(app, make_cq, "adm:day:1")
    await _cb(app, make_cq, "adm:cat:1:2")  # ci=2 -> "Гарниры"

    draft = app.pending[5]
    assert draft["kind"] == "menu_edit"
    assert draft["category"] == "Гарниры"
    before = list(draft["options"])

    all_dishes = admin._draft_dishes(app, "Гарниры", draft["options"])
    first = all_dishes[0]
    await _cb(app, make_cq, "adm:tog:0")
    after = app.pending[5]["options"]
    assert (first in after) != (first in before)  # toggled


@pytest.mark.asyncio
async def test_menu_edit_save_persists_and_warns_group(app, make_cq):
    # active menu + a matching live poll for weekday 1
    menu_config.set_day_category(app.storage, 1, "Вторые блюда", ["Гуляш", "Тефтели"])
    polls.start_day(app.storage, "10.09", "2026-09-10", 1)
    polls.register_poll(app.storage, "10.09", "Вторые блюда", 900, ["Гуляш", "Тефтели"])
    polls.toggle_vote(app.storage, "10.09", 1, 1, 42)  # someone voted Тефтели

    await _cb(app, make_cq, "adm:cat:1:1")
    app.pending[5]["options"] = ["Гуляш"]              # drop Тефтели
    await _cb(app, make_cq, "adm:msave")

    assert menu_config.get_day_menu(app.storage, 1)["Вторые блюда"] == ["Гуляш"]
    entry = polls.get_day(app.storage, "10.09")["categories"]["Вторые блюда"]
    assert entry["options"] == ["Гуляш"]
    assert entry["votes"] == {}                        # Тефтели vote dropped

    warn = [c for c in app.bot.send_message.await_args_list
            if c.args and c.args[0] == app.chat_id]
    assert warn and "Изменения в меню" in warn[0].args[1]
    app.bot.edit_message_reply_markup.assert_awaited()


@pytest.mark.asyncio
async def test_menu_edit_save_without_live_poll_is_silent(app, make_cq):
    await _cb(app, make_cq, "adm:cat:0:0")
    app.pending[5]["options"] = ["Куриный"]
    await _cb(app, make_cq, "adm:msave")
    assert menu_config.get_day_menu(app.storage, 0)["Первые блюда"] == ["Куриный"]
    # no group warning
    assert not [c for c in app.bot.send_message.await_args_list
               if c.args and c.args[0] == app.chat_id]


@pytest.mark.asyncio
async def test_menu_edit_cancel_drops_draft(app, make_cq):
    await _cb(app, make_cq, "adm:cat:2:0")
    assert 5 in app.pending
    await _cb(app, make_cq, "adm:mcancel")
    assert 5 not in app.pending


@pytest.mark.asyncio
async def test_toggle_without_draft_returns_root(app, make_cq):
    cq = await _cb(app, make_cq, "adm:tog:0")
    assert "Админ-панель" in cq.message.edit_text.await_args.args[0]


@pytest.mark.asyncio
async def test_dish_db_add_and_delete(app, make_cq, make_message):
    await _cb(app, make_cq, "adm:dishes")
    await _cb(app, make_cq, "adm:dcat:2")  # Гарниры

    await _cb(app, make_cq, "adm:dadd:2", user_id=5)
    assert app.pending[5]["kind"] == "dish"
    msg = make_message(text="Булгур", chat_type="private", chat_id=5, user_id=5)
    assert await admin.handle_text(app, msg) is True
    assert "Булгур" in list_dishes(app.storage, "Гарниры")

    items = list_dishes(app.storage, "Гарниры")
    idx = items.index("Булгур")
    await _cb(app, make_cq, f"adm:ddel:2:{idx}")
    assert "Булгур" not in list_dishes(app.storage, "Гарниры")


@pytest.mark.asyncio
async def test_dish_add_duplicate_reports(app, make_cq, make_message):
    await _cb(app, make_cq, "adm:dadd:0", user_id=5)
    msg = make_message(text="Щи", chat_type="private", chat_id=5, user_id=5)
    await admin.handle_text(app, msg)
    assert "уже есть" in app.bot.send_message.await_args.args[1]


@pytest.mark.asyncio
async def test_menu_edit_save_no_op_change_is_silent(app, make_cq):
    """Live poll for the edited weekday+category, but the option list is
    unchanged -> no group warning."""
    menu_config.set_day_category(app.storage, 1, "Гарниры", ["Рис", "Гречка"])
    polls.start_day(app.storage, "10.09", "2026-09-10", 1)
    polls.register_poll(app.storage, "10.09", "Гарниры", 900, ["Рис", "Гречка"])

    await _cb(app, make_cq, "adm:cat:1:2")            # draft == current
    await _cb(app, make_cq, "adm:msave")

    assert not [c for c in app.bot.send_message.await_args_list
               if c.args and c.args[0] == app.chat_id]


@pytest.mark.asyncio
async def test_menu_edit_save_other_weekday_poll_untouched(app, make_cq):
    """A live poll exists, but for a different weekday than the one edited."""
    polls.start_day(app.storage, "10.09", "2026-09-10", 3)
    polls.register_poll(app.storage, "10.09", "Гарниры", 900, ["Рис"])

    await _cb(app, make_cq, "adm:cat:1:2")
    app.pending[5]["options"] = ["Гречка"]
    await _cb(app, make_cq, "adm:msave")

    assert polls.get_day(app.storage, "10.09")["categories"]["Гарниры"]["options"] == ["Рис"]
    assert not [c for c in app.bot.send_message.await_args_list
               if c.args and c.args[0] == app.chat_id]


@pytest.mark.asyncio
async def test_menu_edit_save_other_category_poll_untouched(app, make_cq):
    """Live poll for the right weekday but a different category."""
    polls.start_day(app.storage, "10.09", "2026-09-10", 1)
    polls.register_poll(app.storage, "10.09", "Гарниры", 900, ["Рис"])

    await _cb(app, make_cq, "adm:cat:1:0")            # Первые блюда
    app.pending[5]["options"] = ["Куриный"]
    await _cb(app, make_cq, "adm:msave")

    assert not [c for c in app.bot.send_message.await_args_list
               if c.args and c.args[0] == app.chat_id]


@pytest.mark.asyncio
async def test_sync_from_schedule_button(app, make_cq):
    menu_config.set_day_category(app.storage, 0, "Первые блюда", ["Выдумка"])
    await _cb(app, make_cq, "adm:sync")
    cq = await _cb(app, make_cq, "adm:sync!")
    assert "Синхронизировано" in cq.message.edit_text.await_args.args[0]
    assert "Выдумка" not in menu_config.get_day_menu(app.storage, 0)["Первые блюда"]
