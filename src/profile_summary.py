#!/usr/bin/env python3
"""Extract a compact business contact summary from scraper profile data."""

import argparse
import json
import re
from pathlib import Path
from typing import Any

try:
    from logging_config import get_logger
except ModuleNotFoundError:
    from src.logging_config import get_logger

logger = get_logger("profile_summary")


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
    r"(?:3\d{2}[\s().-]*\d{7}|\d{2,3}[\s().-]*\d{6,8})"
    r"(?!\d)|(?<!\d)03\d{2}[\s().-]*\d{7}(?!\d)"
    r"|(?<!\d)0\d{2,3}[\s().-]*\d{6,8}(?!\d)"
)


def normalize_phone(raw: str) -> str:
    cleaned = re.sub(r"[\s().-]", "", raw.strip())
    if not cleaned:
        return ""
    if cleaned.startswith("+92"):
        rest = cleaned[3:]
    elif cleaned.startswith("0092"):
        rest = cleaned[4:]
    elif cleaned.startswith("92"):
        rest = cleaned[2:]
    elif cleaned.startswith("0"):
        rest = cleaned[1:]
    else:
        rest = cleaned
    if rest.startswith("0"):
        rest = rest[1:]
    return f"+92{rest}"


def extract_phone(text: str) -> str:
    matches = list(PHONE_RE.finditer(text))
    if not matches:
        return ""
    # Return every distinct number so bios with multiple contact lines survive.
    values = []
    for match in matches:
        value = normalize_phone(match.group(0))
        if value and value not in values:
            values.append(value)
    return " / ".join(values)


def extract_area(text: str) -> str:
    city_pattern = re.compile(
        r"(?<![\w])(" + "|".join(re.escape(city) for city in sorted(PAKISTANI_CITIES, key=len, reverse=True)) + r")(?![\w])",
        re.IGNORECASE,
    )
    matches = city_pattern.finditer(text)
    found = []
    for match in matches:
        city = match.group(1)
        canonical = next((known for known in PAKISTANI_CITIES if known.casefold() == city.casefold()), city)
        if canonical not in found:
            found.append(canonical)
    return " & ".join(found)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("profile_json", type=Path)
    parser.add_argument("output_json", type=Path)
    args = parser.parse_args()

    logger.info("Extracting business summary from %s", args.profile_json)
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
    logger.info("Saved business summary to %s", args.output_json)


if __name__ == "__main__":
    main()
