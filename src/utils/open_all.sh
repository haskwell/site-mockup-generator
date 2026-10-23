#!/usr/bin/env bash

read -rp "Enter date (YYYY-MM-DD): " DATE

SEARCH_DIR="${WEBSITES_ROOT:-$HOME/websites/$DATE}"

if [[ ! -d "$SEARCH_DIR" ]]; then
    echo "Error: Directory not found: $SEARCH_DIR"
    exit 1
fi

mapfile -d '' FILES < <(find "$SEARCH_DIR" -type f -name "index.html" -print0)
if ((${#FILES[@]} == 0)); then
    echo "No sites found in: $SEARCH_DIR"
    exit 0
fi
echo "Opening ${#FILES[@]} site(s)"
chromium "${FILES[@]}" &
