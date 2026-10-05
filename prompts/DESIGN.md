# DESIGN DIRECTIONS

This file holds the shared guardrails and the design direction assigned to this business. Build that direction. If more than one direction appears below, choose the single best fit from the profile and photos and build only that one; do not blend them.

## Shared guardrails

- **A direction is a structure, not a color scheme.** It fixes the opening composition, section sequence, image scale, alignment, and signature move. Palette, fonts, and tone come from this business's own photos and bio. If the direction feels awkward for the business, keep its structure and adapt it; never fall back to a centered hero followed by a photo grid.
- **Size images by role and by resolution.** Check `posts[].width` and `posts[].height`. An image whose long side is about 900px or more may run full-width on mobile and large on desktop. Smaller images stay under about 600 CSS px and get their scale from the color field and type around them. Never apply one cap to everything, and never show equal-size tiles.
- **Three different section layouts at minimum.** If two sections look alike, change one.
- **Fonts and color.** Up to two font families. Palette of 4 to 6 colors sampled from the photos. The background need not be light, and the accent need not be warm.
- **Few photos.** With fewer than 5 usable photos, use them all and give each room. Do not pad.
- **Contact.** An order or contact action is visible in the first viewport and repeated after the work. Where a layout keeps contact persistent on desktop, bring it back after the work on mobile.
- **Mobile.** Design for 390px first. Body text at least 16px, tap targets at least 44px, no horizontal scrolling, hover never required.
- **Facts.** Wording comes only from `profile_data.json`, as `GEMINI.md` describes. Never write the reasoning behind the design into the page.

## Cover Photograph

**Best fit:** One photo has a strong, clear subject that can carry the first screen.

**Composition:** The first screen is split. The chosen photo fills roughly 60% of the width on desktop and the top 55svh on mobile. Beside or below it, on a solid color picked from that photo, sit the business name set large, the descriptor line, and the order button. Below the cover, the work runs as alternating wide and narrow rows, each row led by one large photo and a plain type label. No grid.

**Signature move:** The color pulled from the cover photo carries through the page as section backgrounds and rules.

**Sections:** Cover, work rows, about, how to order, footer.

**Mobile:** Photo, name, and order button all visible together in the first view. Never place text over a busy part of the photo.

## Oversized Wordmark

**Best fit:** A short or distinctive business name, and bold, high-contrast photos.

**Composition:** The business name is set enormous, left-aligned, broken across lines on purpose, on a single strong color field that fills the first viewport. One photo overlaps the edge of that field as an offset interruption. After it comes a loose sequence of three or four images at different widths, hanging alternately from the left and right edges. The bio sits in a short block of large text.

**Signature move:** The name as the graphic anchor, and the photo breaking out of the color field.

**Sections:** Wordmark field with order action, interrupting photo, loose image sequence, about, how to order, footer.

**Mobile:** Scale the name so it wraps cleanly without clipping. The photo comes right after the headline, never as a small remnant.

## Lookbook Spreads

**Best fit:** Six or more strong photos with varied orientations or related subjects.

**Composition:** The work is a sequence of unequal spreads. Each has a leading image at about 65% width, a smaller supporting image at about 30% offset vertically, and generous negative space. The dominant side alternates from spread to spread. The header is a quiet small wordmark with the descriptor and a short order link.

**Signature move:** The alternating scale and offset of the paired images.

**Sections:** Quiet masthead, spreads, about, ordering details as a closing note, footer.

**Mobile:** Each spread becomes a vertical pair, with the dominant photo first and the smaller one offset below. Keep the difference in scale.

## Studio Sidecar

**Best fit:** A concise identity where the photos should stay the main event while contact stays easy to find.

**Composition:** At 1024px and wider, a fixed rail takes about 30% of the width on the left, on a contrasting background. It holds the wordmark, descriptor, bio, order button, and Instagram link. The right side is a freely composed work area of mixed-width images grouped under plain type labels, not boxed cards.

**Signature move:** The rail's type, background, and alignment make the identity unmistakable.

**Sections:** Rail and work area together, ordering details after the work, footer.

**Mobile:** The rail collapses into a compact masthead with the order action. Repeat that action after the work.

## Editorial Feature

**Best fit:** A refined, personal, or story-led account, or a bio with a short phrase that stands well on its own.

**Composition:** A magazine-style opening: an oversized, left-aligned headline (the business name, or a short phrase from the bio if it works alone), a narrow offset text column, and a small wordmark. Images run down one off-center column, alternating between full-column and narrower placements, with large gaps between them.

**Signature move:** The off-center column and the oversized headline against the narrow text.

**Sections:** Editorial headline and bio, first image with generous separation, offset image sequence, order details, footer.

**Mobile:** Keep the headline large and left-aligned, the bio in a narrow readable measure, and the images alternating in width and offset.

## Tactile Cut-and-Paste

**Best fit:** Colorful, playful, handmade, or market-stall photos.

**Composition:** A restrained paper collage. The business name sits on a cut-paper label, with two or three photos as cutouts at slight angles (3 degrees at most) with straight or torn-looking edges made from CSS. Use one accent color. The collage gesture appears in the opening and once more in the work section, then the layout breathes. Not every image gets a frame, tape, or shadow.

**Signature move:** The cut-paper name label and the cutout photos.

**Sections:** Collage opening with order action, separated image groups, plain ordering details, footer.

**Mobile:** One staggered column with little overlap, so no photo is covered. Keep the signature gesture, not every desktop overlap.

## Colour Blocks

**Best fit:** Photos that fall into two to four visible types (for example cakes, cupcakes, boxes) or distinct color families.

**Composition:** Every type gets its own full-width band. Each band's background is a color sampled from that type's photos. Inside it, a large plain type label and one to three large images at different scales. The bands change direction: image left, image right, stacked. The opening is a band too, holding the name and order button. The last band is the darkest and holds contact and the footer.

**Signature move:** The sequence of full-width color bands, each belonging to its own photos.

**Sections:** Opening band, one band per visible type, about band, order and contact band.

**Mobile:** Bands stack edge to edge and keep their individual colors. If the photos do not separate into types, group them by color instead and do not invent labels.
