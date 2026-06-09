from __future__ import annotations

import re

from .models import WhoraError

SAFE_ID = re.compile(r"^[A-Za-z0-9._-]+$")


def require_id(id: str) -> None:
    if id == "":
        raise WhoraError("--id cannot be empty")
    if id in (".", ".."):
        raise WhoraError(f"--id cannot be dot or dot-dot: {id}")
    if "/" in id or not SAFE_ID.fullmatch(id):
        raise WhoraError(f"--id may contain only letters, numbers, dot, underscore, and dash: {id}")
