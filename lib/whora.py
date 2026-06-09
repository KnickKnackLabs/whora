from __future__ import annotations

import json
import os
import re
import secrets
import shlex
import signal
import subprocess
import sys
import tempfile
import time
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from shutil import which
from typing import Any, Mapping, Sequence

SAFE_ID = re.compile(r"^[A-Za-z0-9._-]+$")

WATCHER_CODE = r'''
import json
import os
import sys
import tempfile
import time
from pathlib import Path

path = Path(sys.argv[1])
seconds = int(sys.argv[2])
timer_id = sys.argv[3]
label = sys.argv[4]
notify_tty = sys.argv[5]

def write_json_atomic(target, data):
    target.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(prefix=f".{target.name}.", suffix=".tmp", dir=target.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as tmp:
            json.dump(data, tmp, indent=2, sort_keys=True)
            tmp.write("\n")
        os.replace(tmp_name, target)
    except Exception:
        try:
            os.unlink(tmp_name)
        except FileNotFoundError:
            pass
        raise

try:
    time.sleep(seconds)
    if not path.exists():
        raise SystemExit(0)

    with path.open("r", encoding="utf-8") as file:
        timer = json.load(file)
    if timer.get("id") != timer_id:
        raise SystemExit(0)

    timer["fired_epoch"] = int(time.time())
    write_json_atomic(path, timer)

    if notify_tty and os.path.exists(notify_tty) and os.access(notify_tty, os.W_OK):
        with open(notify_tty, "w", encoding="utf-8") as tty:
            tty.write(f"\a\n⏱ countdown done: {timer_id}")
            if label:
                tty.write(f" — {label}")
            tty.write("\n")
except Exception:
    raise SystemExit(0)
'''


class WhoraError(Exception):
    """Expected user-facing command error."""


@dataclass(frozen=True)
class StartArgs:
    id: str = ""
    label: str = ""
    tags: tuple[str, ...] = field(default_factory=tuple)
    replace: bool = False
    json_output: bool = False
    origin_pwd: str = ""


@dataclass(frozen=True)
class CountdownStartArgs:
    duration_seconds: int
    id: str = ""
    label: str = ""
    tags: tuple[str, ...] = field(default_factory=tuple)
    replace: bool = False
    notify: bool = False
    json_output: bool = False
    origin_pwd: str = ""


@dataclass(frozen=True)
class StatusArgs:
    id: str = ""
    label_filter: str = ""
    tags: tuple[str, ...] = field(default_factory=tuple)
    json_output: bool = False


@dataclass(frozen=True)
class StopArgs:
    id: str
    json_output: bool = False


@dataclass(frozen=True)
class UpdateArgs:
    id: str
    label: str = ""
    clear_label: bool = False
    add_tags: tuple[str, ...] = field(default_factory=tuple)
    remove_tags: tuple[str, ...] = field(default_factory=tuple)
    clear_tags: bool = False
    json_output: bool = False


