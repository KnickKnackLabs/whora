from __future__ import annotations

import os
import signal
import subprocess
import sys
from pathlib import Path
from typing import Any, Mapping

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
