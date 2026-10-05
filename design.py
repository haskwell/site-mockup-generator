#!/usr/bin/env python3
"""Pick one design direction at random and write it to DESIGN.md.

Usage:
    python pick_design.py                 # writes ./DESIGN.md
    python pick_design.py path/to/DESIGN.md

Every design is written to sit inside the rules in GEMINI.md: one accent
colour, a warm or neutral background, near-black text, two type families,
staggered (not uniform) galleries, images never wider than ~500px, no frames
or boxes around every image, no heavy shadows, no centred-everything layouts,
and no invented captions or copy.
"""

import random
import sys
from pathlib import Path

PRECEDENCE = (
    "GEMINI.md wins on any conflict. This file only chooses the visual "
    "direction. It is the one signature design idea GEMINI.md asks for, so "
    "use it instead of inventing another. It never adds facts, captions, "
    "an About story, prices or copy."
)

SHARED_RULES = """\
- Colour: follow GEMINI.md. A warm or neutral background, near-black text and
  ONE accent taken from 3 to 5 of the photos. Tints of that single accent are
  fine. Put the hex codes in :root. The design below only decides how the
  colour is used.
- Type: two families only, one expressive serif or display face for headings
  and one clean sans for body. Google Fonts via <link> with system fallbacks.
- Images: natural aspect ratio, never wider than about 500px. Corner radius is
  allowed, but never change an image's aspect ratio or crop it to a uniform
  shape. No frames or borders around images, no shadows.
- Captions: show a post's caption only if it is non-empty and evergreen.
  Otherwise show nothing under the image. Never invent text for images.
- Logo: pfp.jpg only small (40 to 64px). Never use it as a large image.
- Sparse accounts: with fewer than 8 usable posts, give each image more space
  within the size cap instead of adding filler.
- Reels: small play marker made with CSS or SVG, linked to the post URL.
- Section separation: spacing and type size only. No divider lines, no boxes
  around sections.
"""

MOBILE_RULES = """\
Design the phone layout first (390px, and nothing breaks at 360px). GEMINI.md
already requires mobile-first CSS, no horizontal scrolling and comfortable tap
targets. In addition:
- Body text at least 16px. Buttons and links at least 44px tall to tap.
- Hover is decoration only. Nothing important may appear only on hover.
- Full-height sections use svh or dvh, never vh.
- The order or Instagram link must be reachable again after the gallery, not
  only in the header.
- The phone layout must be designed on purpose, not a shrunken desktop page.
"""

FIELDS = [
    ("Signature idea", "signature"),
    ("Mood", "mood"),
    ("Colour use", "colour"),
    ("Type", "type"),
    ("Opening", "opening"),
    ("Gallery", "gallery"),
    ("Page order", "order"),
    ("Details", "details"),
    ("Motion", "motion"),
    ("Phone layout", "phone"),
]

