from __future__ import annotations

import secrets
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from .clock import epoch_now, format_duration, iso_now
from .ids import require_id
from .jsonio import write_json_atomic
from .metadata import timer_matches, update_metadata
from .models import CountdownStartArgs, StatusArgs, StopArgs, UpdateArgs, WhoraError
from .render import dim, print_json, print_metadata_summary, success, table, tags_inline
from .store import TimerStore
from .watcher import pid_alive, start_countdown_watcher, stop_countdown_worker


def countdown_status_object(timer: Mapping[str, Any], path: Path) -> dict[str, Any]:
    now = epoch_now()
    started_epoch = int(timer.get("started_epoch", timer.get("deadline_epoch", now)))
    deadline_epoch = int(timer.get("deadline_epoch", started_epoch))
    duration = int(timer.get("duration_seconds", deadline_epoch - started_epoch))
    elapsed = max(0, now - started_epoch)
    remaining = deadline_epoch - now
    overdue = 0
    status = "running"
    fired_epoch = timer.get("fired_epoch")

    if remaining <= 0:
        status = "fired"
        overdue = 0 - remaining
        remaining = 0
        if fired_epoch in (None, ""):
            fired_epoch = deadline_epoch

    watcher_pid = timer.get("watcher_pid")
    sleep_pid = timer.get("sleep_pid")

    return {
        "kind": "countdown",
        "id": str(timer.get("id", path.stem)),
        "status": status,
        "label": str(timer.get("label", "")),
        "tags": list(timer.get("tags", [])),
        "state_path": str(path),
        "started_at": str(timer.get("started_at", "")),
        "started_epoch": started_epoch,
        "deadline_epoch": deadline_epoch,
        "duration_seconds": duration,
        "elapsed_seconds": elapsed,
        "remaining_seconds": remaining,
        "overdue_seconds": overdue,
        "notify": bool(timer.get("notify", False)),
        "watcher_pid": int(watcher_pid) if pid_alive(watcher_pid) or watcher_pid else None,
        "sleep_pid": int(sleep_pid) if pid_alive(sleep_pid) or sleep_pid else None,
        "watcher_alive": pid_alive(watcher_pid),
        "fired_epoch": int(fired_epoch) if fired_epoch not in (None, "") else None,
        "origin_pwd": str(timer.get("origin_pwd", "")),
    }


def stopped_countdown_object(timer: Mapping[str, Any]) -> dict[str, Any]:
    now = epoch_now()
    started_epoch = int(timer.get("started_epoch", now))
    deadline_epoch = int(timer.get("deadline_epoch", started_epoch))
    duration = int(timer.get("duration_seconds", deadline_epoch - started_epoch))
    remaining = deadline_epoch - now
    overdue = 0
    if remaining <= 0:
        overdue = 0 - remaining
        remaining = 0
    return {
        "kind": "countdown",
        "id": str(timer.get("id", "")),
        "status": "stopped",
        "label": str(timer.get("label", "")),
        "tags": list(timer.get("tags", [])),
        "started_at": str(timer.get("started_at", "")),
        "started_epoch": started_epoch,
        "stopped_at": iso_now(),
        "stopped_epoch": now,
        "deadline_epoch": deadline_epoch,
        "duration_seconds": duration,
        "elapsed_seconds": max(0, now - started_epoch),
        "remaining_seconds": max(0, remaining),
        "overdue_seconds": overdue,
        "origin_pwd": str(timer.get("origin_pwd", "")),
    }


