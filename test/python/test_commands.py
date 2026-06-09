import json
import subprocess
import sys

import pytest
import whora.countdown as countdown_mod
import whora.stopwatch as stopwatch_mod
from whora import (
    CountdownStartArgs,
    StartArgs,
    StatusArgs,
    StopArgs,
    TimerStore,
    UpdateArgs,
    WhoraError,
    countdown_start,
    countdown_status,
    countdown_stop,
    countdown_update,
    stopwatch_start,
    stopwatch_status,
    stopwatch_stop,
    stopwatch_update,
)
from whora.watcher import WATCHER_CODE, pid_alive


def read_json_output(capsys):
    return json.loads(capsys.readouterr().out)


def test_stopwatch_status_lists_with_exact_label_and_tag_filters(tmp_path, capsys):
    store = TimerStore(tmp_path)
    store.write_timer(
        "stopwatch",
        "focus-a",
        {"kind": "stopwatch", "id": "focus-a", "label": "work", "tags": ["a"], "started_epoch": 10},
    )
    store.write_timer(
        "stopwatch",
        "focus-b",
        {"kind": "stopwatch", "id": "focus-b", "label": "other", "tags": ["b"], "started_epoch": 10},
    )

    stopwatch_status(store, StatusArgs(label_filter="work", tags=("a",), json_output=True))

    output = read_json_output(capsys)
    assert [item["id"] for item in output] == ["focus-a"]


def test_stopwatch_stop_reports_elapsed_and_deletes_file(tmp_path, capsys, monkeypatch):
    store = TimerStore(tmp_path)
    store.write_timer(
        "stopwatch",
        "focus",
        {
            "kind": "stopwatch",
            "id": "focus",
            "label": "work",
            "tags": ["a"],
            "started_epoch": 100,
            "started_at": "start",
            "origin_pwd": "/work",
        },
    )
    monkeypatch.setattr(stopwatch_mod, "epoch_now", lambda: 145)
    monkeypatch.setattr(stopwatch_mod, "iso_now", lambda: "stop")

    stopwatch_stop(store, StopArgs(id="focus", json_output=True))

    output = read_json_output(capsys)
    assert output["status"] == "stopped"
    assert output["elapsed_seconds"] == 45
    assert output["stopped_at"] == "stop"
    assert not (tmp_path / "stopwatches" / "focus.json").exists()


def test_stopwatch_update_can_clear_label_and_tags(tmp_path, capsys):
    store = TimerStore(tmp_path)
    store.write_timer(
        "stopwatch",
        "focus",
        {"kind": "stopwatch", "id": "focus", "label": "old", "tags": ["a", "b"], "started_epoch": 10},
    )

    stopwatch_update(store, UpdateArgs(id="focus", clear_label=True, clear_tags=True, json_output=True))

    output = read_json_output(capsys)
    assert output["label"] == ""
    assert output["tags"] == []
    stored, _ = store.read_timer("stopwatch", "focus")
    assert stored["label"] == ""
    assert stored["tags"] == []


def test_stopwatch_update_rejects_noop(tmp_path):
    store = TimerStore(tmp_path)
    stopwatch_start(store, StartArgs(id="focus", json_output=True))

    with pytest.raises(WhoraError, match="nothing to update"):
        stopwatch_update(store, UpdateArgs(id="focus"))


def test_countdown_status_reports_fired_and_overdue(tmp_path, capsys, monkeypatch):
    store = TimerStore(tmp_path)
    store.write_timer(
        "countdown",
        "tea",
        {
            "kind": "countdown",
            "id": "tea",
            "label": "tea",
            "tags": ["kitchen"],
            "duration_seconds": 30,
            "started_epoch": 100,
            "deadline_epoch": 130,
            "notify": False,
            "watcher_pid": None,
            "sleep_pid": None,
        },
    )
    monkeypatch.setattr(countdown_mod, "epoch_now", lambda: 145)

    countdown_status(store, StatusArgs(id="tea", json_output=True))

    output = read_json_output(capsys)
    assert output["status"] == "fired"
    assert output["remaining_seconds"] == 0
    assert output["overdue_seconds"] == 15
    assert output["fired_epoch"] == 130


def test_countdown_stop_reports_remaining_and_deletes_file(tmp_path, capsys, monkeypatch):
    store = TimerStore(tmp_path)
    store.write_timer(
        "countdown",
        "tea",
        {
            "kind": "countdown",
            "id": "tea",
            "label": "tea",
            "tags": [],
            "duration_seconds": 60,
            "started_epoch": 100,
            "deadline_epoch": 160,
            "notify": False,
            "watcher_pid": None,
            "sleep_pid": None,
        },
    )
    monkeypatch.setattr(countdown_mod, "epoch_now", lambda: 120)
    monkeypatch.setattr(countdown_mod, "iso_now", lambda: "stop")

    countdown_stop(store, StopArgs(id="tea", json_output=True))

    output = read_json_output(capsys)
    assert output["status"] == "stopped"
    assert output["elapsed_seconds"] == 20
    assert output["remaining_seconds"] == 40
    assert output["overdue_seconds"] == 0
    assert not (tmp_path / "countdowns" / "tea.json").exists()


def test_countdown_start_replace_overwrites_existing_timer(tmp_path, capsys):
    store = TimerStore(tmp_path)
    countdown_start(store, CountdownStartArgs(duration_seconds=10, id="tea", label="old", json_output=True))
    capsys.readouterr()

    with pytest.raises(WhoraError, match="countdown already exists"):
        countdown_start(store, CountdownStartArgs(duration_seconds=20, id="tea", label="blocked"))

    countdown_start(
        store, CountdownStartArgs(duration_seconds=30, id="tea", label="new", replace=True, json_output=True)
    )

    output = read_json_output(capsys)
    assert output["label"] == "new"
    assert output["duration_seconds"] == 30
    stored, _ = store.read_timer("countdown", "tea")
    assert stored["label"] == "new"
    assert stored["duration_seconds"] == 30


def test_stale_countdown_watcher_cannot_mark_replaced_timer_fired(tmp_path):
    path = tmp_path / "countdowns" / "tea.json"
    path.parent.mkdir(parents=True)
    path.write_text(
        json.dumps(
            {
                "kind": "countdown",
                "id": "tea",
                "label": "new timer",
                "duration_seconds": 30,
                "started_epoch": 100,
                "deadline_epoch": 130,
                "run_token": "new-token",
            }
        ),
        encoding="utf-8",
    )

    result = subprocess.run(
        [sys.executable, "-c", WATCHER_CODE, str(path), "0", "tea", "old-token", "old timer", ""],
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0
    stored = json.loads(path.read_text(encoding="utf-8"))
    assert stored["run_token"] == "new-token"
    assert stored["label"] == "new timer"
    assert "fired_epoch" not in stored


def test_countdown_update_adds_and_removes_tags(tmp_path, capsys):
    store = TimerStore(tmp_path)
    countdown_start(
        store,
        CountdownStartArgs(duration_seconds=10, id="tea", label="tea", tags=("old", "keep"), json_output=True),
    )
    capsys.readouterr()

    countdown_update(
        store,
        UpdateArgs(id="tea", label="new tea", add_tags=("fresh",), remove_tags=("old",), json_output=True),
    )

    output = read_json_output(capsys)
    assert output["label"] == "new tea"
    assert output["tags"] == ["keep", "fresh"]


def test_pid_alive_rejects_empty_and_non_numeric_values():
    assert pid_alive(None) is False
    assert pid_alive("") is False
    assert pid_alive("not-a-pid") is False
    assert pid_alive("-1") is False
