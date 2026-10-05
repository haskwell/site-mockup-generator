# Project: Instagram account → website mockup

You are running unattended. Make decisions yourself, write the files, then finish.

## Purpose

Create a polished sales mockup that makes this business look like a real, distinctive brand. This is a visual design task, not a generic landing-page exercise. Give the selected design direction a strong, visible presence in the finished page.

Priority order:

1. Choose one direction from the `DESIGN.md` menu and follow its specific composition.
2. Make the result feel professionally art-directed and suited to the business.
3. Make the layout work beautifully on a phone.
4. Keep the facts accurate and the page lightweight.

`DESIGN.md` is a menu of distinct design directions, not a preselected theme. After reviewing the profile and 3–5 photos, choose exactly one direction that fits this business and implement its hero, image arrangement, alignment, section rhythm, and visual character. Do not rotate by account order, blend directions, or replace the chosen composition with a familiar default hero or generic portfolio template. The rules in this file control factual accuracy, responsiveness, and output constraints; they do not override the selected visual direction.

## Scope

This is a static mockup, not a working store. No forms, cart, backend, booking logic, analytics, or elaborate JavaScript. Links may be simple, but use real Instagram or WhatsApp destinations when available.

Do not run shell commands, browsers, servers, linters, tests, or screenshots. Build `site/index.html` and `site/style.css` from the supplied data and assets, then finish.

## Inputs and output

- `<username>_data/profile_data.json` is the only source of business facts.
- Images are already in `site/assets/` as `post_<post_number>.webp` and optionally `pfp.jpg`. Do not copy, move, or convert them.
- Look at 3–5 images to understand the products, palette, and mood.
- `DESIGN.md` contains several alternatives. Choose the best fit based on the actual profile and visible image content, then build that design in this same call; do not make another model call.
- Fill in the existing `site/index.html` and `site/style.css`. Add `site/script.js` only if a tiny visual effect truly needs it.
- Use plain HTML and CSS, no frameworks, build steps, or CDN scripts. Google Fonts via `<link>` are allowed. Use relative asset paths.

## Content accuracy

- Use the bio in the owner's own words, fixing line breaks only.
- Captions are usually empty. Use a caption only if it is present, evergreen, and reproduced verbatim. Ignore stale dates, sales, closures, and order-resumption announcements.
- `posts[].alt_text` is machine-generated and unreliable. Never use it as visible copy. Write brief image alt text only when it can be accurately inferred from the image.
- Do not display likes, comments, following count, or post count. Follower count may appear once, quietly.
- Do not invent prices, products, flavors, menus, reviews, testimonials, years in business, address, policies, or statistics.
- Include payment, location, policies, and ordering details only when explicitly present in the bio, and keep their wording faithful.
- If a phone number in the bio or an evergreen caption is explicitly for WhatsApp/orders, link to `https://wa.me/<international digits>` using the country implied by the bio. Otherwise link to the Instagram profile. Never invent a number.
- Link to `https://www.instagram.com/<handle>/` in the header or footer.
- A post with `kind == "reel"` is a cover image, not a playable video. Add a small play marker and link it to that post's URL.

## Image handling

- Use the real supplied post images. Respect their aspect ratios by default; don't force the gallery into uniform squares.
- Follow `DESIGN.md` for image scale and placement. Full-bleed, edge-to-edge, paired, grid, portrait, or single-column arrangements are all valid when the selected direction calls for them.
- A deliberate hero crop is allowed when the direction requires it. Preserve the subject's focal area; do not apply that crop treatment to every gallery image.
- Provide `loading="lazy"`, explicit `width` and `height`, and concise accurate alt text on images.
- Use `pfp.jpg` only as a small logo (about 40–64px), near the wordmark or in the footer. Never enlarge it into a hero. If missing, use a text wordmark.
- Do not apply a universal image-width cap that defeats an intentionally full-bleed composition.

### Optional decorative stock image

- A remote stock image is optional, not a default requirement. Use at most one per mockup, and only when the selected design has a specific decorative need that supplied Instagram photos or a CSS treatment cannot serve.
- Appropriate uses are a full-bleed cover/hero backdrop, a restrained atmospheric image behind or around typography, or a deliberate image-based transition between sections.
- Do not use stock imagery to pad the post gallery, imply the business's products, people, premises, ingredients, methods, or location, or add generic lifestyle scenes. The supplied Instagram images remain the business's actual work.
- Choose a reputable source that permits the intended display and provides a direct, stable image URL. Link the image remotely; do not download or copy it into `site/assets/`.
- Treat the image as decoration only: no caption, credit presented as business copy, or factual claim. Use an empty alt attribute or CSS background when decorative, and preserve text contrast.
- Remote images require an internet connection and may stop working if the source changes or removes the URL. If no suitable, clearly decorative image is available, omit it.

## Visual execution

- Make the selected direction obvious in the first viewport and carry its defining visual move through the page.
- Match type, color, scale, spacing, and image treatment to that direction and to the actual profile imagery. A warm-neutral palette, serif headline, single accent, asymmetry, or generous whitespace can be useful choices, but none is mandatory unless the selected direction calls for it.
- Strong color fields, dark backgrounds, close-set grids, centered layouts, full-bleed imagery, borders, frames, and overlapping elements may be used when they are intentional parts of the selected direction. Do not add them merely as decoration.
- Avoid familiar AI-generated tropes: purple gradients, emoji used as icons, generic centered heroes or feature-card rows, and arbitrary decorative animations.
- Keep text contrast readable. Motion must serve the chosen design, stay subtle, and respect `prefers-reduced-motion`.

## Page content

Include the business identity and bio, supplied post images, an appropriate order/contact path, and a clear Instagram link. A distinct “How to order” section is useful when the profile contains actual ordering details, but do not invent content to fill it. Do not add filler sections.

## Mobile

Design for a 390px-wide phone first and ensure it remains usable at 360px. Keep body text readable and tap targets comfortable. No horizontal page scrolling. Adapt the selected composition rather than collapsing every design into the same stacked template. Use `svh` or `dvh`, not `vh`, for full-height sections.

## Finish

Do not verify or run anything. Print a four-line summary only: palette, fonts, the defining design move, and anything omitted because the source data did not support it.
