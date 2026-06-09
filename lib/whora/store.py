from __future__ import annotations

import json
import secrets
from datetime import datetime
from pathlib import Path
from typing import Any, Mapping

from .ids import require_id
from .jsonio import write_json_atomic
from .models import WhoraError


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

    def exists(self, kind: str, id: str) -> bool:
        return self.timer_path(kind, id).exists()

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
