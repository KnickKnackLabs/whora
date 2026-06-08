#!/usr/bin/env bats

load test_helper

setup() {
  export WHORA_STATE_DIR="$BATS_TEST_TMPDIR/whora-state"
  rm -rf "$WHORA_STATE_DIR"
  mkdir -p "$WHORA_STATE_DIR"
}

teardown() {
  local pid_file pid
  if [ -d "$WHORA_STATE_DIR/countdowns" ]; then
    for pid_file in "$WHORA_STATE_DIR"/countdowns/*/pid "$WHORA_STATE_DIR"/countdowns/*/sleep_pid; do
      [ -f "$pid_file" ] || continue
      if IFS= read -r pid < "$pid_file"; then
        if [ -n "$pid" ]; then
          if kill -0 "$pid" >/dev/null 2>&1; then
            kill "$pid" >/dev/null 2>&1
          fi
        fi
      fi
    done
  fi
  rm -rf "$WHORA_STATE_DIR"
}

json_value() {
  local query="$1"
  printf '%s' "$output" | jq -r "$query"
}

@test "stopwatch start/status/stop lifecycle" {
  run whora stopwatch
  [ "$status" -eq 0 ]
  [[ "$output" == *"No stopwatches"* ]]

  run whora stopwatch:start --id focus --label "familiarization" --tag session=demo
  [ "$status" -eq 0 ]
  [[ "$output" == *"Stopwatch started"* ]]
  [[ "$output" == *"ID: focus"* ]]
  [[ "$output" == *"Label: familiarization"* ]]
  [[ "$output" == *"Tags: session=demo"* ]]

  sleep 1

  run whora stopwatch:status --id focus
  [ "$status" -eq 0 ]
  [[ "$output" == *"focus"* ]]
  [[ "$output" == *"running"* ]]
  [[ "$output" == *"familiarization"* ]]
  [[ "$output" == *"session=demo"* ]]

  run whora stopwatch:stop --id focus
  [ "$status" -eq 0 ]
  [[ "$output" == *"Stopwatch stopped"* ]]
  [[ "$output" == *"ID: focus"* ]]

  run whora stopwatch:status
  [ "$status" -eq 0 ]
  [[ "$output" == *"No stopwatches"* ]]
}

@test "countdown start/status/fire/stop lifecycle" {
  run whora countdown
  [ "$status" -eq 0 ]
  [[ "$output" == *"No countdowns"* ]]

  run whora countdown:start 2s --id tea --label "check tea" --quiet
  [ "$status" -eq 0 ]
  [[ "$output" == *"Countdown started"* ]]
  [[ "$output" == *"ID: tea"* ]]
  [[ "$output" == *"Duration: 2s"* ]]

  run whora countdown:status --id tea
  [ "$status" -eq 0 ]
  [[ "$output" == *"tea"* ]]
  [[ "$output" == *"running"* ]]
  [[ "$output" == *"check tea"* ]]

  sleep 3

  run whora countdown:status --id tea
  [ "$status" -eq 0 ]
  [[ "$output" == *"tea"* ]]
  [[ "$output" == *"fired"* ]]

  run whora countdown:stop --id tea
  [ "$status" -eq 0 ]
  [[ "$output" == *"Countdown stopped"* ]]
  [[ "$output" == *"ID: tea"* ]]

  run whora countdown:status
  [ "$status" -eq 0 ]
  [[ "$output" == *"No countdowns"* ]]
}

@test "omitted start ids are generated instead of using a magic default" {
  run whora stopwatch:start --json --label "generated stopwatch"
  [ "$status" -eq 0 ]
  stopwatch_id="$(json_value '.id')"
  [ -n "$stopwatch_id" ]
  [ "$stopwatch_id" != "default" ]
  [ "$(json_value '.generated_id')" = "true" ]

  run whora stopwatch:stop --id "$stopwatch_id" --json
  [ "$status" -eq 0 ]
  [ "$(json_value '.id')" = "$stopwatch_id" ]

  run whora countdown:start 30s --json --quiet
  [ "$status" -eq 0 ]
  countdown_id="$(json_value '.id')"
  [ -n "$countdown_id" ]
  [ "$countdown_id" != "default" ]
  [ "$(json_value '.generated_id')" = "true" ]

  run whora countdown:stop --id "$countdown_id" --json
  [ "$status" -eq 0 ]
  [ "$(json_value '.id')" = "$countdown_id" ]
}

@test "stopwatch commands support json output" {
  run whora stopwatch:start --id json-sw --label "json label" --tag issue=9 --json
  [ "$status" -eq 0 ]
  [ "$(json_value '.kind')" = "stopwatch" ]
  [ "$(json_value '.id')" = "json-sw" ]
  [ "$(json_value '.status')" = "running" ]
  [ "$(json_value '.label')" = "json label" ]
  [ "$(json_value '.tags[0]')" = "issue=9" ]

  run whora stopwatch --json
  [ "$status" -eq 0 ]
  [ "$(json_value 'length')" = "1" ]
  [ "$(json_value '.[0].id')" = "json-sw" ]

  run whora stopwatch:status --id json-sw --json
  [ "$status" -eq 0 ]
  [ "$(json_value '.id')" = "json-sw" ]
  [ "$(json_value '.status')" = "running" ]

  run whora stopwatch:stop --id json-sw --json
  [ "$status" -eq 0 ]
  [ "$(json_value '.status')" = "stopped" ]
  [ "$(json_value '.elapsed_seconds | type')" = "number" ]
}