# The "suits" key is for your own reference (e.g. a future category hint).
# It is not written to DESIGN.md.
DESIGNS = [
    {
        "name": "Cottage Warm",
        "suits": "bakeries, home cooks; fine for artists",
        "signature": "A huge soft-serif name set hard left with the bio as a handwritten-feeling italic tagline beside it. Images drift in a zig-zag, alternating left and right at different widths, like things left on a kitchen table.",
        "mood": "Friendly, homely, generous.",
        "colour": "Warm cream background, deep brown-black text. The accent is the warmest tone in the photos, used on key words in the headline and on the order link.",
        "type": "Fraunces for headings, Nunito Sans for body. Fallbacks: Georgia, system-ui.",
        "opening": "Left-aligned name at very large size, bio tagline beneath in a narrow column, small pfp beside the name.",
        "gallery": "Zig-zag column. On phones image widths vary between about 60% and 100% with left or right offsets. On desktop widths vary between about 280px and 500px, with some images pulled up beside the text.",
        "order": "Header, opening, gallery, how to order, footer.",
        "details": "12px image corner radius. The accent underlines the order link.",
        "motion": "Fade-up on scroll. Images lift 4px on hover.",
        "phone": "Single column, zig-zag created with margins, name sized with clamp().",
    },
    {
        "name": "Gallery White",
        "suits": "artists, jewellery; warm the white for bakeries",
        "signature": "A gallery wall: lots of empty white with images floating at very different sizes and positions, each given room like a hung print.",
        "mood": "Quiet, spacious, confident.",
        "colour": "Near-white with a slight warm tint, near-black text. The accent appears only on links and the order link.",
        "type": "Instrument Serif for headings, Inter for body.",
        "opening": "Name very large in a light weight, bio in a small narrow column offset to the right of or below the name.",
        "gallery": "Loose 12-column placement: images span 3 to 7 columns with uneven vertical offsets and wide gaps. On phones, a single column where widths alternate between 65% and 100% with a left or right offset.",
        "order": "Header, opening, gallery, how to order, footer.",
        "details": "No radius, no frames, no shadows. Tiny type for secondary details.",
        "motion": "Slow fade-in on scroll and nothing else.",
        "phone": "Generous vertical gaps (at least 20vh between some images) so each image gets its own moment.",
    },
    {
        "name": "Atelier Stone",
        "suits": "jewellery, small objects; fine for artists",
        "signature": "Spotlight spacing: each image sits almost alone, offset to one side with a huge empty margin and a small index number beside it. The headline is a thin, widely tracked display serif.",
        "mood": "Refined, intimate, unhurried.",
        "colour": "A slightly deeper stone or taupe background taken from the photos' neutrals, near-black text. The accent is used for index numbers and links.",
        "type": "Cormorant Garamond in a light weight for headings, Montserrat in small sizes for body.",
        "opening": "Name large and left-aligned in the light serif, bio set small beneath and offset, small pfp beside the name.",
        "gallery": "One image at a time, alternating between the left third and right third of the page. Small numerals (01, 02...) beside each image. Large empty space above and below each one.",
        "order": "Header, opening, gallery, how to order, footer.",
        "details": "No frames. A thin accent underline only on links.",
        "motion": "400ms opacity fades on scroll and hover.",
        "phone": "Images up to full phone width, alternating with margins of 0 and 15%, numerals above each image.",
    },
    {
        "name": "Pastel Boutique",
        "suits": "bakeries, craft sellers; fine for jewellery",
        "signature": "Arch-topped images (rounded top corners only, aspect ratio kept) sitting on soft tinted colour fields that bleed to the screen edge. Sweet and soft without being childish.",
        "mood": "Playful, soft, cheerful.",
        "colour": "Very pale tint of the accent as the main background, with a slightly stronger tint for colour fields. The full-strength accent is used on the order button only. Text stays near-black.",
        "type": "Fredoka for headings, Nunito Sans for body.",
        "opening": "A tinted field running to the screen edges holds the large name and bio. Small pfp overlaps the field's lower edge.",
        "gallery": "Staggered two columns with the second column dropped lower. Each image has an arch top via border-radius (for example 999px 999px 12px 12px) and keeps its aspect ratio. Widths vary between columns.",
        "order": "Header, opening field, gallery, how to order on a tinted field, footer.",
        "details": "Pill-shaped order button. No outlines.",
        "motion": "Images scale up 3% on hover and rise on scroll.",
        "phone": "Two staggered columns that stay two columns down to 360px, name wraps over two lines.",
    },
    {
        "name": "Kraft and Tape",
        "suits": "bakeries, craft; fine for artists",
        "signature": "Handmade stall feel: the name sits on a luggage-tag shaped label, and images look taped to a paper page with slight rotation and occasional tape strips.",
        "mood": "Handmade, tactile, warm.",
        "colour": "Kraft-paper beige background, ink-brown near-black text. The accent is a stamp-like tone from the photos, used on the tag and tape strips.",
        "type": "Zilla Slab for headings, Source Sans 3 for body.",
        "opening": "The name on a tag-shaped label (clip-path or notched corner) at the top left, bio set beside or below it in a narrow column.",
        "gallery": "Scattered column: images of different widths, rotated 1 to 2 degrees in alternating directions, and a small accent tape strip (CSS pseudo-element) on roughly every third image. No frames, no shadows.",
        "order": "Header with tag, gallery, how to order, footer.",
        "details": "Dashed underline on the order link. Tape strips are the only decoration.",
        "motion": "Images straighten to 0 degrees on hover (decoration only).",
        "phone": "Single column with rotation capped at 1.5 degrees and widths varying 65% to 100%.",
    },
    {
        "name": "Editorial Column",
        "suits": "all three; best when the bio is long",
        "signature": "A magazine feature: an oversized serif headline, a drop cap on the bio, and one narrow image column set off-centre with the headline hanging in the margin.",
        "mood": "Calm, confident, story-led.",
        "colour": "Warm white, near-black text. The accent colours the drop cap and links only.",
        "type": "DM Serif Display for headings, Source Sans 3 for body at 18px with 1.7 line height.",
        "opening": "Very large name as the headline. The bio follows as the article text with a drop cap, in a column of about 60 characters.",
        "gallery": "A single column no wider than 480px. Images alternate between full column width and about 70% width with an indent. On desktop the column sits right of centre with the headline in the wide left margin. If the bio contains a short line that works as a pull quote, set it large between images (bio words only).",
        "order": "Header, headline and bio, gallery, how to order as a closing note, footer.",
        "details": "No frames, no cards. Plenty of leading.",
        "motion": "No scroll effects. Underline animation on links only.",
        "phone": "Same single-column structure, headline scales with clamp().",
    },
    {
        "name": "Collage Zine",
        "suits": "artists, craft; fine for bakeries; keep jewellery images upright",
        "signature": "Scrapbook collage: a very large condensed name overlapped by two or three photos at slight angles, with accent-coloured sticker labels.",
        "mood": "Loose, personal, energetic.",
        "colour": "Pale paper background, near-black text. Every sticker label uses the single accent.",
        "type": "Anton for headings, DM Sans for body.",
        "opening": "Condensed name set huge and left-aligned, with 2 or 3 photos overlapping its edges at small angles. Bio on a sticker-style label.",
        "gallery": "Overlapping scatter: widths vary between 40% and 90%, rotation up to 3 degrees, negative margins so images tuck under each other. Each image stays at least 85% visible. No shadows.",
        "order": "Header, collage opening, gallery, how to order on a sticker label, footer.",
        "details": "Sticker labels with a small radius. Reels get a play marker on a sticker.",
        "motion": "Images straighten and rise slightly on hover.",
        "phone": "Overlap limited to roughly 15% of an image, rotation up to 2 degrees, staggered single column.",
    },
    {
        "name": "Lookbook Spread",
        "suits": "jewellery, products; fine for bakeries and artists",
        "signature": "Printed lookbook spreads: each spread pairs one large image with two small ones in an offset arrangement, numbered like pages.",
        "mood": "Polished, product-focused, editorial.",
        "colour": "Neutral light background, near-black text. The accent, taken from the strongest photo, is used for spread numbers and links.",
        "type": "Bodoni Moda for headings, Jost for body.",
        "opening": "Name in large tracked uppercase across the top, bio beneath, with the best image offset to the right of the name (max 500px).",
        "gallery": "Repeating spreads: one large image (up to 500px) and two small ones (about 200px) overlapping its corner or sitting beside it. Alternate the large image from left to right on each spread. Page numbers like 01 / 05 in the accent.",
        "order": "Header, opening, spreads, how to order, footer.",
        "details": "Small tracked uppercase labels. No frames.",
        "motion": "Small images slide 12px into place on scroll.",
        "phone": "Large image at full phone width, the two small images side by side at different heights beneath it.",
    },
    {
        "name": "Colour Block",
        "suits": "bakeries, craft, artists; keep it restrained for jewellery",
        "signature": "One huge full-width block of the accent colour behind the enormous name. The rest of the page is neutral so the colour lands exactly once.",
        "mood": "Cheerful, confident, market-poster bold.",
        "colour": "Neutral light background. The accent fills the opening block at full strength, with near-black or white text chosen for contrast.",
        "type": "Archivo Black for headings, Work Sans for body.",
        "opening": "A full-bleed accent block at the top holds the name at an enormous size. The first image overlaps the block's lower edge. Bio below the block in a narrow column.",
        "gallery": "Staggered placement with large size jumps (about 200px to 500px), alternating sides, some images pulled upward to overlap the previous one's space.",
        "order": "Header, colour block opening, gallery, how to order, footer.",
        "details": "Flat accent buttons with no shadows or outlines.",
        "motion": "The block slides in 8px on load. Buttons darken on hover.",
        "phone": "Name wraps to 2 or 3 lines inside the block at the largest size that fits.",
    },
    {
        "name": "Botanical Soft",
        "suits": "bakeries, artists, jewellery; best with natural-toned photos",
        "signature": "Soft organic shapes: a large blob of pale accent tint sits behind the name, and images use soft corner radii that differ from one image to the next.",
        "mood": "Calm, natural, slow-made.",
        "colour": "Light warm background, deep earthy near-black text. The accent is a muted natural tone from the photos, with a pale tint for the blob.",
        "type": "Cormorant Garamond with italic emphasis for headings, Lato for body.",
        "opening": "Name and bio on the left over a large soft blob (CSS border-radius or inline SVG), small pfp beside the name.",
        "gallery": "Staggered two columns with the second column dropped by roughly 8 to 15vw. Each image gets a different border-radius (for example 32px 8px 32px 8px, or 48px) but keeps its aspect ratio.",
        "order": "Header, opening, gallery, how to order, footer.",
        "details": "Nothing sharp. Links get a soft accent highlight behind the text.",
        "motion": "Slow 600ms scale on hover (decoration only), gentle fade on scroll.",
        "phone": "Blob scales down behind the name, columns stay two with a reduced offset.",
    },
    {
        "name": "Sticky Panel",
        "suits": "artists, jewellery; warm the panel for bakeries",
        "signature": "On desktop the name, bio and order link stay fixed in a tinted left panel while the images scroll past in a staggered feed. On phones the panel becomes a compact top header.",
        "mood": "Structured, calm, focused on the work.",
        "colour": "Neutral light main area, near-black text. The side panel uses a pale tint of the accent. The full accent is used for the order link.",
        "type": "Young Serif for headings, Public Sans for body.",
        "opening": "No separate hero. The panel holds the name (large), bio, small pfp, Instagram link and order link.",
        "gallery": "A feed with a mix of single images and offset pairs, widths between 220px and 500px, aligned to varying positions in the right area.",
        "order": "Panel (name, bio, order link), image feed, how to order after the feed, footer.",
        "details": "The panel is separated by colour only, with no divider line.",
        "motion": "Gentle fade on scroll. Link underline slides in on hover.",
        "phone": "Panel becomes a normal header. Order link repeats after the feed because the panel no longer stays visible.",
    },
    {
        "name": "Numbered Index",
        "suits": "all three; works with few or many posts",
        "signature": "A running catalogue: every image has a very large numeral in the accent colour that partly overlaps its corner, so the gallery reads like a numbered index of the work.",
        "mood": "Organised, characterful, graphic.",
        "colour": "Warm light background, near-black text. The accent colours the numerals and links.",
        "type": "Playfair Display for headings and the numerals, DM Sans for body.",
        "opening": "Name large and left-aligned with the bio beneath, followed by a short line pointing to the order link.",
        "gallery": "Images at different widths pinned alternately to the left and right edges. A big numeral (01, 02...) in the heading face overlaps a corner of each image. Reels carry a play marker beside the numeral.",
        "order": "Header, opening, indexed gallery, how to order, footer.",
        "details": "No captions unless a post has an evergreen caption of its own.",
        "motion": "Numerals drift 8px against the scroll direction. Images fade in.",
        "phone": "Numerals scaled down with clamp() so they overlap the image corner but never cover its subject.",
    },
]


def render(design: dict) -> str:
    lines = [
        "# DESIGN",
        "",
        f"## {design['name']}",
        "",
        PRECEDENCE,
        "",
        "### Rules shared by every design",
        "",
        SHARED_RULES,
    ]
    for title, key in FIELDS:
        lines += [f"### {title}", "", design[key], ""]
    lines += ["### Mobile rules", "", MOBILE_RULES]
    return "\n".join(lines)


def main() -> None:
    out = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("DESIGN.md")
    design = random.choice(DESIGNS)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(render(design), encoding="utf-8")
    print(f"Selected design: {design['name']} -> {out}")


if __name__ == "__main__":
    main()