def countdown_start(store: TimerStore, args: CountdownStartArgs) -> int:
    id = args.id or store.new_id("countdown")
    require_id(id)
    path = store.timer_path("countdown", id)
    generated = args.id == ""

    if path.exists():
        if not args.replace:
            raise WhoraError(f"countdown already exists: {id} (use --replace or stop it first)")
        existing, _ = store.read_timer("countdown", id)
        stop_countdown_worker(existing)

    now = epoch_now()
    timer: dict[str, Any] = {
        "schema_version": 1,
        "kind": "countdown",
        "id": id,
        "run_token": secrets.token_hex(16),
        "label": args.label,
        "tags": list(args.tags),
        "duration_seconds": args.duration_seconds,
        "started_epoch": now,
        "deadline_epoch": now + args.duration_seconds,
        "started_at": iso_now(),
        "notify": args.notify,
        "watcher_pid": None,
        "sleep_pid": None,
        "origin_pwd": args.origin_pwd,
    }
    write_json_atomic(path, timer)

    if args.notify:
        timer["watcher_pid"] = start_countdown_watcher(
            path, args.duration_seconds, id, str(timer["run_token"]), args.label
        )
        write_json_atomic(path, timer)

    status = countdown_status_object(timer, path)
    status["generated_id"] = generated

    if args.json_output:
        print_json(status)
        return 0

    success("⏱ Countdown started")
    print(f"ID: {id}")
    print(f"Duration: {format_duration(args.duration_seconds)}")
    print(f"Notify: {str(args.notify).lower()}")
    if generated:
        print("Generated: yes")
    if args.label:
        print(f"Label: {args.label}")
    if args.tags:
        print(f"Tags: {tags_inline(args.tags)}")
    print(f"State: {path}")
    print()
    dim("Next:")
    print(f"  mise run countdown:status --id {id}")
    print(f"  mise run countdown:stop --id {id}")
    if not args.notify:
        dim("Tip: pass --notify if you want a terminal bell/message when it fires.")
    return 0


def countdown_status(store: TimerStore, args: StatusArgs) -> int:
    if args.id:
        timer, path = store.read_timer("countdown", args.id)
        status = countdown_status_object(timer, path)
        if args.json_output:
            print_json(status)
        else:
            table(["ID", "STATUS", "REMAINING", "ELAPSED", "LABEL", "TAGS", "NOTE"], [countdown_row(status)])
        return 0

    items = [
        countdown_status_object(timer, path)
        for timer, path in store.list_timers("countdown")
        if timer_matches(timer, args.label_filter, args.tags)
    ]
    if args.json_output:
        print_json(items)
    elif items:
        headers = ["ID", "STATUS", "REMAINING", "ELAPSED", "LABEL", "TAGS", "NOTE"]
        table(headers, [countdown_row(item) for item in items])
    else:
        dim("No countdowns")
    return 0


def countdown_stop(store: TimerStore, args: StopArgs) -> int:
    timer, _ = store.read_timer("countdown", args.id)
    stop_countdown_worker(timer)
    stopped = stopped_countdown_object(timer)
    store.delete_timer("countdown", args.id)

    if args.json_output:
        print_json(stopped)
        return 0

    success("✓ Countdown stopped")
    print(f"ID: {args.id}")
    print(f"Elapsed: {format_duration(stopped['elapsed_seconds'])}")
    if stopped["remaining_seconds"] > 0:
        print(f"Remaining: {format_duration(stopped['remaining_seconds'])}")
    else:
        print(f"Overdue: {format_duration(stopped['overdue_seconds'])}")
    if stopped["label"]:
        print(f"Label: {stopped['label']}")
    return 0


def countdown_update(store: TimerStore, args: UpdateArgs) -> int:
    timer, path = store.read_timer("countdown", args.id)
    changed = update_metadata(timer, args, "countdown")
    if not changed:
        raise WhoraError(f"nothing to update for countdown {args.id}")
    store.write_timer("countdown", args.id, timer)
    status = countdown_status_object(timer, path)

    if args.json_output:
        print_json(status)
        return 0

    success("✓ Countdown updated")
    print_metadata_summary(args.id, timer)
    return 0


def countdown_row(status: Mapping[str, Any]) -> list[str]:
    note = ""
    if status.get("status") == "running" and status.get("notify") and not status.get("watcher_alive"):
        note = "notifier stale"
    remaining = format_duration(status["remaining_seconds"])
    if status.get("status") == "fired":
        remaining = f"overdue {format_duration(status['overdue_seconds'])}"
    return [
        str(status["id"]),
        str(status["status"]),
        remaining,
        format_duration(status["elapsed_seconds"]),
        str(status.get("label", "")),
        tags_inline(status.get("tags", [])),
        note,
    ]
