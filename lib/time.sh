#!/usr/bin/env bash

set -euo pipefail

time_state_home() {
  if [ -n "${WHORA_STATE_DIR:-}" ]; then
    printf '%s\n' "$WHORA_STATE_DIR"
    return 0
  fi

  if [ -n "${XDG_STATE_HOME:-}" ]; then
    printf '%s/whora\n' "$XDG_STATE_HOME"
    return 0
  fi

  printf '%s/.local/state/whora\n' "$HOME"
}

time_kind_dir() {
  local kind root
  kind="$1"
  root="$(time_state_home)"

  case "$kind" in
    stopwatch) printf '%s/stopwatches\n' "$root" ;;
    countdown) printf '%s/countdowns\n' "$root" ;;
    *)
      printf 'time: unknown state kind: %s\n' "$kind" >&2
      return 1
      ;;
  esac
}

time_item_dir() {
  local kind id
  kind="$1"
  id="$2"
  printf '%s/%s\n' "$(time_kind_dir "$kind")" "$id"
}

time_normalize_empty() {
  case "${1:-}" in
    ""|"''") printf '\n' ;;
    *) printf '%s\n' "$1" ;;
  esac
}

time_require_id() {
  local id
  id="$1"

  case "$id" in
    "")
      printf 'time: --id cannot be empty\n' >&2
      return 1
      ;;
    "."|"..")
      printf 'time: --id cannot be dot or dot-dot: %s\n' "$id" >&2
      return 1
      ;;
    *[!A-Za-z0-9._-]*)
      printf 'time: --id may contain only letters, numbers, dot, underscore, and dash: %s\n' "$id" >&2
      return 1
      ;;
  esac
}

time_epoch_now() {
  date '+%s'
}

time_iso_now() {
  date '+%Y-%m-%dT%H:%M:%S%z'
}

time_new_id() {
  local kind prefix stamp id dir
  kind="$1"
  case "$kind" in
    stopwatch) prefix="sw" ;;
    countdown) prefix="cd" ;;
    *) prefix="time" ;;
  esac

  while :; do
    stamp="$(date '+%Y%m%d-%H%M%S')"
    id="${prefix}-${stamp}-${RANDOM}"
    dir="$(time_item_dir "$kind" "$id")"
    [ -e "$dir" ] || break
  done

  printf '%s\n' "$id"
}

time_write_field() {
  local dir field value
  dir="$1"
  field="$2"
  value="$3"
  printf '%s\n' "$value" > "$dir/$field"
}

time_read_field() {
  local dir field file value
  dir="$1"
  field="$2"
  file="$dir/$field"
  value=""

  [ -f "$file" ] || return 1
  if IFS= read -r value < "$file"; then
    :
  else
    value=""
  fi
  printf '%s\n' "$value"
}

time_pid_alive() {
  local pid
  pid="${1:-}"
  case "$pid" in
    ""|*[!0-9]*) return 1 ;;
  esac
  kill -0 "$pid" >/dev/null 2>&1
}

time_usage_words() {
  local input word
  input="$(time_normalize_empty "${1:-}")"
  [ -n "$input" ] || return 0

  while IFS= read -r word; do
    [ -n "$word" ] || continue
    printf '%s\n' "$word"
  done < <(printf '%s' "$input" | xargs printf '%s\n')
}

time_write_tags() {
  local dir tag
  dir="$1"
  shift

  : > "$dir/tags"
  for tag in "$@"; do
    tag="$(time_normalize_empty "$tag")"
    [ -n "$tag" ] || continue
    printf '%s\n' "$tag" >> "$dir/tags"
  done

  [ -s "$dir/tags" ] || rm -f "$dir/tags"
}

