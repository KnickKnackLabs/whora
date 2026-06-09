from __future__ import annotations

import re
import time
from datetime import datetime

from .cli import normalize_empty
from .models import WhoraError


def epoch_now() -> int:
    return int(time.time())


def iso_now() -> str:
    return datetime.now().astimezone().strftime("%Y-%m-%dT%H:%M:%S%z")


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
