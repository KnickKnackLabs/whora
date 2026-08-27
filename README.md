<div align="center">

# whora

**Stopwatches and countdowns for shell-shaped work.**

Ask what hour it is, then make the work answer.

![shape: mise + Python](https://img.shields.io/badge/shape-mise%20%2B%20Python-3776AB?style=flat&logo=python&logoColor=white)
[![tests: 68](https://img.shields.io/badge/tests-68-brightgreen?style=flat)](test/)
[![BATS: 23](https://img.shields.io/badge/BATS-23-brightgreen?style=flat)](test/)
[![pytest: 45](https://img.shields.io/badge/pytest-45-brightgreen?style=flat)](test/python/)
![lints: 17](https://img.shields.io/badge/lints-17-blue?style=flat)
![README: TSX](https://img.shields.io/badge/README-TSX-f472b6?style=flat)
[![License: MIT](https://img.shields.io/badge/License-MIT-blue?style=flat)](LICENSE)

</div>

<br />

## What this is

`whora` is a tiny shell-time tool: named stopwatches, named countdowns, editable labels and tags, JSON output for scripts, and gum-styled dashboards for humans.

It separates two common needs that agents blur together: a **stopwatch** counts elapsed time, while a **countdown** has a duration and can become fired/overdue. Countdown notifications are opt-in, so ordinary countdowns do not leave long-running sleeper processes behind.

## Quick start

```bash
# Inside this repo while developing:
mise run stopwatch:start --label "PR review" --tag repo=notes
mise run stopwatch
mise run stopwatch:stop --id <id>

mise run countdown:start 10m --id ci-check --label "check CI" --tag pr=123
mise run countdown
mise run countdown:update --id ci-check --tag session=iris
mise run countdown:stop --id ci-check
```

When installed as a shiv package, the same task names are intended to be available through `whora`, for example `whora countdown:start 5m --label "tea"`.

## Behavior

- **No magic default timers.** Starting without `--id` generates an id; stopping requires an explicit id.
- **Metadata stays editable.** Use `update` tasks to set/clear labels and add/remove tags.
- **Silent countdowns by default.** A countdown is considered fired when its deadline passes. Pass `--notify` only when you want a terminal bell/message.
- **Human and machine surfaces are separate.** Default output uses gum where helpful; `--json` stays plain.
- **State is local and simple.** Whora stores one JSON file per timer under `${WHORA_STATE_DIR}`, then `${XDG_STATE_HOME}/whora`, then `~/.local/state/whora`.

## Examples

```bash
# Stopwatch with generated id.
mise run stopwatch:start --label "familiarization" --json
mise run stopwatch --label "familiarization"

# Countdown with a stable id so repeated starts replace the same semantic timer.
mise run countdown:start 1m --id min-check --replace --label "check min"
mise run countdown:status --id min-check --json

# Opt into a terminal notification.
mise run countdown:start 5m --id tea --label "check tea" --notify

# Edit metadata later.
mise run stopwatch:update --id <id> --label "PR review" --tag repo=notes
mise run countdown:update --id min-check --remove-tag session=old --tag session=new
```

## Validation

```bash
mise run test
codebase lint "$PWD"
mise exec -- readme build --check
git diff --check
```

The current suite has **68 tests** (**23 BATS** + **45 pytest**). `mise run test` runs BATS, Python unit tests, and ruff lint/format checks. The repo also has **17 convention lints** configured.

<div align="center">

---

<sub>
This README was generated from `README.tsx` with [KnickKnackLabs/readme](https://github.com/KnickKnackLabs/readme).
</sub></div>
