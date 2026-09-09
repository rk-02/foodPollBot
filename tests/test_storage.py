import json

import pytest

from app.storage import Storage


@pytest.mark.unit
def test_read_missing_returns_default(tmp_path):
    s = Storage(str(tmp_path))
    assert s.load_config() == {}
    assert s.load_dishes() == {}
    assert s.load_history() == {}
    assert s.load_poll_state() == {}
    assert s.load_dm_users() == {}
    assert s.load_schedule() == []


@pytest.mark.unit
def test_write_is_atomic_and_roundtrips(tmp_path):
    s = Storage(str(tmp_path))
    s.save_config({"poll_time": "09:30", "к": "значение"})
    assert s.load_config() == {"poll_time": "09:30", "к": "значение"}
    # written as real UTF-8, not \u escapes
    raw = (tmp_path / "config.json").read_text(encoding="utf-8")
    assert "значение" in raw
    assert not list(tmp_path.glob("*.tmp"))


@pytest.mark.unit
def test_corrupt_file_falls_back_to_default(tmp_path):
    s = Storage(str(tmp_path))
    (tmp_path / "dishes.json").write_text("{ not json", encoding="utf-8")
    assert s.load_dishes() == {}


@pytest.mark.unit
def test_write_failure_cleans_up_temp_file(tmp_path):
    s = Storage(str(tmp_path))
    with pytest.raises(TypeError):
        s.save_config({"bad": object()})          # not JSON-serialisable
    assert not list(tmp_path.glob("*.tmp"))       # temp file removed
    assert not (tmp_path / "config.json").exists()


@pytest.mark.unit
def test_default_base_dir_is_repo_root():
    s = Storage()
    assert s._path("schedule.json").endswith("schedule.json")
    assert json.loads(open(s._path("schedule.json"), encoding="utf-8").read())
