#!/usr/bin/env python3
"""Cycle through distinct visual directions for small, image-led businesses.

Usage:
    python src/design.py                   # writes ./DESIGN.md
    python src/design.py path/to/DESIGN.md
"""

import sys
from pathlib import Path

STATE_FILE = Path(__file__).with_name(".design_index")

PRECEDENCE = (
    "prompts/GEMINI.md is authoritative for facts, content, and technical "
    "requirements. This file defines the visual direction: follow its specific "
    "composition instead of replacing it with a generic editorial collage or "
    "inventing a different concept."
)

SHARED_RULES = """\
- Treat the chosen direction as the design brief, not as loose inspiration.
  Implement its stated composition, hierarchy, image scale, alignment, and
  section rhythm. Do not add a second competing concept.
- Palette: derive colors from the photos and the selected mood. Use readable
  contrast. A warm neutral base and one accent are a useful default, not a
  requirement; a direction may call for a dark ground, a bold color field, or
  more than one carefully related color.
- Typography: use no more than two font families. Choose type with a clear
  relationship to the selected direction. Google Fonts via <link> with system
  fallbacks are allowed.
- Images: preserve natural aspect ratios by default. A direction may feature
  one deliberate full-bleed or art-directed hero image; crop that image only
  when the crop serves the composition and its subject remains clear. Do not
  force every gallery image into the same crop or size.
- Captions: show a post caption only when it is non-empty and evergreen.
  Otherwise show nothing under the image. Never invent text.
- Logo: pfp.jpg only small (40 to 64px). Never use it as a large image.
- Sparse accounts: with fewer than 8 usable posts, give available images room
  and do not add filler.
- Reels: use a small play marker made with CSS or SVG, linked to the post URL.
- Use section backgrounds, borders, rules, or framing only when they are
  deliberate parts of the selected direction; do not decorate every section.
"""

