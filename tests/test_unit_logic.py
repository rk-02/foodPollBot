import pytest


@pytest.mark.unit
def test_escape_markdown_escapes_special_chars(telegram_bot):
    text = "_*[]()~`>#+-=|{}.!"
    escaped = telegram_bot.escape_markdown(text)
    assert escaped == "\\_\\*\\[\\]\\(\\)\\~\\`\\>\\#\\+\\-\\=\\|\\{\\}\\.\\!"


@pytest.mark.unit
@pytest.mark.asyncio
async def test_get_joint_results_returns_no_votes_when_set_dish_empty(telegram_bot, computed_date):
    telegram_bot.polls_dict[computed_date] = {
        "Первые блюда": {"options": ["Суп"], "votes": [0]},
        "Салаты": {"options": ["Салат"], "votes": [0]},
        "set_dish": {},
    }
    result = await telegram_bot.get_joint_results()
    assert "Нет голосов" in result


@pytest.mark.unit
@pytest.mark.asyncio
async def test_get_joint_results_renders_combos(telegram_bot, computed_date):
    telegram_bot.polls_dict[computed_date] = {
        "Первые блюда": {"options": ["Суп"], "votes": [1]},
        "Салаты": {"options": ["Салат"], "votes": [1]},
        "set_dish": {1: {"Вторые блюда": ["Котлета"], "Гарниры": ["Рис"]}},
    }
    result = await telegram_bot.get_joint_results()
    assert "Котлета" in result
    assert "Рис" in result
    assert "Первые блюда" in result


@pytest.mark.unit
@pytest.mark.asyncio
async def test_get_joint_results_handles_cancelled_votes_without_crash(telegram_bot, computed_date):
    telegram_bot.polls_dict[computed_date] = {
        "set_dish": {
            1: {"Вторые блюда": [], "Гарниры": ["Рис"]},
            2: {"Вторые блюда": ["Котлета"], "Гарниры": []},
        }
    }
    result = await telegram_bot.get_joint_results()
    assert "Рис" in result
    assert "Котлета" in result
