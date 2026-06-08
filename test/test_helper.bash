#!/usr/bin/env bash
# Shared fixtures for whora tests.

# Run a repo task through mise so tests exercise the real task path.
whora() {
  cd "$REPO_DIR" && mise run -q "$@"
}
export -f whora