time_add_tags() {
  local dir tmp tag
  dir="$1"
  shift
  tmp="$(mktemp)"

  if [ -s "$dir/tags" ]; then
    cp "$dir/tags" "$tmp"
  fi

  for tag in "$@"; do
    tag="$(time_normalize_empty "$tag")"
    [ -n "$tag" ] || continue
    if ! grep -Fx -- "$tag" "$tmp" >/dev/null 2>&1; then
      printf '%s\n' "$tag" >> "$tmp"
    fi
  done

  if [ -s "$tmp" ]; then
    mv "$tmp" "$dir/tags"
  else
    rm -f "$tmp" "$dir/tags"
  fi
}

time_remove_tags() {
  local dir tmp existing remove tag
  dir="$1"
  shift

  [ -s "$dir/tags" ] || return 0
  tmp="$(mktemp)"

  while IFS= read -r existing; do
    remove=false
    for tag in "$@"; do
      [ "$existing" = "$tag" ] && remove=true
    done
    if ! $remove; then
      printf '%s\n' "$existing" >> "$tmp"
    fi
  done < "$dir/tags"

  if [ -s "$tmp" ]; then
    mv "$tmp" "$dir/tags"
  else
    rm -f "$tmp" "$dir/tags"
  fi
}

time_tags_inline() {
  local dir tags_file
  dir="$1"
  tags_file="$dir/tags"

  [ -s "$tags_file" ] || return 0
  awk 'NF { if (out != "") out = out ", " $0; else out = $0 } END { print out }' "$tags_file"
}

time_tags_match_all() {
  local dir tag tags_file
  dir="$1"
  shift
  tags_file="$dir/tags"

  for tag in "$@"; do
    [ -n "$tag" ] || continue
    [ -s "$tags_file" ] || return 1
    grep -Fx -- "$tag" "$tags_file" >/dev/null 2>&1 || return 1
  done

  return 0
}

time_item_matches() {
  local dir label_filter label
  dir="$1"
  label_filter="$2"
  shift 2

  if [ -n "$label_filter" ]; then
    if ! label="$(time_read_field "$dir" label)"; then
      label=""
    fi
    [ "$label" = "$label_filter" ] || return 1
  fi

  time_tags_match_all "$dir" "$@"
}

