# Instagram account → small business website mockup

Unattended. Write `site/index.html` and `site/style.css` (add `site/script.js` only if needed), then finish. Don't run commands, browsers, or screenshots.

## Goal

A one-page site the owner would believe is real and would say "that's us, and it looks incredible" about. A stranger should want what this business offers within the first viewport. This is a sales demo, so aim for real peaks, not tasteful and forgettable.

Priority order when instructions conflict: the accuracy rules below, then `DESIGN.md`, then this file, then `SKILL.md`. Use `SKILL.md` for craft (execution quality, polish, detail), not for choosing a different direction. Where it pushes toward restraint, ambition wins, but never at the expense of `DESIGN.md`.

## Inputs

- `DESIGN.md` is the fixed design direction for this site (see Design direction).
- `<username>_data/profile_data.json` is the only source of facts.
- Images are in `site/assets/` as `post_<n>.webp` (maybe `pfp.jpg`); don't move or convert them. `posts[].width/height` give pixel sizes. Look at a few first.
- Static HTML/CSS, no frameworks. Google Fonts via `<link>` is fine. Modern CSS and inline SVG are welcome.

## Design direction

`DESIGN.md` lists fixed design constraints for this site. They are binding: follow every line. They win over your own taste and over any default in `SKILL.md`. Do not substitute a direction of your own.

Work out what this business makes or does and let its materials, textures, and vocabulary shape how you fit into those constraints: palette sampled from the photos, one signature motif drawn from the trade. A candle maker, a hair stylist, and a bakery should never look alike, even under similar constraints.

Anything `DESIGN.md` doesn't list is yours to decide. Make those choices deliberately to suit the direction instead of falling back on common patterns, and keep them consistent with the listed constraints.

If a constraint clashes badly with this business, adapt only that one axis and name it in your final summary. Don't drop constraints because they feel risky or hard.

Some axes in `DESIGN.md` concern text (copy voice, headline style). Because visible text is limited by the accuracy rules, they apply only to the descriptor line, headline treatment of the business name, and functional labels (buttons, nav). Never invent claims, copy, or facts to satisfy them.

The order or contact action should be a designed centerpiece and easy to reach on mobile. Whatever the direction, the site must work and read well on a phone.

When `SKILL.md` asks for a design plan or an anti-default review, build the plan inside the constraints in `DESIGN.md`. The review applies only to axes `DESIGN.md` leaves free; never revise a listed constraint because it resembles a common default. `SKILL.md`'s guidance on writing copy does not apply here; the accuracy rules govern all text.

## It must be a website, not a profile

- The business name is the headline, with one plain line saying what they do (from the bio or clearly visible in photos). Don't open with the bio.
- Several sections, each doing a different job with its own layout. Use 5 to 8 photos at varied scales. Same-size tile grids only if `DESIGN.md` explicitly calls for one.
- Leave out Instagram tells: counts, round avatar, story circles, play markers, follow buttons, caption cards, `@handle` as a heading, Instagram colors. The handle appears only in the footer and contact link (`https://www.instagram.com/<handle>/`).

## Accuracy (hard rules)

- Keep the bio's wording; drop decorative emoji and hashtags. Use captions only if evergreen and verbatim.
- Never use `alt_text` as visible copy. Write alt text only for what you can see.
- Don't invent prices, products, services, menus, reviews, credentials, years, addresses, policies, or stats. Include ordering, payment, and location details only if explicit in the bio.
- Link to WhatsApp (`https://wa.me/<digits>`) only if a number is explicitly for orders or WhatsApp; otherwise link to Instagram.
- No marketing claims unless they're in the bio. Visible text is limited to the bio, verbatim captions, the descriptor line, and plain functional labels.
- Some posts may be graphics containing text (a menu, price list, ordering rules). If one clearly looks evergreen, you may use its text verbatim as a source of facts, equal to the bio. Skip anything dated, promotional, or unclear, and don't use that graphic as a photo in the gallery.

## Mobile quality check

- Review the layout at narrow phone widths, including around 320–390 CSS pixels.
- Make sure there is no horizontal page overflow and every section fits within the viewport.
- Check that navigation, logos, headings, cards, and order/contact actions stay visible and usable.
- Make hover effects optional enhancements: provide an equivalent tap or focus interaction where the action matters.
- Keep body text readable and check text/background contrast.
- Avoid fixed-width elements and fixed or sticky controls that can be clipped on small screens.
- Before finishing, recheck the narrow layout after the final CSS changes.

## Finish

Before finishing, check two things:

1. Describe your first viewport in one sentence. If it would fit any other business in the same trade, redo it.
2. Walk through every line of `DESIGN.md` and confirm the site follows it. Fix any miss.

Then print six lines only: concept, palette, fonts, defining move, axes adapted from `DESIGN.md` (or "none"), anything omitted for lack of data.
