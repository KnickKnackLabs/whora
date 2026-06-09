import json
from pathlib import Path

import pytest
from whora import TimerStore, WhoraError, bool_env, normalize_empty, usage_words
from whora.jsonio import write_json_atomic


def test_timer_store_from_env_prefers_whora_state_dir(tmp_path):
    store = TimerStore.from_env(
        {
            "WHORA_STATE_DIR": str(tmp_path / "explicit"),
            "XDG_STATE_HOME": str(tmp_path / "xdg"),
            "HOME": str(tmp_path / "home"),
        }
    )

    assert store.root == tmp_path / "explicit"


def test_timer_store_from_env_uses_xdg_state_home_when_present(tmp_path):
    store = TimerStore.from_env({"XDG_STATE_HOME": str(tmp_path / "xdg"), "HOME": str(tmp_path / "home")})

    assert store.root == tmp_path / "xdg" / "whora"


def test_timer_store_from_env_falls_back_to_home(tmp_path):
    store = TimerStore.from_env({"HOME": str(tmp_path / "home")})

    assert store.root == tmp_path / "home" / ".local" / "state" / "whora"


def test_timer_store_write_read_list_delete_round_trip(tmp_path):
    store = TimerStore(tmp_path)
    timer = {"kind": "stopwatch", "id": "focus", "label": "work", "tags": ["a"]}

    path = store.write_timer("stopwatch", "focus", timer)

    assert path == tmp_path / "stopwatches" / "focus.json"
    assert store.exists("stopwatch", "focus") is True
    read, read_path = store.read_timer("stopwatch", "focus")
    assert read == timer
    assert read_path == path
    assert store.list_timers("stopwatch") == [(timer, path)]

    store.delete_timer("stopwatch", "focus")

    assert store.exists("stopwatch", "focus") is False
    with pytest.raises(WhoraError, match="no such stopwatch"):
        store.read_timer("stopwatch", "focus")


def test_timer_store_read_rejects_invalid_json(tmp_path):
    path = tmp_path / "stopwatches" / "broken.json"
    path.parent.mkdir(parents=True)
    path.write_text("not json", encoding="utf-8")

    with pytest.raises(WhoraError, match="invalid stopwatch state"):
        TimerStore(tmp_path).read_timer("stopwatch", "broken")


def test_write_json_atomic_replaces_existing_file(tmp_path):
    path = tmp_path / "state" / "timer.json"
    write_json_atomic(path, {"id": "first"})
    write_json_atomic(path, {"id": "second", "tags": ["a"]})

    assert json.loads(path.read_text(encoding="utf-8")) == {"id": "second", "tags": ["a"]}
    assert list(path.parent.glob("*.tmp")) == []


def test_usage_words_parses_mise_shell_escaped_values():
    assert usage_words("'repo=whora' 'label with spaces' ''") == ("repo=whora", "label with spaces")


def test_normalize_empty_and_bool_env_helpers():
    assert normalize_empty(None) == ""
    assert normalize_empty("") == ""
    assert normalize_empty("''") == ""
    assert normalize_empty("value") == "value"
    assert bool_env("true") is True
    assert bool_env("false") is False
    assert bool_env(None) is False


def test_timer_path_rejects_unsafe_ids(tmp_path):
    with pytest.raises(WhoraError, match="may contain only"):
        TimerStore(tmp_path).timer_path("stopwatch", "../bad")


def test_kind_dir_rejects_unknown_kind(tmp_path):
    with pytest.raises(WhoraError, match="unknown timer kind"):
        TimerStore(tmp_path).kind_dir("hourglass")


def test_new_id_uses_kind_prefix_and_json_file_shape(tmp_path):
    store = TimerStore(tmp_path)

    stopwatch_id = store.new_id("stopwatch")
    countdown_id = store.new_id("countdown")

    assert stopwatch_id.startswith("sw-")
    assert countdown_id.startswith("cd-")
    assert Path(store.timer_path("stopwatch", stopwatch_id)).suffix == ".json"
