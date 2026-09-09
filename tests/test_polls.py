import pytest

from app import polls


@pytest.mark.unit
def test_start_day_and_register(storage):
    polls.start_day(storage, "10.09", "2026-09-10", 2)
    entry = polls.register_poll(storage, "10.09", "Гарниры", 55, ["Рис", " Гречка "])
    assert entry["message_id"] == 55
    assert entry["options"] == ["Рис", "Гречка"]
    day = polls.get_day(storage, "10.09")
    assert day["menu_weekday"] == 2
    assert day["iso"] == "2026-09-10"


@pytest.mark.unit
def test_start_day_wipes_previous_votes(storage):
    polls.start_day(storage, "10.09", "2026-09-10", 2)
    polls.register_poll(storage, "10.09", "Гарниры", 1, ["Рис", "Гречка"])
    polls.toggle_vote(storage, "10.09", 2, 0, 999)
    polls.start_day(storage, "10.09", "2026-09-11", 3)
    assert polls.get_day(storage, "10.09")["categories"] == {}


@pytest.mark.unit
def test_toggle_vote_add_switch_remove(storage):
    polls.start_day(storage, "10.09", "2026-09-10", 2)
    polls.register_poll(storage, "10.09", "Гарниры", 1, ["Рис", "Гречка"])

    action, entry = polls.toggle_vote(storage, "10.09", 2, 0, 7)
    assert action == "added"
    assert entry["votes"] == {"Рис": [7]}

    action, entry = polls.toggle_vote(storage, "10.09", 2, 1, 7)
    assert action == "switched"
    assert entry["votes"] == {"Гречка": [7]}          # single-select

    action, entry = polls.toggle_vote(storage, "10.09", 2, 1, 7)
    assert action == "removed"
    assert entry["votes"] == {}


@pytest.mark.unit
def test_toggle_vote_invalid_targets(storage):
    assert polls.toggle_vote(storage, "01.01", 0, 0, 1) == (None, None)
    polls.start_day(storage, "10.09", "2026-09-10", 2)
    polls.register_poll(storage, "10.09", "Гарниры", 1, ["Рис"])
    assert polls.toggle_vote(storage, "10.09", 9, 0, 1) == (None, None)
    action, _ = polls.toggle_vote(storage, "10.09", 2, 5, 1)
    assert action is None


@pytest.mark.unit
def test_two_users_independent(storage):
    polls.start_day(storage, "10.09", "2026-09-10", 2)
    polls.register_poll(storage, "10.09", "Гарниры", 1, ["Рис", "Гречка"])
    polls.toggle_vote(storage, "10.09", 2, 0, 1)
    polls.toggle_vote(storage, "10.09", 2, 1, 2)
    entry = polls.get_day(storage, "10.09")["categories"]["Гарниры"]
    assert entry["votes"] == {"Рис": [1], "Гречка": [2]}


@pytest.mark.unit
def test_set_vote_used_by_usual(storage):
    polls.start_day(storage, "10.09", "2026-09-10", 2)
    polls.register_poll(storage, "10.09", "Гарниры", 1, ["Рис", "Гречка"])
    assert polls.set_vote(storage, "10.09", "Гарниры", "Рис", 7) is True
    assert polls.set_vote(storage, "10.09", "Гарниры", "Рис", 7) is False  # already
    assert polls.set_vote(storage, "10.09", "Гарниры", "Отсутствует", 7) is False
    assert polls.set_vote(storage, "10.09", "Супы", "Рис", 7) is False


@pytest.mark.unit
def test_apply_menu_change_replace_keeps_surviving_votes(storage):
    polls.start_day(storage, "10.09", "2026-09-10", 2)
    polls.register_poll(storage, "10.09", "Вторые блюда", 1, ["Гуляш", "Тефтели"])
    polls.toggle_vote(storage, "10.09", 1, 0, 100)   # Гуляш
    polls.toggle_vote(storage, "10.09", 1, 1, 200)   # Тефтели

    diff = polls.apply_menu_change(storage, "10.09", "Вторые блюда", ["Гуляш", "Плов"])
    assert diff == {"live": True, "removed": ["Тефтели"], "added": ["Плов"]}
    entry = polls.get_day(storage, "10.09")["categories"]["Вторые блюда"]
    assert entry["options"] == ["Гуляш", "Плов"]
    assert entry["votes"] == {"Гуляш": [100]}         # Тефтели vote dropped

    text = polls.describe_change("Вторые блюда", "10.09", diff)
    assert "заменено" in text and "Тефтели" in text and "Плов" in text
    assert "переголосуйте" in text


@pytest.mark.unit
def test_apply_menu_change_not_live(storage):
    diff = polls.apply_menu_change(storage, "31.12", "Салаты", ["Оливье"])
    assert diff == {"live": False, "removed": [], "added": []}
    assert polls.describe_change("Салаты", "31.12", diff) == ""