@test "countdown commands support json output" {
  run whora countdown:start 20s --id json-cd --label "json countdown" --tag project=min --quiet --json
  [ "$status" -eq 0 ]
  [ "$(json_value '.kind')" = "countdown" ]
  [ "$(json_value '.id')" = "json-cd" ]
  [ "$(json_value '.status')" = "running" ]
  [ "$(json_value '.duration_seconds')" = "20" ]
  [ "$(json_value '.notify')" = "false" ]
  [ "$(json_value '.tags[0]')" = "project=min" ]

  run whora countdown --json
  [ "$status" -eq 0 ]
  [ "$(json_value 'length')" = "1" ]
  [ "$(json_value '.[0].id')" = "json-cd" ]

  run whora countdown:status --id json-cd --json
  [ "$status" -eq 0 ]
  [ "$(json_value '.id')" = "json-cd" ]
  [ "$(json_value '.status')" = "running" ]
  [ "$(json_value '.remaining_seconds | type')" = "number" ]

  run whora countdown:stop --id json-cd --json
  [ "$status" -eq 0 ]
  [ "$(json_value '.status')" = "stopped" ]
  [ "$(json_value '.remaining_seconds | type')" = "number" ]
}

@test "status supports label and tag filters" {
  whora stopwatch:start --id focus-a --label "min thing" --tag project=min
  whora stopwatch:start --id focus-b --label "other" --tag project=other

  run whora stopwatch:status --label "min thing" --json
  [ "$status" -eq 0 ]
  [ "$(json_value 'length')" = "1" ]
  [ "$(json_value '.[0].id')" = "focus-a" ]

  run whora stopwatch --tag project=other --json
  [ "$status" -eq 0 ]
  [ "$(json_value 'length')" = "1" ]
  [ "$(json_value '.[0].id')" = "focus-b" ]
}

@test "stopwatch metadata can be edited after creation" {
  whora stopwatch:start --id meta-sw --label "old" --tag a --tag b

  run whora stopwatch:update --id meta-sw --label "new" --remove-tag a --tag c --json
  [ "$status" -eq 0 ]
  [ "$(json_value '.label')" = "new" ]
  [ "$(json_value '.tags | join(",")')" = "b,c" ]

  run whora stopwatch:update --id meta-sw --clear-label --clear-tags --json
  [ "$status" -eq 0 ]
  [ "$(json_value '.label')" = "" ]
  [ "$(json_value '.tags | length')" = "0" ]
}

@test "countdown metadata can be edited after creation" {
  whora countdown:start 20s --id meta-cd --label "old" --tag a --tag b --quiet

  run whora countdown:update --id meta-cd --label "new" --remove-tag b --tag c --json
  [ "$status" -eq 0 ]
  [ "$(json_value '.label')" = "new" ]
  [ "$(json_value '.tags | join(",")')" = "a,c" ]

  run whora countdown:update --id meta-cd --clear-label --clear-tags --json
  [ "$status" -eq 0 ]
  [ "$(json_value '.label')" = "" ]
  [ "$(json_value '.tags | length')" = "0" ]
}

@test "update requires an actual metadata change" {
  whora stopwatch:start --id no-op

  run whora stopwatch:update --id no-op
  [ "$status" -ne 0 ]
  [[ "$output" == *"nothing to update"* ]]
}

@test "countdown accepts human-ish duration shapes" {
  run whora countdown:start "1 minute" --id words --quiet
  [ "$status" -eq 0 ]
  [[ "$output" == *"Countdown started"* ]]
  [[ "$output" == *"Duration: 1m 0s"* ]]

  run whora countdown:stop --id words
  [ "$status" -eq 0 ]

  run whora countdown:start 01:30 --id colon --quiet
  [ "$status" -eq 0 ]
  [[ "$output" == *"Countdown started"* ]]
  [[ "$output" == *"Duration: 1m 30s"* ]]
}

@test "notify is opt-in and creates a watcher only when requested" {
  run whora countdown:start 20s --id silent --json
  [ "$status" -eq 0 ]
  [ "$(json_value '.notify')" = "false" ]
  [ "$(json_value '.watcher_pid')" = "null" ]

  run whora countdown:stop --id silent --json
  [ "$status" -eq 0 ]

  run whora countdown:start 20s --id loud --notify --json
  [ "$status" -eq 0 ]
  [ "$(json_value '.notify')" = "true" ]
  [ "$(json_value '.watcher_alive')" = "true" ]

  run whora countdown:stop --id loud --json
  [ "$status" -eq 0 ]
}

@test "ids reject path-like characters" {
  run whora stopwatch:start --id ../bad
  [ "$status" -ne 0 ]
  [[ "$output" == *"--id may contain only"* ]]
}