MOBILE_RULES = """\
Design the phone layout first (390px, and nothing breaks at 360px). Preserve the
chosen direction's defining feature on mobile rather than shrinking a desktop
layout into a generic stack.
- Body text at least 16px. Buttons and links at least 44px tall to tap.
- Hover is decoration only. Nothing important may appear only on hover.
- Full-height sections use svh or dvh, never vh.
- The order or Instagram link must be reachable again after the gallery, not
  only in the header.
- No horizontal page scrolling. Full-bleed imagery may touch the viewport edge.
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

DESIGNS = [
    {
        "name": "Full-Bleed Campaign",
        "suits": "businesses with one striking, high-quality hero photo",
        "signature": "A cinematic, edge-to-edge opening image owns the first viewport. The business name is set very large over or directly against the image, with a restrained contrast treatment. This is a deliberate campaign cover, not a small image in a padded hero.",
        "mood": "Confident, immersive, high-impact.",
        "colour": "Build the palette from the hero photo. Let the image supply most color; use a solid readable text treatment and one restrained supporting color below.",
        "type": "A high-contrast display serif such as Bodoni Moda for the name, paired with a neutral sans such as DM Sans for utility text.",
        "opening": "A compact transparent or solid header sits over the hero. The hero image runs full viewport width and roughly 75–90svh tall, with the name and actual bio placed as a carefully composed overlay. Do not add generic promotional copy.",
        "gallery": "After the hero, use a clean, deliberate sequence of medium-sized images with consistent alignment and generous gaps. Keep this gallery quiet so the opening image remains the signature.",
        "order": "Overlay header, full-bleed campaign hero, image sequence, how to order, footer.",
        "details": "Use a subtle text shadow or solid backing only if needed for legibility. No decorative collage, stickers, or unrelated overlap.",
        "motion": "A very slow hero image reveal or simple fade is enough; no parallax that hurts readability.",
        "phone": "Keep the hero edge-to-edge and preserve the large name. Set hero height with svh and place text where it does not hide the image's subject.",
    },
    {
        "name": "Split-Screen Atelier",
        "suits": "artists, jewellery, makers, and product-led businesses",
        "signature": "A decisive two-part composition: one half is a calm brand panel, the other is a single tall image. The vertical split is the identity; do not turn it into a collage.",
        "mood": "Precise, modern, composed.",
        "colour": "Use a quiet photo-derived background with dark text, and let the image provide the strongest color. A single accent may mark the order link.",
        "type": "Use a refined serif for the business name and a clean geometric sans for body and small labels.",
        "opening": "On desktop, place the name, bio, and order link in a vertically centered text panel beside a large portrait-orientation image. Keep the two halves visibly distinct and avoid overlaying copy on the image.",
        "gallery": "Continue with paired image-and-text-free compositions: one image per row, alternating which side it occupies. Keep images large but preserve their proportions.",
        "order": "Quiet header, split opening, alternating image rows, how to order, footer.",
        "details": "Use broad margins and a clean vertical seam between the halves. Avoid cards, stickers, and floating elements.",
        "motion": "Simple image fade-in only.",
        "phone": "Stack text panel then hero image. Keep the split concept through a strong background transition and generous separation, not by squeezing both columns.",
    },
    {
        "name": "Vertical Image Runway",
        "suits": "food, floristry, objects, and visually tactile work",
        "signature": "A long, uninterrupted runway of large images, one per row. The page feels like a focused visual procession rather than a thumbnail gallery.",
        "mood": "Sensory, immersive, unhurried.",
        "colour": "Use a grounded background and muted text so the photos lead. Pull one color from the images for the order link or small running label.",
        "type": "An expressive editorial serif for the name with a quiet, readable sans for the bio and details.",
        "opening": "Place a small header and unusually large name above the first image. The bio is concise and sits beside or just beneath the wordmark; do not place a hero image behind the text.",
        "gallery": "Show one large image at a time in a centered, consistent column, allowing up to about 85vw on desktop. Keep natural ratios, regular vertical intervals, and no alternating offsets or multi-column grid.",
        "order": "Header, name and bio, single-image runway, how to order as a clear pause, footer.",
        "details": "Small sequential labels may introduce each image. No frames, cards, or decorative collage.",
        "motion": "A subtle dissolve between image entrances; no scale or parallax effects.",
        "phone": "Keep the single-image sequence and close to full available width with comfortable side gutters.",
    },
    {
        "name": "Typographic Poster",
        "suits": "bold, playful, or instantly recognizable brand names",
        "signature": "Treat the first screen like a beautifully typeset poster: the business name dominates the canvas in oversized, tightly composed type. Photography enters later and does not compete with the wordmark.",
        "mood": "Loud, graphic, self-assured.",
        "colour": "Choose one strong color from the account imagery for a large solid poster field, paired with a contrasting readable text color. Keep later sections mostly neutral.",
        "type": "Use a bold condensed or heavy display face for the name, with a simple sans for everything else.",
        "opening": "Create a full-width color field containing the very large name, a small logo if available, and the actual bio. The name may wrap dramatically. Do not put photos over the lettering.",
        "gallery": "Below the poster, use a restrained sequence of broad rectangular image panels with consistent edges and varied heights. Keep the typography-led opening as the main statement.",
        "order": "Small header, poster-like name field, photo sequence, how to order, footer.",
        "details": "Favor solid color and type over decoration. One small uppercase label or rule is enough.",
        "motion": "No animation beyond a short opacity fade on the poster.",
        "phone": "Let the wordmark break across several lines with intentional spacing. Keep all letters within the viewport and retain the strong color field.",
    },
    {
        "name": "Nocturne Filmstrip",
        "suits": "artists, jewellery, ceramics, and refined product photography",
        "signature": "A dark, immersive image experience built around a single horizontal filmstrip. Each photo gets a generous portrait tile, with the next tile visibly peeking in to invite a deliberate swipe.",
        "mood": "Quiet, nocturnal, premium.",
        "colour": "Use a deep ink or charcoal background with warm white type. Keep photo colors intact; a muted photo-derived accent is optional for links only.",
        "type": "A fine display serif for the name and a highly legible neutral sans for details.",
        "opening": "Use a small understated header and a large left-aligned name above the gallery. Keep the bio brief and separated from the images; no image overlay or light hero panel.",
        "gallery": "Create one horizontal, swipeable track of portrait tiles on the dark ground, with scroll-snap and a small glimpse of the next image. Keep each tile at a consistent scale and preserve its natural ratio. Do not use a vertical feed or multi-column grid.",
        "order": "Dark header, restrained name and bio, single horizontal filmstrip, how to order, dark footer.",
        "details": "Use small sequence numbers below the tiles and generous space above and below the track. Ensure contrast remains strong.",
        "motion": "Rely on native swipe and scroll-snap; no automatic movement.",
        "phone": "Make the filmstrip swipeable with a clear next-tile preview and no page-level horizontal overflow. Keep the dark gallery presentation.",
    },
    {
        "name": "Diptych Pairings",
        "suits": "accounts with two complementary kinds of work or strong image pairs",
        "signature": "Build the gallery from paired diptychs: two adjacent images form one composition, separated by a narrow gutter. Pairing, not staggering or overlap, is the defining move.",
        "mood": "Curated, balanced, quietly surprising.",
        "colour": "Choose a calm background and near-black type. Let each image pair carry the color; accent is reserved for links.",
        "type": "A graceful serif for the brand name and a neutral sans for body copy.",
        "opening": "Start with the name and bio in a compact left-aligned masthead, followed by one full-width diptych. Do not add a giant hero image.",
        "gallery": "Arrange posts in side-by-side pairs, varying each pair's image proportions but keeping its outer edges aligned. For odd post counts, finish with a single centered image.",
        "order": "Compact masthead, repeated diptych gallery, how to order, footer.",
        "details": "A narrow consistent gutter separates paired images. No overlapping or offset collage elements.",
        "motion": "No scroll effects; a soft hover treatment may identify reel links.",
        "phone": "Stack the images within each pair at narrow widths while retaining pair order and a small shared gap.",
    },
    {
        "name": "Paper Market",
        "suits": "bakeries, home businesses, crafts, and handmade goods",
        "signature": "A maker's catalog set like a printed market list: each entry is a horizontal row with a modest image on the left and sparse, factual text on the right. The repeated rows—not a collage—create the identity.",
        "mood": "Warm, handmade, inviting.",
        "colour": "Use a warm paper ground, dark ink text, and one earthy accent drawn from the photos. Solid fields are allowed; avoid faux textures that reduce legibility.",
        "type": "A characterful slab serif or rounded display face for the name, paired with a practical sans.",
        "opening": "Set the name as a strong printed wordmark at the top of a clean paper-colored page. Place the bio and order link beneath it as a compact maker's note.",
        "gallery": "Arrange posts as a vertical list of horizontal catalog rows. Each row has a contained, natural-ratio image taking roughly one-third of the row and a text area that may show only that post's actual evergreen caption. When no caption exists, leave the text area quiet; do not invent titles or prices.",
        "order": "Wordmark header, maker's note, horizontal catalog list, how to order in a tinted paper panel, footer.",
        "details": "Separate catalog rows with generous spacing or a light paper rule. Use small sequence labels; no fake paper grain, tape, or shadow.",
        "motion": "No motion required; links may change color on hover.",
        "phone": "Stack each catalog row into a compact image-then-caption unit, keeping the repeated list structure and paper palette. Keep the wordmark and order link prominent.",
    },
    {
        "name": "Floating Gallery Wall",
        "suits": "artists, makers, jewellery, and accounts with varied portrait/landscape images",
        "signature": "A curated gallery wall with generous empty space and a few deliberately placed, differently scaled images. Use only a handful of intentional offsets; this is not an instruction to stagger every post.",
        "mood": "Airy, considered, art-led.",
        "colour": "Warm white or pale stone with dark type. Let one muted accent appear only in the identity or order link.",
        "type": "A light expressive serif for the name and a quiet sans for short supporting copy.",
        "opening": "Place a modest wordmark and bio in a quiet corner, leaving an open field before the first image. No full-bleed hero or colored poster block.",
        "gallery": "Arrange selected images like prints on a wall: mix sizes and allow broad whitespace, but align each image deliberately. Use a simple single column on phones rather than preserving desktop scatter.",
        "order": "Small header, open masthead, curated gallery wall, how to order, footer.",
        "details": "Keep image edges clean and avoid frames, labels on every image, or decorative overlays.",
        "motion": "A gentle fade-in, with no movement of the images.",
        "phone": "Convert to a calm vertical sequence with variable but controlled image widths and ample breathing room.",
    },
    {
        "name": "Color Field Sequence",
        "suits": "accounts with a distinctive accent color and concise bio",
        "signature": "A sequence of oversized, edge-to-edge color fields alternates with full-width image bands. The business name occupies its own color field; imagery and typography never overlap. The repeated banding is the design system.",
        "mood": "Contemporary, punchy, designed.",
        "colour": "Select a saturated but grounded photo-derived accent and pair it with a contrasting neutral. Maintain readable text contrast; avoid gradients.",
        "type": "A sharp modern sans for the name with a humanist sans for the bio and order details.",
        "opening": "Begin with a tall solid accent field carrying the oversized name and actual bio. Follow it with a full-width image band on a neutral ground; do not overlay the two.",
        "gallery": "Alternate broad color bands and full-width image bands in a measured sequence. Keep image edges aligned and aspect ratios natural; the gallery is neither a staggered collage nor a thumbnail grid.",
        "order": "Oversized color-field masthead, alternating image and color bands, contrasting order field, footer.",
        "details": "Make the large color fields the primary graphic device. Use clean edges and avoid cards, shadows, and extra decorative shapes.",
        "motion": "No animation; keep the color transitions and photography direct.",
        "phone": "Preserve the full-width bands as stacked color and image sections. Scale the name to fit without shrinking into a small heading.",
    },
    {
        "name": "Sticky Studio Rail",
        "suits": "artists, jewellery, and product-focused accounts with many images",
        "signature": "On wide screens, a narrow fixed-feeling identity rail stays alongside a spacious image field. The rail is the anchor; images flow in one simple column, not a staggered feed.",
        "mood": "Architectural, calm, studio-like.",
        "colour": "A pale stone or warm neutral main area with near-black type. Use a muted accent for one action in the identity rail.",
        "type": "A balanced serif for the name and a highly legible sans for compact rail information.",
        "opening": "Do not create a separate hero. The left rail contains a small logo, name, bio, Instagram link, and order action; the first image begins in the main column.",
        "gallery": "Keep a single aligned image column in the main area, with substantial but consistent vertical spacing. Images may vary in width only where their aspect ratio naturally requires it.",
        "order": "Persistent identity rail, flowing image column, how to order after the gallery, footer.",
        "details": "Separate the rail using background tone and spacing, not a heavy border. Avoid cards and floating overlays.",
        "motion": "No scroll effects. The rail remains still on desktop; no sticky behavior on phone.",
        "phone": "Turn the rail into a normal compact masthead above a full-width image sequence. Repeat the order action after the gallery.",
    },
]


def render(design: dict[str, str]) -> str:
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
    try:
        index = int(STATE_FILE.read_text(encoding="utf-8").strip()) % len(DESIGNS)
    except (OSError, ValueError):
        index = 0

    design = DESIGNS[index]
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(render(design), encoding="utf-8")
    STATE_FILE.write_text(f"{(index + 1) % len(DESIGNS)}\n", encoding="utf-8")
    print(f"Selected design: {design['name']} -> {out}")


if __name__ == "__main__":
    main()
