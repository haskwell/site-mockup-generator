import argparse
import json
from pathlib import Path

import gspread


def follower_count(value):
    """Convert Instagram counts such as 1.2K or 2M into integers."""
    if isinstance(value, (int, float)):
        return int(value)
    text = str(value or "").strip().replace(",", "")
    if not text:
        return 0
    multiplier = 1
    if text[-1:].casefold() == "k":
        multiplier, text = 1_000, text[:-1]
    elif text[-1:].casefold() == "m":
        multiplier, text = 1_000_000, text[:-1]
    try:
        return int(float(text) * multiplier)
    except ValueError:
        return 0


def follower_bucket(n):
    if n < 500:
        return "0-500"
    if n < 1000:
        return "500-1k"
    if n < 5000:
        return "1k-5k"
    if n < 10000:
        return "5k-10k"
    if n < 50000:
        return "10k-50k"
    return "50k+"


def main():
    parser = argparse.ArgumentParser(description="Add one business summary JSON to the leads sheet.")
    parser.add_argument("leads_json", type=Path)
    parser.add_argument(
        "--credentials",
        type=Path,
        default=Path(__file__).resolve().with_name("creds.json"),
    )
    args = parser.parse_args()

    gc = gspread.service_account(filename=str(args.credentials))
    ws = gc.open("websites").sheet1
    with args.leads_json.open(encoding="utf-8") as f:
        leads = json.load(f)

    for lead in leads:
        names = ws.col_values(2)
        row = len(names) + 1
        number = len(names)
        ws.update(
            range_name=f"A{row}:F{row}",
            values=[
                [
                    number,
                    lead.get("name", ""),
                    lead.get("handle", ""),
                    lead.get("phone", ""),
                    lead.get("area", ""),
                    follower_bucket(follower_count(lead.get("followers"))),
                ]
            ],
        )


if __name__ == "__main__":
    main()
