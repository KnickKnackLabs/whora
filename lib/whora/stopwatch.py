from __future__ import annotations

from pathlib import Path
from typing import Any, Mapping

from .clock import epoch_now, format_duration, iso_now
from .ids import require_id
from .jsonio import write_json_atomic
from .metadata import timer_matches, update_metadata
from .models import StartArgs, StatusArgs, StopArgs, UpdateArgs, WhoraError
from .render import dim, print_json, print_metadata_summary, success, table, tags_inline
from .store import TimerStore


def stopwatch_status_object(timer: Mapping[str, Any], path: Path, generated: bool | None = None) -> dict[str, Any]:
    started_epoch = int(timer.get("started_epoch", 0))
    result: dict[str, Any] = {
        "kind": "stopwatch",
        "id": str(timer.get("id", path.stem)),
        "status": "running",
        "label": str(timer.get("label", "")),
        "tags": list(timer.get("tags", [])),
        "state_path": str(path),
        "started_at": str(timer.get("started_at", "")),
        "started_epoch": started_epoch,
        "elapsed_seconds": max(0, epoch_now() - started_epoch),
        "origin_pwd": str(timer.get("origin_pwd", "")),
    }
    if generated is not None:
        result["generated_id"] = generated
    return result


def stopped_stopwatch_object(timer: Mapping[str, Any]) -> dict[str, Any]:
    now = epoch_now()
    started_epoch = int(timer.get("started_epoch", now))
    return {
        "kind": "stopwatch",
        "id": str(timer.get("id", "")),
        "status": "stopped",
        "label": str(timer.get("label", "")),
        "tags": list(timer.get("tags", [])),
        "started_at": str(timer.get("started_at", "")),
        "started_epoch": started_epoch,
        "stopped_at": iso_now(),
        "stopped_epoch": now,
        "elapsed_seconds": max(0, now - started_epoch),
        "origin_pwd": str(timer.get("origin_pwd", "")),
    }


def stopwatch_start(store: TimerStore, args: StartArgs) -> int:
    id = args.id or store.new_id("stopwatch")
    require_id(id)
    path = store.timer_path("stopwatch", id)
    generated = args.id == ""

    if path.exists() and not args.replace:
        raise WhoraError(f"stopwatch already exists: {id} (use --replace or stop it first)")

    timer: dict[str, Any] = {
        "kind": "stopwatch",
        "id": id,
        "label": args.label,
        "tags": list(args.tags),
        "started_epoch": epoch_now(),
        "started_at": iso_now(),
        "origin_pwd": args.origin_pwd,
    }
    write_json_atomic(path, timer)
    status = stopwatch_status_object(timer, path, generated=generated)

    if args.json_output:
        print_json(status)
        return 0

    success("✓ Stopwatch started")
    print(f"ID: {id}")
    if generated:
        print("Generated: yes")
    if args.label:
        print(f"Label: {args.label}")
    if args.tags:
        print(f"Tags: {tags_inline(args.tags)}")
    print(f"State: {path}")
    print()
    dim("Next:")
    print(f"  mise run stopwatch:status --id {id}")
    print(f"  mise run stopwatch:stop --id {id}")
    return 0


def stopwatch_status(store: TimerStore, args: StatusArgs) -> int:
    if args.id:
        timer, path = store.read_timer("stopwatch", args.id)
        status = stopwatch_status_object(timer, path)
        if args.json_output:
            print_json(status)
        else:
            table(["ID", "STATUS", "ELAPSED", "LABEL", "TAGS"], [stopwatch_row(status)])
        return 0

    items = [
        stopwatch_status_object(timer, path)
        for timer, path in store.list_timers("stopwatch")
        if timer_matches(timer, args.label_filter, args.tags)
    ]
    if args.json_output:
        print_json(items)
    elif items:
        table(["ID", "STATUS", "ELAPSED", "LABEL", "TAGS"], [stopwatch_row(item) for item in items])
    else:
        dim("No stopwatches")
    return 0


def stopwatch_stop(store: TimerStore, args: StopArgs) -> int:
    timer, _ = store.read_timer("stopwatch", args.id)
    stopped = stopped_stopwatch_object(timer)
    store.delete_timer("stopwatch", args.id)

    if args.json_output:
        print_json(stopped)
        return 0

    success("✓ Stopwatch stopped")
    print(f"ID: {args.id}")
    print(f"Elapsed: {format_duration(stopped['elapsed_seconds'])}")
    if stopped["label"]:
        print(f"Label: {stopped['label']}")
    return 0


def stopwatch_update(store: TimerStore, args: UpdateArgs) -> int:
    timer, path = store.read_timer("stopwatch", args.id)
    changed = update_metadata(timer, args, "stopwatch")
    if not changed:
        raise WhoraError(f"nothing to update for stopwatch {args.id}")
    store.write_timer("stopwatch", args.id, timer)
    status = stopwatch_status_object(timer, path)

    if args.json_output:
        print_json(status)
        return 0

    success("✓ Stopwatch updated")
    print_metadata_summary(args.id, timer)
    return 0


def stopwatch_row(status: Mapping[str, Any]) -> list[str]:
    return [
        str(status["id"]),
        str(status["status"]),
        format_duration(status["elapsed_seconds"]),
        str(status.get("label", "")),
        tags_inline(status.get("tags", [])),
    ]