time_style() {
  local gum
  gum="${GUM:-gum}"
  if command -v "$gum" >/dev/null 2>&1; then
    "$gum" style "$@"
  else
    shift $(( $# > 0 ? $# - 1 : 0 ))
    printf '%s\n' "${1:-}"
  fi
}

time_heading() {
  time_style --bold --foreground 212 -- "$1"
}

time_success() {
  time_style --bold --foreground 46 -- "$1"
}

time_dim() {
  time_style --foreground 240 -- "$1"
}

time_table() {
  local gum
  gum="${GUM:-gum}"
  if command -v "$gum" >/dev/null 2>&1; then
    "$gum" table --print --separator $'\t'
  else
    cat
  fi
}

time_tags_json() {
  local dir tags_file
  dir="$1"
  tags_file="$dir/tags"

  if [ -s "$tags_file" ]; then
    jq -R . "$tags_file" | jq -s .
  else
    printf '[]\n'
  fi
}

time_json_list() {
  if [ -t 0 ]; then
    printf '[]\n'
  else
    jq -s .
  fi
}

time_format_duration() {
  local total sign hours minutes seconds
  total="${1:-0}"
  sign=""

  case "$total" in
    ""|*[!0-9-]*) total=0 ;;
  esac

  if [ "$total" -lt 0 ]; then
    sign="-"
    total=$((0 - total))
  fi

  hours=$((total / 3600))
  minutes=$(((total % 3600) / 60))
  seconds=$((total % 60))

  if [ "$hours" -gt 0 ]; then
    printf '%s%dh %dm %ds\n' "$sign" "$hours" "$minutes" "$seconds"
  elif [ "$minutes" -gt 0 ]; then
    printf '%s%dm %ds\n' "$sign" "$minutes" "$seconds"
  else
    printf '%s%ds\n' "$sign" "$seconds"
  fi
}

time_parse_duration() {
  local raw normalized rest total number unit seconds minutes hours
  raw="$(time_normalize_empty "${1:-}")"
  normalized="$(printf '%s' "$raw" | tr '[:upper:]' '[:lower:]' | tr -d '[:space:]')"

  if [ -z "$normalized" ]; then
    printf 'time: duration is required\n' >&2
    return 1
  fi

  if [[ "$normalized" =~ ^([0-9]+):([0-9][0-9])$ ]]; then
    minutes="${BASH_REMATCH[1]}"
    seconds="${BASH_REMATCH[2]}"
    total=$((minutes * 60 + seconds))
  elif [[ "$normalized" =~ ^([0-9]+):([0-9][0-9]):([0-9][0-9])$ ]]; then
    hours="${BASH_REMATCH[1]}"
    minutes="${BASH_REMATCH[2]}"
    seconds="${BASH_REMATCH[3]}"
    total=$((hours * 3600 + minutes * 60 + seconds))
  elif [[ "$normalized" =~ ^[0-9]+$ ]]; then
    total="$normalized"
  else
    rest="$normalized"
    total=0
    while [[ "$rest" =~ ^([0-9]+)(hours|hour|hrs|hr|h|minutes|minute|mins|min|m|seconds|second|secs|sec|s)(.*)$ ]]; do
      number="${BASH_REMATCH[1]}"
      unit="${BASH_REMATCH[2]}"
      rest="${BASH_REMATCH[3]}"
      case "$unit" in
        hours|hour|hrs|hr|h) total=$((total + number * 3600)) ;;
        minutes|minute|mins|min|m) total=$((total + number * 60)) ;;
        seconds|second|secs|sec|s) total=$((total + number)) ;;
      esac
    done

    if [ -n "$rest" ] || [ "$total" -eq 0 ]; then
      printf 'time: unsupported duration: %s (try 90s, 1m, 1m30s, or 01:30)\n' "$raw" >&2
      return 1
    fi
  fi

  if [ "$total" -le 0 ]; then
    printf 'time: duration must be greater than zero: %s\n' "$raw" >&2
    return 1
  fi

  printf '%s\n' "$total"
}

time_stopwatch_json() {
  local dir id label started_epoch started_at origin_pwd now elapsed tags_json
  dir="$1"

  if ! id="$(time_read_field "$dir" id)"; then
    id="$(basename "$dir")"
  fi
  if ! label="$(time_read_field "$dir" label)"; then
    label=""
  fi
  if ! started_epoch="$(time_read_field "$dir" started_epoch)"; then
    started_epoch=0
  fi
  if ! started_at="$(time_read_field "$dir" started_at)"; then
    started_at=""
  fi
  if ! origin_pwd="$(time_read_field "$dir" origin_pwd)"; then
    origin_pwd=""
  fi

  now="$(time_epoch_now)"
  elapsed=$((now - started_epoch))
  tags_json="$(time_tags_json "$dir")"

  jq -nc \
    --arg kind "stopwatch" \
    --arg id "$id" \
    --arg status "running" \
    --arg label "$label" \
    --arg state_dir "$dir" \
    --arg started_at "$started_at" \
    --arg origin_pwd "$origin_pwd" \
    --argjson started_epoch "$started_epoch" \
    --argjson elapsed_seconds "$elapsed" \
    --argjson tags "$tags_json" \
    '{kind:$kind,id:$id,status:$status,label:$label,tags:$tags,state_dir:$state_dir,started_at:$started_at,started_epoch:$started_epoch,elapsed_seconds:$elapsed_seconds,origin_pwd:$origin_pwd}'
}