@pytest.mark.unit
def test_describe_change_multi_add_remove(storage):
    diff = {"live": True, "removed": ["A", "B"], "added": ["C"]}
    text = polls.describe_change("Гарниры", "10.09", diff)
    assert "удалено: «A»" in text
    assert "удалено: «B»" in text
    assert "добавлено: «C»" in text


@pytest.mark.unit
def test_results_text_merges_second_side_drops_soup(storage):
    polls.start_day(storage, "10.09", "2026-09-10", 2)
    polls.register_poll(storage, "10.09", "Первые блюда", 1, ["Куриный", "Щи"])
    polls.register_poll(storage, "10.09", "Вторые блюда", 2, ["Гуляш", "Тефтели"])
    polls.register_poll(storage, "10.09", "Гарниры", 3, ["Рис", "Гречка"])
    polls.register_poll(storage, "10.09", "Салаты", 4, ["Зимний", "Обжорка"])
    # Иван: суп Куриный, второе Гуляш, гарнир Гречка, салат Зимний
    polls.toggle_vote(storage, "10.09", 0, 0, 1)
    polls.toggle_vote(storage, "10.09", 1, 0, 1)
    polls.toggle_vote(storage, "10.09", 2, 1, 1)
    polls.toggle_vote(storage, "10.09", 3, 0, 1)
    polls.remember_name(storage, "10.09", 1, "Иван")
    # Пётр: второе Гуляш, гарнир Рис
    polls.toggle_vote(storage, "10.09", 1, 0, 2)
    polls.toggle_vote(storage, "10.09", 2, 0, 2)
    polls.remember_name(storage, "10.09", 2, "Пётр")

    text = polls.results_text(storage, "10.09")
    assert "🗓 10.09" in text
    # merged second + side tally
    assert "🍽 Вторые блюда + гарниры:" in text
    assert "Гуляш + Гречка: 1" in text
    assert "Гуляш + Рис: 1" in text
    # no soup, no standalone second/side sections
    assert "Куриный" not in text
    assert "Первые блюда" not in text
    assert "🍚 Гарниры:" not in text
    # salads kept
    assert "🥗 Салаты:" in text and "Зимний: 1" in text
    # per-person, soup excluded
    assert "Иван — Гуляш + Гречка + Зимний" in text
    assert "Пётр — Гуляш + Рис" in text


@pytest.mark.unit
def test_results_text_side_only_vote_still_shows(storage):
    polls.start_day(storage, "10.09", "2026-09-10", 2)
    polls.register_poll(storage, "10.09", "Гарниры", 1, ["Рис", "Гречка"])
    polls.toggle_vote(storage, "10.09", 2, 0, 7)
    text = polls.results_text(storage, "10.09")
    assert "🍽 Вторые блюда + гарниры:" in text
    assert "Рис: 1" in text


@pytest.mark.unit
def test_results_text_no_data_and_no_votes(storage):
    assert "нет опросов" in polls.results_text(storage, "01.02").lower()
    polls.start_day(storage, "10.09", "2026-09-10", 2)
    polls.register_poll(storage, "10.09", "Гарниры", 1, ["Рис"])
    assert "Нет голосов" in polls.results_text(storage, "10.09")
    # a soup-only vote is not enough for the grouped result
    polls.register_poll(storage, "10.09", "Первые блюда", 2, ["Куриный"])
    polls.toggle_vote(storage, "10.09", 0, 0, 5)
    assert "Нет голосов" in polls.results_text(storage, "10.09")


@pytest.mark.unit
def test_poll_keyboard_marks_choice_and_counts(storage):
    polls.start_day(storage, "10.09", "2026-09-10", 2)
    entry = polls.register_poll(storage, "10.09", "Гарниры", 1, ["Рис", "Гречка"])
    polls.toggle_vote(storage, "10.09", 2, 0, 7)
    entry = polls.get_day(storage, "10.09")["categories"]["Гарниры"]

    kb = polls.poll_keyboard(entry, "Гарниры", "10.09", user_id=7)
    labels = [b.text for row in kb.inline_keyboard for b in row]
    assert labels[0].startswith(polls.VOTE_MARK)
    assert "· 1" in labels[0]
    data = [b.callback_data for row in kb.inline_keyboard for b in row]
    assert data == ["poll:10.09:2:0", "poll:10.09:2:1"]

    kb_anon = polls.poll_keyboard(entry, "Гарниры", "10.09")
    assert not any(b.text.startswith(polls.VOTE_MARK)
                   for row in kb_anon.inline_keyboard for b in row)


@pytest.mark.unit
def test_remember_name_noop_without_day(storage):
    polls.remember_name(storage, "01.01", 1, "Ghost")   # no crash
    polls.set_action_menu_message(storage, "01.01", 5)  # no crash
