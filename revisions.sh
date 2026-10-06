#!/usr/bin/env bash
# Apply non-empty sections from REVISIONS.md to their existing generated sites.
set -euo pipefail

REPO="$(cd "$(dirname "$0")" && pwd)"
LOG_DIR="$REPO/logs"
mkdir -p "$LOG_DIR"
SESSION_LOG="$LOG_DIR/$(date '+%Y-%m-%d_%H-%M-%S')_revisions_$$.log"
exec > >(tee "$SESSION_LOG") 2>&1

ROOT="${WEBSITES_ROOT:-/home/frost/websites}"
REVISIONS_FILE="$REPO/REVISIONS.md"
ACCOUNTS_FILE="$REPO/config/accounts.txt"
MODEL="gemini-3.8-flash-medium"
TIMEOUT_SECONDS=900
MIN_SIZE=600

if [[ ! -f "$REVISIONS_FILE" ]]; then
  printf 'ERROR    Revisions file not found: %s\n' "$REVISIONS_FILE"
  exit 1
fi
if [[ ! -f "$ACCOUNTS_FILE" ]]; then
  printf 'ERROR    Accounts file not found: %s\n' "$ACCOUNTS_FILE"
  exit 1
fi

log() {
  local level="$1"
  shift
  printf '%s %-8s %s\n' "$(date '+%Y-%m-%d %H:%M:%S')" "$level" "$*"
}

is_account() {
  local candidate="$1"
  local configured
  while IFS= read -r configured || [[ -n "$configured" ]]; do
    configured="${configured%%#*}"
    configured="${configured//$'\r'/}"
    configured="${configured#"${configured%%[![:space:]@]*}"}"
    configured="${configured%"${configured##*[![:space:]]}"}"
    [[ "$configured" == "$candidate" ]] && return 0
  done < "$ACCOUNTS_FILE"
  return 1
}

process_revision() {
  local user="$1"
  local revision="$2"
  local account_dir="$ROOT/$user"
  local site_dir="$account_dir/site"
  local agylog="$account_dir/logs/agy_revision_$(date +%F_%H%M%S).log"
  local code=0
  local size

  # Ignore whitespace-only sections.
  [[ -n "${revision//[[:space:]]/}" ]] || return 2
  if ! is_account "$user"; then
    log ERROR "Unknown account heading '#$user'; skipping"
    return 1
  fi
  if [[ ! -f "$site_dir/index.html" ]]; then
    log ERROR "$user: existing site not found at $site_dir/index.html"
    return 1
  fi
  if [[ ! -f "$account_dir/DESIGN.md" ]]; then
    log ERROR "$user: DESIGN.md not found in $account_dir"
    return 1
  fi

  mkdir -p "$account_dir/logs" || { log ERROR "$user: could not create logs directory"; return 1; }
  cp -f "$REPO/prompts/GEMINI.md" "$account_dir/GEMINI.md" \
    || { log ERROR "$user: failed to copy GEMINI.md"; return 1; }
  cp -f "$REPO/prompts/SKILL.md" "$account_dir/SKILL.md" \
    || { log ERROR "$user: failed to copy SKILL.md"; return 1; }

  log INFO "$user: revising site with agy ($MODEL)..."
  local prompt
  prompt="Revise the existing website in site/ to address these requested changes. Preserve its working content and assets unless a requested change requires updating them."
  prompt+=$'\n\nRevision requests:\n'
  prompt+="$revision"
  if (
    cd "$account_dir" && timeout "$TIMEOUT_SECONDS" agy \
      -p "$prompt" \
      --model "$MODEL" \
      --dangerously-skip-permissions
  ) 2>&1 | tee "$agylog" | while IFS= read -r line; do
    log INFO "$user: $line"
  done; then
    code=0
  else
    code=$?
  fi

  if [[ "$code" -eq 124 ]]; then
    log WARN "$user: agy timed out after ${TIMEOUT_SECONDS}s (see $agylog)"
  elif [[ "$code" -ne 0 ]]; then
    log ERROR "$user: agy exited with status $code (see $agylog)"
    return 1
  fi

  size=$(wc -c < "$site_dir/index.html" | tr -d ' ')
  if [[ "$size" -lt "$MIN_SIZE" ]]; then
    log ERROR "$user: index.html is smaller than $MIN_SIZE bytes after revision (see $agylog)"
    return 1
  fi
  log SUCCESS "$user: revision complete -> $site_dir/index.html ($size bytes)"
  return 0
}

declare -a OK=() FAILED=() SKIPPED=()
current_user=""
revision=""
finish_section() {
  [[ -n "$current_user" ]] || return 0
  local rc=0
  process_revision "$current_user" "$revision" || rc=$?
  case "$rc" in
    0) OK+=("$current_user") ;;
    2) SKIPPED+=("$current_user") ;;
    *) FAILED+=("$current_user") ;;
  esac
}

while IFS= read -r line || [[ -n "$line" ]]; do
  line="${line%$'\r'}"
  if [[ "$line" =~ ^#[[:space:]]*(.+)$ ]]; then
    finish_section
    current_user="${BASH_REMATCH[1]}"
    current_user="${current_user#"${current_user%%[![:space:]]*}"}"
    current_user="${current_user%"${current_user##*[![:space:]]}"}"
    revision=""
  elif [[ -n "$current_user" ]]; then
    revision+="$line"$'\n'
  fi
done < "$REVISIONS_FILE"
finish_section

log INFO "================ Revision summary ================"
log SUCCESS "Updated: ${#OK[@]} ${OK[*]:-}"
log WARN "Skipped: ${#SKIPPED[@]} ${SKIPPED[*]:-}"
log ERROR "Failed:  ${#FAILED[@]} ${FAILED[*]:-}"
[[ "${#FAILED[@]}" -eq 0 ]]
