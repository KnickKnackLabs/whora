import json

import pytest
from whora import (
    CountdownStartArgs,
    StartArgs,
    TimerStore,
    UpdateArgs,
    WhoraError,
    countdown_start,
    parse_duration,
    require_id,
    stopwatch_start,
)
from whora.metadata import update_metadata


@pytest.mark.parametrize(
    ("raw", "seconds"),
    [
        ("90", 90),
        ("90s", 90),
        ("1m30s", 90),
        ("1 minute", 60),
        ("01:30", 90),
        ("1:02:03", 3723),
    ],
)
def test_parse_duration_accepts_supported_shapes(raw, seconds):
    assert parse_duration(raw) == seconds


@pytest.mark.parametrize("raw", ["", "0", "nope", "1x"])
def test_parse_duration_rejects_invalid_shapes(raw):
    with pytest.raises(WhoraError):
        parse_duration(raw)


@pytest.mark.parametrize("id", ["focus", "focus.1", "focus_1", "focus-1"])
def test_require_id_accepts_safe_ids(id):
    require_id(id)


@pytest.mark.parametrize("id", ["", ".", "..", "../bad", "bad/slash", "bad space"])
def test_require_id_rejects_path_like_or_unsafe_ids(id):
    with pytest.raises(WhoraError):
        require_id(id)


def test_stopwatch_start_writes_one_json_file(tmp_path, capsys):
    store = TimerStore(tmp_path)

    status = stopwatch_start(
        store,
        StartArgs(id="focus", label="deep work", tags=("repo=whora",), json_output=True, origin_pwd="/work"),
    )

    assert status == 0
    output = json.loads(capsys.readouterr().out)
    assert output["id"] == "focus"
    assert output["state_path"].endswith("/stopwatches/focus.json")
    assert (tmp_path / "stopwatches" / "focus.json").is_file()
    assert not (tmp_path / "stopwatches" / "focus").exists()

    stored = json.loads((tmp_path / "stopwatches" / "focus.json").read_text())
    assert stored["label"] == "deep work"
    assert stored["tags"] == ["repo=whora"]


def test_countdown_start_is_silent_without_notify(tmp_path, capsys):
    store = TimerStore(tmp_path)

    status = countdown_start(
        store,
        CountdownStartArgs(duration_seconds=30, id="tea", label="tea", json_output=True, origin_pwd="/work"),
    )

    assert status == 0
    output = json.loads(capsys.readouterr().out)
    assert output["notify"] is False
    assert output["watcher_pid"] is None
    assert output["sleep_pid"] is None
    assert output["watcher_alive"] is False

    stored = json.loads((tmp_path / "countdowns" / "tea.json").read_text())
    assert stored["notify"] is False
    assert stored["watcher_pid"] is None
    assert stored["sleep_pid"] is None


def test_update_metadata_edits_label_and_tags():
    timer = {"kind": "stopwatch", "id": "focus", "label": "old", "tags": ["a", "b"]}

    changed = update_metadata(
        timer,
        UpdateArgs(id="focus", label="new", add_tags=("c",), remove_tags=("a",)),
        "stopwatch",
    )

    assert changed is True
    assert timer["label"] == "new"
    assert timer["tags"] == ["b", "c"]
