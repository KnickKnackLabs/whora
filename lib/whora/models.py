from __future__ import annotations

from dataclasses import dataclass, field


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
