"""Deterministic design-direction generator for generated business sites.

Usage:
    python design.py "Joe's Bakery"
    python design.py "Joe's Bakery" --output DESIGN.md

Same username -> same direction on every run.
"""

import argparse
import pathlib
import random

from logging_config import get_logger

logger = get_logger("design")

AXES = {
    # ---- core composition ----
    "Hero": [
        "full-bleed photo with oversized type over it",
        "split screen: type on one side, photo on the other",
        "type-only hero with one small tilted photo",
        "single photo cropped into an unusual shape",
        "stacked collage of 3 photos at different scales",
        "one photo centered on a flat color field",
    ],
    "Layout rhythm": [
        "asymmetric and overlapping",
        "strict modular with generous gutters",
        "long vertical editorial scroll",
        "one horizontally scrolling section, the rest vertical",
        "big alternating color blocks",
    ],
    "Type personality": [
        "chunky and soft",
        "condensed and loud",
        "high-contrast elegant",
        "hand-drawn or script display",
        "quirky grotesque",
        "typewriter or mono accents",
    ],
    "Mood": ["playful", "luxurious", "rustic", "graphic and modern", "nostalgic"],
    # ---- optional ----
    "Alignment": ["left-aligned", "centered", "right-weighted", "mixed"],
    "Density": ["very airy", "medium", "packed and busy"],
    "Color strategy": [
        "monochrome tints of one brand color",
        "two-color duotone with a neutral",
        "dark mode with one glowing accent",
        "pastel multi-color",
        "a restrained base punctuated by deliberately clashing accents",
        "earthy and muted, low saturation",
    ],
    "Background treatment": [
        "flat solid colors",
        "subtle paper or grain texture",
        "soft gradients",
        "pattern or repeating motif from the business",
        "photo-tinted sections",
    ],
    "Imagery treatment": [
        "natural color, untouched",
        "duotone or color-overlay photos",
        "black-and-white with color accents",
        "photos with thick borders or frames",
        "cutouts with drop shapes behind them",
    ],
    "Shape language": [
        "sharp rectangles, zero radius",
        "fully rounded pills and circles",
        "organic blobs and wavy dividers",
        "arches and soft-cornered cards",
        "mixed: sharp containers, round buttons",
    ],
    "Borders and depth": [
        "no borders, flat",
        "thick outlined boxes, hard offset shadows",
        "hairline rules and fine dividers",
        "soft layered shadows",
        "overlapping translucent layers",
    ],
    "Decorative elements": [
        "none, let content carry it",
        "stickers, stamps, and badges",
        "large numerals or section numbers",
        "marquee or ticker text strips",
        "line illustrations or doodles",
        "oversized pull quotes",
    ],
    "Navigation style": [
        "classic top bar",
        "minimal logo plus hamburger on all sizes",
        "sticky side rail",
        "floating pill nav",
        "nav integrated into the hero",
    ],
    "Section order emphasis": [
        "story/about first, offerings second",
        "offerings first, story last",
        "social proof (reviews) right after hero",
        "gallery-heavy, text minimal",
    ],
    "Content presentation": [
        "cards grid",
        "alternating image/text rows",
        "accordion or tabbed",
        "big list with hover reveals",
        "masonry gallery",
        "timeline or stepped flow",
    ],
    "CTA style": [
        "one big persistent button",
        "text links with arrows",
        "sticky bottom bar on mobile",
        "form inline in the hero",
        "phone/WhatsApp-first (click to call)",
    ],
    "Footer": [
        "minimal one-liner",
        "oversized wordmark footer",
        "full sitemap with contact block",
        "map-forward footer",
    ],
    "Motion": [
        "static, no animation",
        "gentle fade-up on scroll",
        "parallax on hero imagery",
        "hover-driven micro-interactions",
        "scroll-linked marquee or reveal",
    ],
    "Hover feel": [
        "standard",
        "image-swap on hover",
        "color-invert on hover",
        "underline-draw animations",
    ],
    "Copy voice": [
        "warm and conversational",
        "short, punchy, declarative",
        "poetic and slow",
        "witty and a little irreverent",
        "professional and reassuring",
    ],
    "Headline style": [
        "questions",
        "single bold statements",
        "lowercase everything",
        "ALL CAPS short phrases",
        "mixed-weight within one headline",
    ],
    "Wildcard": [
        "one section styled like a receipt or ticket",
        "a section laid out like a magazine contents page",
        "an oversized cursor-following element",
        "a section that breaks the grid entirely",
        "one full-screen statement section with a single sentence",
    ],
}

