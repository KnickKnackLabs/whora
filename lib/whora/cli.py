from __future__ import annotations

import shlex
import sys

from .models import WhoraError


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


def main_error(exc: WhoraError) -> int:
    print(f"time: {exc}", file=sys.stderr)
    return 1
