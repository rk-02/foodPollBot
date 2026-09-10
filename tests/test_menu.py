import pytest

from app import menu


@pytest.mark.unit
def test_group_menu_has_results_usual_and_write_to_bot():
    kb = menu.action_menu_markup(private=False, bot_username="foodpoll_bot", show_usual=True)
    rows = kb.inline_keyboard
    texts = [b.text for row in rows for b in row]
    assert any("Обновить результаты" in t for t in texts)
    assert any("как обычно" in t.lower() for t in texts)
    write_btn = [b for row in rows for b in row if "Написать боту" in b.text][0]
    assert write_btn.url == "https://t.me/foodpoll_bot?start=dm"


@pytest.mark.unit
def test_group_menu_hides_usual_until_ready():
    kb = menu.action_menu_markup(private=False, bot_username="foodpoll_bot", show_usual=False)
    texts = [b.text for row in kb.inline_keyboard for b in row]
    assert not any("как обычно" in t.lower() for t in texts)
    assert any("Обновить результаты" in t for t in texts)


@pytest.mark.unit
def test_group_menu_without_username_hides_write_button():
    kb = menu.action_menu_markup(private=False, bot_username=None)
    texts = [b.text for row in kb.inline_keyboard for b in row]
    assert not any("Написать боту" in t for t in texts)


@pytest.mark.integration
@pytest.mark.asyncio
async def test_send_action_menu_hides_usual_when_not_ready(app):
    await menu.send_action_menu(app, 555, private=False)
    kb = app.bot.send_message.await_args.kwargs["reply_markup"]
    texts = [b.text for row in kb.inline_keyboard for b in row]
    assert not any("как обычно" in t.lower() for t in texts)


@pytest.mark.integration
@pytest.mark.asyncio
async def test_send_action_menu_shows_usual_when_ready(app, usual_ready):
    await menu.send_action_menu(app, 555, private=False)
    kb = app.bot.send_message.await_args.kwargs["reply_markup"]
    texts = [b.text for row in kb.inline_keyboard for b in row]
    assert any("как обычно" in t.lower() for t in texts)


@pytest.mark.unit
def test_private_menu_has_admin_and_no_write_button():
    kb = menu.action_menu_markup(private=True, bot_username="foodpoll_bot")
    texts = [b.text for row in kb.inline_keyboard for b in row]
    datas = [b.callback_data for row in kb.inline_keyboard for b in row]
    assert any("Админ-панель" in t for t in texts)
    assert "adm:root" in datas
    assert not any("Написать боту" in t for t in texts)


@pytest.mark.integration
@pytest.mark.asyncio
async def test_send_action_menu_uses_bot(app):
    await menu.send_action_menu(app, 555, private=False)
    app.bot.send_message.assert_awaited_once()
    args, kwargs = app.bot.send_message.await_args
    assert args[0] == 555
    assert kwargs["reply_markup"] is not None
