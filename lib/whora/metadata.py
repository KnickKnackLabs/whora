from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from .models import UpdateArgs


def timer_matches(timer: Mapping[str, Any], label_filter: str, tags: Sequence[str]) -> bool:
    if label_filter and timer.get("label", "") != label_filter:
        return False
    timer_tags = {str(tag) for tag in timer.get("tags", [])}
    return all(tag in timer_tags for tag in tags if tag)


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
