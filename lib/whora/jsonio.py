from __future__ import annotations

import json
import os
import tempfile
from collections.abc import Mapping
from contextlib import suppress
from pathlib import Path
from typing import Any


def write_json_atomic(path: Path, data: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as tmp:
            json.dump(data, tmp, indent=2, sort_keys=True)
            tmp.write("\n")
        os.replace(tmp_name, path)
    except Exception:
        with suppress(FileNotFoundError):
            os.unlink(tmp_name)
        raise
