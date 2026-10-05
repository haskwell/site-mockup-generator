#!/usr/bin/env python3
"""Extract a compact business contact summary from scraper profile data."""

import argparse
import json
import re
from pathlib import Path
from typing import Any


PAKISTANI_CITIES = (
    "Karachi", "Lahore", "Islamabad", "Rawalpindi", "Faisalabad",
    "Peshawar", "Quetta", "Multan", "Hyderabad", "Gujranwala",
    "Sialkot", "Sargodha", "Bahawalpur", "Sukkur", "Larkana",
    "Sheikhupura", "Jhang", "Rahim Yar Khan", "Mardan", "Abbottabad",
    "Gujrat", "Sahiwal", "Okara", "Wah Cantt", "Dera Ghazi Khan",
    "Mirpur", "Muzaffarabad", "Gilgit", "Skardu",
)

# Match international and domestic Pakistani mobile/landline forms.
PHONE_RE = re.compile(
    r"(?<!\d)(?:\+?92|0092)[\s().-]*(?:0[\s().-]*)?"
    r"(?:3\d{2}[\s().-]*\d{7}|\d{2,3}[\s().-]*\d{6,7})"
    r"(?!\d)|(?<!\d)03\d{2}[\s().-]*\d{7}(?!\d)"
)


def extract_phone(text: str) -> str:
    match = PHONE_RE.search(text)
    if not match:
        return ""
    value = match.group(0).strip()
    # Normalize separators only; preserve the number's original country prefix.
    return re.sub(r"[\s().-]", "", value)


def extract_area(text: str) -> str:
    city_pattern = re.compile(
        r"(?<![\w])(" + "|".join(re.escape(city) for city in sorted(PAKISTANI_CITIES, key=len, reverse=True)) + r")(?![\w])",
        re.IGNORECASE,
    )
    match = city_pattern.search(text)
    if not match:
        return ""
    city = match.group(1)
    return next((known for known in PAKISTANI_CITIES if known.casefold() == city.casefold()), city)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("profile_json", type=Path)
    parser.add_argument("output_json", type=Path)
    args = parser.parse_args()

    with args.profile_json.open(encoding="utf-8") as source:
        profile: dict[str, Any] = json.load(source)
    bio = str(profile.get("bio") or "")
    result = [{
        "name": profile.get("name") or "",
        "handle": profile.get("handle") or "",
        "phone": extract_phone(bio),
        "area": extract_area(bio),
        "followers": profile.get("followers", ""),
    }]
    args.output_json.parent.mkdir(parents=True, exist_ok=True)
    with args.output_json.open("w", encoding="utf-8") as output:
        json.dump(result, output, indent=2, ensure_ascii=False)
        output.write("\n")


if __name__ == "__main__":
    main()
