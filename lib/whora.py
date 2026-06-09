from __future__ import annotations

import json
import os
import re
import secrets
import shlex
import subprocess
import sys
import tempfile
import time
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from shutil import which
from typing import Mapping

SAFE_ID = re.compile(r"^[A-Za-z0-9._-]+$")


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

    def start_stopwatch(self, args: StartArgs) -> tuple[dict[str, object], Path, bool]:
        id = args.id or self.new_id("stopwatch")
        require_id(id)
        path = self.timer_path("stopwatch", id)
        generated = args.id == ""

        if path.exists() and not args.replace:
            raise WhoraError(f"stopwatch already exists: {id} (use --replace or stop it first)")

        now = epoch_now()
        timer: dict[str, object] = {
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


def write_json_atomic(path: Path, data: Mapping[str, object]) -> None:
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


def stopwatch_status(timer: Mapping[str, object], path: Path, generated: bool | None = None) -> dict[str, object]:
    started_epoch = int(timer.get("started_epoch", 0))
    result: dict[str, object] = {
        "kind": "stopwatch",
        "id": str(timer.get("id", "")),
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


def stopwatch_start(store: TimerStore, args: StartArgs) -> int:
    timer, path, generated = store.start_stopwatch(args)
    status = stopwatch_status(timer, path, generated=generated)

    if args.json_output:
        print(json.dumps(status, separators=(",", ":")))
        return 0

    success("✓ Stopwatch started")
    print(f"ID: {timer['id']}")
    if generated:
        print("Generated: yes")
    if args.label:
        print(f"Label: {args.label}")
    if args.tags:
        print(f"Tags: {', '.join(args.tags)}")
    print(f"State: {path}")
    print()
    dim("Next:")
    print(f"  mise run stopwatch:status --id {timer['id']}")
    print(f"  mise run stopwatch:stop --id {timer['id']}")
    return 0


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


def main_error(exc: WhoraError) -> int:
    print(f"time: {exc}", file=sys.stderr)
    return 1
