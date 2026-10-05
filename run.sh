#!/usr/bin/env bash
# Usage: ./run.sh [accounts_file]      (default: config/accounts.txt)
#   FORCE=1 ./run.sh   rebuild the site even if one already exists (reuses scraped data)
#
# accounts.txt: one Instagram username per line. Blank lines, "# comments" and a
# leading "@" are ignored.
set -euo pipefail

REPO="$(cd "$(dirname "$0")" && pwd)"
ROOT="${WEBSITES_ROOT:-/home/frost/websites}"
ACCOUNTS_FILE="${1:-$REPO/config/accounts.txt}"
MODEL="gemini-3.8-flash-medium"
MIN_SIZE=600   # bytes; an unfilled skeleton index.html is smaller than this

if [[ -t 1 && -z "${NO_COLOR:-}" ]]; then
  C_INFO=$'\033[36m'
  C_SUCCESS=$'\033[32m'
  C_WARN=$'\033[33m'
  C_ERROR=$'\033[31m'
  C_RESET=$'\033[0m'
else
  C_INFO=''
  C_SUCCESS=''
  C_WARN=''
  C_ERROR=''
  C_RESET=''
fi

log() {
  local level="$1"
  shift
  local color
  case "$level" in
    SUCCESS) color="$C_SUCCESS" ;;
    WARN) color="$C_WARN" ;;
    ERROR) color="$C_ERROR" ;;
    *) color="$C_INFO" ;;
  esac
  printf '[%s] %s%-7s%s %s\n' "$(date +%H:%M:%S)" "$color" "$level" "$C_RESET" "$*"
}

[ -f "$ACCOUNTS_FILE" ] || { log ERROR "Accounts file not found: $ACCOUNTS_FILE"; exit 1; }
mkdir -p "$ROOT"

# Return codes: 0 = built, 1 = failed, 2 = skipped (already built)
# NOTE: this runs inside an if/|| context, so set -e is off in here;
# every step checks its own result with "|| return 1".
process_account() {
  local user="$1"
  local acct="$ROOT/$user"
  local data="$acct/${user}_data"
  local site="$acct/site"
  local agylog="$acct/logs/agy_$(date +%F_%H%M).log"

  mkdir -p "$acct/logs" "$site/assets" || return 1

  # Skip accounts that already have a finished site
  if [ "${FORCE:-0}" != "1" ] && [ -f "$site/index.html" ]; then
    local existing
    existing=$(wc -c < "$site/index.html" | tr -d ' ')
    if [ "$existing" -ge "$MIN_SIZE" ]; then
      log INFO "$user: site already built, skipping (use FORCE=1 to rebuild)"
      return 2
    fi
  fi

  # 1. Scrape (run from the account folder so data/debug land there;
  #    skips automatically if profile_data.json already exists)
  log INFO "$user: scraping..."
  ( cd "$acct" && python3 "$REPO/src/scraper.py" "$user" --captions --auth "$REPO/config/auth.json" ) \
    || { log ERROR "$user: scraper failed"; return 1; }
  [ -f "$data/profile_data.json" ] || { log ERROR "$user: no profile_data.json"; return 1; }

  # 1b. Extract name, handle, contact details and followers into a compact JSON file
  python3 "$REPO/src/profile_summary.py" "$data/profile_data.json" "$data/business_data.json" \
    || { log ERROR "$user: profile summary extraction failed"; return 1; }

  # 2. Pre-build the site skeleton so agy doesn't spend tokens on boilerplate
  cp -f "$data"/posts/web/*.webp "$site/assets/" || { log ERROR "$user: no images to copy"; return 1; }
  if [ -f "$data/pfp.jpg" ]; then
    cp -f "$data/pfp.jpg" "$site/assets/pfp.jpg" || { log ERROR "$user: failed to copy profile image"; return 1; }
  fi

  cat > "$site/index.html" <<'HTML'
<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Mockup</title>
  <link rel="icon" href="assets/pfp.jpg">
  <link rel="stylesheet" href="style.css">
</head>
<body>
</body>
</html>
HTML
  : > "$site/style.css"

  # Fresh copy of the rules next to the data, so agy can read them from its workspace
  cp -f "$REPO/prompts/GEMINI.md" "$acct/GEMINI.md" || { log ERROR "$user: failed to copy GEMINI.md"; return 1; }

  # 3. Let agy design the site
  log INFO "$user: building site with agy ($MODEL)..."
  local code=0
  ( cd "$acct" && timeout 900 agy \
      -p "Read $acct/GEMINI.md and follow it exactly. This is a design mockup. Source data: $data/profile_data.json. Images are already in $site/assets/ (post_N.webp and pfp.jpg); do not copy anything. $site/index.html and $site/style.css already exist as skeletons; fill them in." \
      --model "$MODEL" \
      --dangerously-skip-permissions ) \
    > "$agylog" 2>&1 || code=$?

  if [ "$code" -eq 124 ]; then
    log WARN "$user: agy timed out (see $agylog)"
  fi

  # 4. Success = index.html is bigger than the empty skeleton
  local size
  size=$(wc -c < "$site/index.html" | tr -d ' ')
  if [ "$size" -lt "$MIN_SIZE" ]; then
    log ERROR "$user: agy did not fill in index.html (see $agylog)"
    return 1
  fi
  log SUCCESS "$user: done -> $site/index.html ($size bytes)"
  return 0
}

# Read usernames: strip comments, CRs, leading spaces/@, trailing spaces, blank lines
mapfile -t USERS < <(
  sed -e 's/#.*$//' -e 's/\r$//' -e 's/^[[:space:]@]*//' -e 's/[[:space:]]*$//' "$ACCOUNTS_FILE" \
    | grep -v '^$' || true
)
total=${#USERS[@]}
[ "$total" -gt 0 ] || { log ERROR "No accounts found in $ACCOUNTS_FILE"; exit 1; }

ok=(); failed=(); skipped=()
i=0
for user in "${USERS[@]}"; do
  i=$((i + 1))
  log INFO "=== [$i/$total] @$user ==="
  rc=0
  process_account "$user" || rc=$?
  case "$rc" in
    0) ok+=("$user") ;;
    2) skipped+=("$user") ;;
    *) failed+=("$user") ;;
  esac

  # Polite random pause between accounts (not after the last, not after a skip)
  if [ "$i" -lt "$total" ] && [ "$rc" -ne 2 ]; then
    d=$((RANDOM % 41 + 20))
    log INFO "Waiting ${d}s before the next account..."
    sleep "$d"
  fi
done

echo
echo "================ Summary ================"
printf '%sBuilt:%s   %d  %s\n' "$C_SUCCESS" "$C_RESET" "${#ok[@]}" "${ok[*]:-}"
printf '%sSkipped:%s %d  %s\n' "$C_WARN" "$C_RESET" "${#skipped[@]}" "${skipped[*]:-}"
printf '%sFailed:%s  %d  %s\n' "$C_ERROR" "$C_RESET" "${#failed[@]}" "${failed[*]:-}"
echo "Output:  $ROOT/<username>/site/index.html"

[ "${#failed[@]}" -eq 0 ] || exit 1
