from __future__ import annotations

import json
import os
import subprocess
import sys
from shutil import which
from typing import Any, Mapping, Sequence


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


def tags_inline(tags: Sequence[object]) -> str:
    return ", ".join(str(tag) for tag in tags if str(tag))


def print_metadata_summary(id: str, timer: Mapping[str, Any]) -> None:
    print(f"ID: {id}")
    label = str(timer.get("label", ""))
    tags = tags_inline(timer.get("tags", []))
    print(f"Label: {label if label else '—'}")
    print(f"Tags: {tags if tags else '—'}")