class TimerStore:
    def __init__(self, root: Path):
        self.root = root

    @classmethod
    def from_env(cls, env: Mapping[str, str]) -> "TimerStore":
        if env.get("WHORA_STATE_DIR"):
            return cls(Path(env["WHORA_STATE_DIR"]))
        if env.get("XDG_STATE_HOME"):
            return cls(Path(env["XDG_STATE_HOME"]) / "whora")
        return cls(Path(env.get("HOME", str(Path.home()))) / ".local" / "state" / "whora")

    def kind_dir(self, kind: str) -> Path:
        if kind == "stopwatch":
            return self.root / "stopwatches"
        if kind == "countdown":
            return self.root / "countdowns"
        raise WhoraError(f"unknown timer kind: {kind}")

    def timer_path(self, kind: str, id: str) -> Path:
        require_id(id)
        return self.kind_dir(kind) / f"{id}.json"

    def new_id(self, kind: str) -> str:
        prefix = {"stopwatch": "sw", "countdown": "cd"}.get(kind, "time")
        while True:
            stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
            id = f"{prefix}-{stamp}-{secrets.randbelow(100000)}"
            if not self.timer_path(kind, id).exists():
                return id

    def read_timer(self, kind: str, id: str) -> tuple[dict[str, Any], Path]:
        path = self.timer_path(kind, id)
        if not path.exists():
            raise WhoraError(f"no such {kind}: {id}")
        try:
            with path.open("r", encoding="utf-8") as file:
                timer = json.load(file)
        except json.JSONDecodeError as exc:
            raise WhoraError(f"invalid {kind} state: {path}") from exc
        if not isinstance(timer, dict):
            raise WhoraError(f"invalid {kind} state: {path}")
        timer.setdefault("kind", kind)
        timer.setdefault("id", path.stem)
        timer.setdefault("label", "")
        timer.setdefault("tags", [])
        return timer, path

    def list_timers(self, kind: str) -> list[tuple[dict[str, Any], Path]]:
        kind_dir = self.kind_dir(kind)
        if not kind_dir.exists():
            return []
        timers: list[tuple[dict[str, Any], Path]] = []
        for path in sorted(kind_dir.glob("*.json")):
            timer, _ = self.read_timer(kind, path.stem)
            timers.append((timer, path))
        return timers

    def write_timer(self, kind: str, id: str, timer: Mapping[str, Any]) -> Path:
        path = self.timer_path(kind, id)
        write_json_atomic(path, timer)
        return path

    def delete_timer(self, kind: str, id: str) -> None:
        path = self.timer_path(kind, id)
        try:
            path.unlink()
        except FileNotFoundError:
            pass

    def start_stopwatch(self, args: StartArgs) -> tuple[dict[str, Any], Path, bool]:
        id = args.id or self.new_id("stopwatch")
        require_id(id)
        path = self.timer_path("stopwatch", id)
        generated = args.id == ""

        if path.exists() and not args.replace:
            raise WhoraError(f"stopwatch already exists: {id} (use --replace or stop it first)")

        now = epoch_now()
        timer: dict[str, Any] = {
            "kind": "stopwatch",
            "id": id,
            "label": args.label,
            "tags": list(args.tags),
            "started_epoch": now,
            "started_at": iso_now(),
            "origin_pwd": args.origin_pwd,
        }
        write_json_atomic(path, timer)
        return timer, path, generated

    def start_countdown(self, args: CountdownStartArgs) -> tuple[dict[str, Any], Path, bool]:
        id = args.id or self.new_id("countdown")
        require_id(id)
        path = self.timer_path("countdown", id)
        generated = args.id == ""

        if path.exists():
            if not args.replace:
                raise WhoraError(f"countdown already exists: {id} (use --replace or stop it first)")
            existing, _ = self.read_timer("countdown", id)
            stop_countdown_worker(existing)

        now = epoch_now()
        timer: dict[str, Any] = {
            "kind": "countdown",
            "id": id,
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
            watcher_pid = start_countdown_watcher(path, args.duration_seconds, id, args.label)
            timer["watcher_pid"] = watcher_pid
            write_json_atomic(path, timer)

        return timer, path, generated


def normalize_empty(value: str | None) -> str:
    if value in (None, "", "''"):
        return ""
    return value


def bool_env(value: str | None) -> bool:
    return value == "true"


def usage_words(value: str | None) -> tuple[str, ...]:
    raw = normalize_empty(value)
    if not raw:
        return ()
    return tuple(part for part in shlex.split(raw) if part)


def require_id(id: str) -> None:
    if id == "":
        raise WhoraError("--id cannot be empty")
    if id in (".", ".."):
        raise WhoraError(f"--id cannot be dot or dot-dot: {id}")
    if "/" in id or not SAFE_ID.fullmatch(id):
        raise WhoraError(f"--id may contain only letters, numbers, dot, underscore, and dash: {id}")


def epoch_now() -> int:
    return int(time.time())


def iso_now() -> str:
    return datetime.now().astimezone().strftime("%Y-%m-%dT%H:%M:%S%z")


def write_json_atomic(path: Path, data: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as tmp:
            json.dump(data, tmp, indent=2, sort_keys=True)
            tmp.write("\n")
        os.replace(tmp_name, path)
    except Exception:
        try:
            os.unlink(tmp_name)
        except FileNotFoundError:
            pass
        raise


def start_countdown_watcher(path: Path, seconds: int, id: str, label: str) -> int:
    notify_tty = "/dev/tty" if sys.stderr.isatty() else ""
    process = subprocess.Popen(
        [sys.executable, "-c", WATCHER_CODE, str(path), str(seconds), id, label, notify_tty],
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        close_fds=True,
        start_new_session=True,
    )
    return int(process.pid)


def pid_alive(pid: object) -> bool:
    try:
        value = int(pid)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return False
    if value <= 0:
        return False
    try:
        os.kill(value, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def stop_countdown_worker(timer: Mapping[str, Any]) -> None:
    for field in ("sleep_pid", "watcher_pid"):
        pid = timer.get(field)
        if not pid_alive(pid):
            continue
        try:
            os.kill(int(pid), signal.SIGTERM)  # type: ignore[arg-type]
        except (ProcessLookupError, PermissionError, ValueError, TypeError):
            pass


def format_duration(total: object) -> str:
    try:
        seconds = int(total)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        seconds = 0

    sign = ""
    if seconds < 0:
        sign = "-"
        seconds = -seconds

    hours = seconds // 3600
    minutes = (seconds % 3600) // 60
    secs = seconds % 60

    if hours > 0:
        return f"{sign}{hours}h {minutes}m {secs}s"
    if minutes > 0:
        return f"{sign}{minutes}m {secs}s"
    return f"{sign}{secs}s"


def parse_duration(raw: str) -> int:
    normalized = "".join(normalize_empty(raw).lower().split())
    if not normalized:
        raise WhoraError("duration is required")

    match = re.fullmatch(r"([0-9]+):([0-9][0-9])", normalized)
    if match:
        total = int(match.group(1)) * 60 + int(match.group(2))
        return require_positive_duration(total, raw)

    match = re.fullmatch(r"([0-9]+):([0-9][0-9]):([0-9][0-9])", normalized)
    if match:
        total = int(match.group(1)) * 3600 + int(match.group(2)) * 60 + int(match.group(3))
        return require_positive_duration(total, raw)

    if re.fullmatch(r"[0-9]+", normalized):
        return require_positive_duration(int(normalized), raw)

    rest = normalized
    total = 0
    unit_re = re.compile(r"^([0-9]+)(hours|hour|hrs|hr|h|minutes|minute|mins|min|m|seconds|second|secs|sec|s)(.*)$")
    while rest:
        match = unit_re.match(rest)
        if not match:
            raise WhoraError(f"unsupported duration: {raw} (try 90s, 1m, 1m30s, or 01:30)")
        number = int(match.group(1))
        unit = match.group(2)
        rest = match.group(3)
        if unit in ("hours", "hour", "hrs", "hr", "h"):
            total += number * 3600
        elif unit in ("minutes", "minute", "mins", "min", "m"):
            total += number * 60
        else:
            total += number

    return require_positive_duration(total, raw)


def require_positive_duration(total: int, raw: str) -> int:
    if total <= 0:
        raise WhoraError(f"duration must be greater than zero: {raw}")
    return total


def tags_inline(tags: Sequence[object]) -> str:
    return ", ".join(str(tag) for tag in tags if str(tag))


def timer_matches(timer: Mapping[str, Any], label_filter: str, tags: Sequence[str]) -> bool:
    if label_filter and timer.get("label", "") != label_filter:
        return False
    timer_tags = {str(tag) for tag in timer.get("tags", [])}
    return all(tag in timer_tags for tag in tags if tag)


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


def print_json(data: Any) -> None:
    print(json.dumps(data, separators=(",", ":")))


def success(text: str) -> None:
    style(["--bold", "--foreground", "46"], text)


def dim(text: str) -> None:
    style(["--foreground", "240"], text)


def style(args: list[str], text: str) -> None:
    sys.stdout.flush()
    gum = os.environ.get("GUM", "gum")
    if which(gum):
        completed = subprocess.run([gum, "style", *args, "--", text], check=False)
        if completed.returncode == 0:
            sys.stdout.flush()
            return
    print(text, flush=True)


def table(headers: Sequence[str], rows: Sequence[Sequence[object]]) -> None:
    lines = ["\t".join(headers)]
    lines.extend("\t".join(str(cell) for cell in row) for row in rows)
    data = "\n".join(lines) + "\n"
    gum = os.environ.get("GUM", "gum")
    if which(gum):
        sys.stdout.flush()
        completed = subprocess.run(
            [gum, "table", "--print", "--separator", "\t"],
            input=data,
            text=True,
            check=False,
        )
        if completed.returncode == 0:
            return
    print(data, end="")


def main_error(exc: WhoraError) -> int:
    print(f"time: {exc}", file=sys.stderr)
    return 1


def stopwatch_start(store: TimerStore, args: StartArgs) -> int:
    timer, path, generated = store.start_stopwatch(args)
    status = stopwatch_status_object(timer, path, generated=generated)

    if args.json_output:
        print_json(status)
        return 0

    success("✓ Stopwatch started")
    print(f"ID: {timer['id']}")
    if generated:
        print("Generated: yes")
    if args.label:
        print(f"Label: {args.label}")
    if args.tags:
        print(f"Tags: {tags_inline(args.tags)}")
    print(f"State: {path}")
    print()
    dim("Next:")
    print(f"  mise run stopwatch:status --id {timer['id']}")
    print(f"  mise run stopwatch:stop --id {timer['id']}")
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


def countdown_start(store: TimerStore, args: CountdownStartArgs) -> int:
    timer, path, generated = store.start_countdown(args)
    status = countdown_status_object(timer, path)
    status["generated_id"] = generated

    if args.json_output:
        print_json(status)
        return 0

    success("⏱ Countdown started")
    print(f"ID: {timer['id']}")
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
    print(f"  mise run countdown:status --id {timer['id']}")
    print(f"  mise run countdown:stop --id {timer['id']}")
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
        table(["ID", "STATUS", "REMAINING", "ELAPSED", "LABEL", "TAGS", "NOTE"], [countdown_row(item) for item in items])
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


def update_metadata(timer: dict[str, Any], args: UpdateArgs, kind: str) -> bool:
    changed = False
    if args.clear_label:
        timer["label"] = ""
        changed = True
    elif args.label:
        timer["label"] = args.label
        changed = True

    tags = [str(tag) for tag in timer.get("tags", [])]
    if args.clear_tags:
        tags = []
        changed = True
    if args.remove_tags:
        remove = set(args.remove_tags)
        tags = [tag for tag in tags if tag not in remove]
        changed = True
    if args.add_tags:
        for tag in args.add_tags:
            if tag and tag not in tags:
                tags.append(tag)
        changed = True
    timer["tags"] = tags
    timer.setdefault("kind", kind)
    return changed


def print_metadata_summary(id: str, timer: Mapping[str, Any]) -> None:
    print(f"ID: {id}")
    label = str(timer.get("label", ""))
    tags = tags_inline(timer.get("tags", []))
    print(f"Label: {label if label else '—'}")
    print(f"Tags: {tags if tags else '—'}")