time_countdown_json() {
  local dir id label started_epoch deadline_epoch started_at origin_pwd duration pid sleep_pid fired_epoch notify now elapsed remaining overdue status watcher_alive tags_json
  dir="$1"

  if ! id="$(time_read_field "$dir" id)"; then
    id="$(basename "$dir")"
  fi
  if ! label="$(time_read_field "$dir" label)"; then
    label=""
  fi
  if ! started_epoch="$(time_read_field "$dir" started_epoch)"; then
    started_epoch=0
  fi
  if ! deadline_epoch="$(time_read_field "$dir" deadline_epoch)"; then
    deadline_epoch=0
  fi
  if ! duration="$(time_read_field "$dir" duration_seconds)"; then
    duration=$((deadline_epoch - started_epoch))
  fi
  if ! started_at="$(time_read_field "$dir" started_at)"; then
    started_at=""
  fi
  if ! origin_pwd="$(time_read_field "$dir" origin_pwd)"; then
    origin_pwd=""
  fi
  if ! pid="$(time_read_field "$dir" pid)"; then
    pid=""
  fi
  if ! sleep_pid="$(time_read_field "$dir" sleep_pid)"; then
    sleep_pid=""
  fi
  if ! fired_epoch="$(time_read_field "$dir" fired_epoch)"; then
    fired_epoch=""
  fi
  if ! notify="$(time_read_field "$dir" notify)"; then
    notify="false"
  fi

  now="$(time_epoch_now)"
  elapsed=$((now - started_epoch))
  remaining=$((deadline_epoch - now))
  overdue=0
  status="running"
  if [ "$remaining" -le 0 ]; then
    status="fired"
    overdue=$((0 - remaining))
    remaining=0
    if [ -z "$fired_epoch" ]; then
      fired_epoch="$deadline_epoch"
    fi
  fi
  watcher_alive=false
  if time_pid_alive "$pid"; then
    watcher_alive=true
  fi
  tags_json="$(time_tags_json "$dir")"

  jq -nc \
    --arg kind "countdown" \
    --arg id "$id" \
    --arg status "$status" \
    --arg label "$label" \
    --arg state_dir "$dir" \
    --arg started_at "$started_at" \
    --arg origin_pwd "$origin_pwd" \
    --arg pid "$pid" \
    --arg sleep_pid "$sleep_pid" \
    --arg fired_epoch "$fired_epoch" \
    --argjson notify "$notify" \
    --argjson started_epoch "$started_epoch" \
    --argjson deadline_epoch "$deadline_epoch" \
    --argjson duration_seconds "$duration" \
    --argjson elapsed_seconds "$elapsed" \
    --argjson remaining_seconds "$remaining" \
    --argjson overdue_seconds "$overdue" \
    --argjson watcher_alive "$watcher_alive" \
    --argjson tags "$tags_json" \
    '{kind:$kind,id:$id,status:$status,label:$label,tags:$tags,state_dir:$state_dir,started_at:$started_at,started_epoch:$started_epoch,deadline_epoch:$deadline_epoch,duration_seconds:$duration_seconds,elapsed_seconds:$elapsed_seconds,remaining_seconds:$remaining_seconds,overdue_seconds:$overdue_seconds,notify:$notify,watcher_pid:(if $pid == "" then null else ($pid|tonumber) end),sleep_pid:(if $sleep_pid == "" then null else ($sleep_pid|tonumber) end),watcher_alive:$watcher_alive,fired_epoch:(if $fired_epoch == "" then null else ($fired_epoch|tonumber) end),origin_pwd:$origin_pwd}'
}

time_stop_countdown_worker() {
  local dir pid sleep_pid
  dir="$1"
  if ! pid="$(time_read_field "$dir" pid)"; then
    pid=""
  fi
  if ! sleep_pid="$(time_read_field "$dir" sleep_pid)"; then
    sleep_pid=""
  fi

  if time_pid_alive "$sleep_pid"; then
    if kill "$sleep_pid" >/dev/null 2>&1; then
      :
    fi
  fi

  if time_pid_alive "$pid"; then
    if kill "$pid" >/dev/null 2>&1; then
      :
    fi
  fi
}
