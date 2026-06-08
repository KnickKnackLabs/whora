# Contributing

`whora` is a small KnickKnackLabs Bash/mise tool for stopwatches and countdowns.

## Local setup

```bash
gh repo clone KnickKnackLabs/whora
cd whora
mise trust
mise install
mise run test
mise run doctor
```

## Development notes

- Public behavior lives in file tasks under `.mise/tasks/`.
- Shared Bash helpers live in `lib/time.sh`.
- Tests call tasks through `mise run` via `test/test_helper.bash`; do not call task scripts directly.
- Human-facing output should use gum when it improves scanability; JSON output should stay plain.
- Countdown notification is opt-in. Avoid introducing long-running background processes for silent countdowns.

## Validation

```bash
mise run test
codebase lint "$PWD"
mise exec -- readme build --check
git diff --check
```
