#!/usr/bin/env bash

set -euo pipefail

cd "$(dirname "$0")"

USERNAME="${1:?usage: ./run.sh <instagram_username>}"
DATA="${USERNAME}_data"

python3 scraper.py "$USERNAME" --captions

MODEL="gemini-3.8-flash-medium"

timeout 900 agy \
  -p "Read GEMINI.md in $(pwd) and follow it exactly. Source data: $(pwd)/$DATA/profile_data.json. Images: $(pwd)/$DATA/posts/web/ and $(pwd)/$DATA/pfp.jpg. Build the site in $(pwd)/site/." \
  --model "$MODEL" \
  --dangerously-skip-permissions \
  > "logs/agy_$(date +%F_%H%M).log" 2>&1 || true