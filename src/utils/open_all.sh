#!/usr/bin/env bash

BASE_DIR="/home/frost/websites"

read -rp "Enter date (YYYY-MM-DD): " DATE

SEARCH_DIR="$BASE_DIR/$DATE"

if [[ ! -d "$SEARCH_DIR" ]]; then
    echo "Error: Directory not found: $SEARCH_DIR"
    exit 1
fi

find "$SEARCH_DIR" -type f -name "index.html" -print0 |
while IFS= read -r -d '' file; do
    echo "Opening: $file"
    chromium "$file" &
done

wait