# Always included; the rest are sampled.
CORE = ["Hero", "Layout rhythm", "Type personality", "Mood"]
OPTIONAL_COUNT = 6  # total axes per site = len(CORE) + OPTIONAL_COUNT

# Each rule: if every key/value in `a` AND every key/value in `b` are picked, reject.
CONFLICTS = [
    ({"Mood": "luxurious"}, {"Decorative elements": "stickers, stamps, and badges"}),
    ({"Mood": "luxurious"}, {"Density": "packed and busy"}),
    ({"Mood": "luxurious"}, {"Type personality": "chunky and soft"}),
    (
        {"Density": "very airy"},
        {"Hero": "stacked collage of 3 photos at different scales"},
    ),
    (
        {"Density": "very airy"},
        {"Decorative elements": "marquee or ticker text strips"},
    ),
    (
        {"Type personality": "hand-drawn or script display"},
        {"Headline style": "ALL CAPS short phrases"},
    ),
    ({"Type personality": "condensed and loud"}, {"Copy voice": "poetic and slow"}),
    ({"Shape language": "sharp rectangles, zero radius"}, {"Mood": "playful"}),
    ({"Color strategy": "dark mode with one glowing accent"}, {"Mood": "rustic"}),
    (
        {"Background treatment": "subtle paper or grain texture"},
        {"Color strategy": "dark mode with one glowing accent"},
    ),
    ({"Motion": "static, no animation"}, {"Hover feel": "underline-draw animations"}),
    (
        {"Motion": "static, no animation"},
        {"Wildcard": "an oversized cursor-following element"},
    ),
    (
        {"Layout rhythm": "one horizontally scrolling section, the rest vertical"},
        {"Content presentation": "masonry gallery"},
    ),
]


def normalize(text: str) -> str:
    return " ".join(text.strip().lower().split())


def violates(picks: dict) -> bool:
    """True if any conflict rule has all of its conditions present in picks."""
    for a, b in CONFLICTS:
        rule = {**a, **b}
        if all(picks.get(k) == v for k, v in rule.items()):
            return True
    return False


def pick_direction(username: str, max_tries: int = 200) -> dict:
    rng = random.Random(normalize(username))

    optional_axes = [a for a in AXES if a not in CORE]
    picks = {}
    for _ in range(max_tries):
        chosen = CORE + rng.sample(optional_axes, k=OPTIONAL_COUNT)
        picks = {axis: rng.choice(AXES[axis]) for axis in chosen}
        if not violates(picks):
            break
    # Preserve the AXES ordering so the prompt reads consistently.
    return {axis: picks[axis] for axis in AXES if axis in picks}


def build_direction(username: str) -> str:
    picks = pick_direction(username)
    lines = "\n".join(f"- {axis}: {value}" for axis, value in picks.items())
    return (
        "\n\n## Direction for this site\n"
        f"{lines}\n"
        "Treat these as fixed constraints and fit the business into them using "
        "its photos and palette. Anything not listed is up to you, but keep it "
        "consistent with the choices above. If one constraint clashes badly "
        "with the business, adapt that single axis and say which in your final "
        "summary.\n"
    )


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("username", help="business account username")
    parser.add_argument(
        "--output",
        default="DESIGN.md",
        help="path for the generated design direction (default: DESIGN.md)",
    )
    args = parser.parse_args()

    path = pathlib.Path(args.output)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        f"# Design direction for @{args.username}\n" + build_direction(args.username),
        encoding="utf-8",
    )
    logger.info("Wrote design direction to %s", path)


if __name__ == "__main__":
    main()
