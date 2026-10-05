# Project: Instagram account → business website mockup

You are running unattended. Make decisions yourself, write the files, then finish.

## Goal

Build a one-page website mockup that the business owner would believe is their real site. It must read as a **website**, never as an Instagram profile in nicer clothes. Instagram is only the source of facts and photos.

Priorities, in order:

1. Build the design direction assigned in `DESIGN.md`. Its composition is the page's identity.
2. Make it read as a website: sections with different jobs and a clear way to order.
3. Keep every fact accurate.
4. Make it work beautifully on a 390px phone.
5. Keep it lightweight: plain static HTML and CSS.

## Website, not profile

An Instagram profile is an avatar, a name, a bio, some counts, and a grid of equal pictures. A website has a headline, sections that each do a different job, and an obvious next step. Build the second thing.

- **Opening.** Headline is the business name. Under it, one plain line saying what they make, using words from the bio or things clearly visible in the photos (for example "Cakes and cupcakes"). Add a city only if the bio states one. Do not open with the bio.
- **Curate.** Use 5 to 8 photos in total: the sharpest, best lit, most varied ones. Leave the rest unused. Never show every scraped post and never lay photos out as a grid of same-size tiles.
- **Give each photo a role.** Lead image, supporting image, or detail, each at a different scale.
- **Sections.** Include only what the data supports, each with its own layout:
  - Opening with the order action.
  - Work, grouped by what the photos visibly show. Use plain type labels such as "Cakes" or "Cupcakes" only for things you can clearly see. No flavors, sizes, or claims.
  - About, containing the bio.
  - How to order, only when the bio contains real ordering details.
  - Footer with the Instagram link.
- **Navigation.** A slim header with the wordmark and at most three anchor links. On mobile, add a sticky bottom bar with one order button (WhatsApp if a number exists, otherwise Instagram).
- **Leave out the Instagram tells:** follower count, post/like/comment counts, round avatar, story-style circles, reel play markers, "follow" buttons, caption cards, an `@handle` as a heading, and Instagram colors or gradients. The handle appears only in the footer and contact link.
- **Reels.** A post with `kind == "reel"` is only a cover image. Prefer non-reel photos; if you use one, treat it as a normal image.

## Scope

Static mockup, not a working store. No forms, cart, backend, booking logic, analytics, or elaborate JavaScript. Links may be simple but must be real: Instagram or WhatsApp when available.

Do not run shell commands, browsers, servers, linters, tests, or screenshots. Build `site/index.html` and `site/style.css` from the supplied data and assets, then finish.

## Inputs and output

- `<username>_data/profile_data.json` is the only source of business facts.
- Images are already in `site/assets/` as `post_<n>.webp`, and optionally `pfp.jpg`. Do not copy, move, or convert them.
- Look at 3 to 5 images first to understand products, palette, and mood. `posts[].width` and `posts[].height` give each file's pixel size.
- `DESIGN.md` holds shared guardrails and the assigned design direction. Build that direction in this same call.
- Fill in the existing `site/index.html` and `site/style.css`. Add `site/script.js` only if a tiny visual effect truly needs it.
- Plain HTML and CSS: no frameworks, build steps, or CDN scripts. Google Fonts via `<link>` are allowed. Use relative asset paths.

## Content accuracy

- **Bio:** keep the owner's wording. Fix line breaks. Decorative emoji and hashtag strings may be dropped.
- **Captions** are usually empty. Use one only if it is present, evergreen, and reproduced verbatim. Ignore stale dates, sales, closures, and order-resumption notices.
- **`posts[].alt_text`** is machine-generated and unreliable. Never use it as visible copy. Write short alt text only for what you can see.
- Do not invent prices, products, flavors, menus, reviews, testimonials, years in business, addresses, policies, or statistics.
- Include payment, location, policy, and ordering details only when they are explicitly in the bio, with faithful wording.
- If a phone number in the bio or an evergreen caption is explicitly for WhatsApp or orders, link to `https://wa.me/<international digits>` using the country the bio implies. Otherwise link to the Instagram profile. Never invent a number.
- Link to `https://www.instagram.com/<handle>/` in the footer.
- Do not write marketing claims ("handcrafted", "freshly baked", "made with love") unless they are in the bio. The only written content is the bio, verbatim captions, the descriptor line, and plain functional labels.

## Images

- Use the real supplied images. Respect aspect ratios by default; do not force squares.
- Scale by role and by source resolution. Do not display an image much wider than its file's pixel width, because it will blur. `DESIGN.md` explains how to size images.
- A deliberate crop is allowed when the direction calls for it. Use `object-fit` with an `object-position` that keeps the subject. Do not crop every image.
- Every `<img>` gets explicit `width` and `height` and short accurate alt text. Use `loading="lazy"` on everything except the first visible image.
- Use `pfp.jpg` only if it is clearly a logo rather than a photo, at 40 to 64px, never in a circle and never as a hero. Otherwise use a text wordmark.
- Do not apply a universal image-width cap.

### Optional decorative stock image

At most one remote stock image, and only when the direction needs a decorative backdrop or transition that the supplied photos and CSS cannot give. It must not suggest the business's products, people, premises, or work. It gets an empty alt (or is a CSS background), no caption, and text over it must stay readable. Use a reputable source with a direct, stable URL and honor its attribution requirements. If nothing suitable exists, omit it.

## Plan before you build

Before writing code, decide silently (do not write this into any file):

- **Palette:** 4 to 6 hex values sampled from this business's photos, not defaults.
- **Type:** at most two families with distinct roles and real fallback stacks.
- **Layout:** one sentence per section, plus alignment.

Then check the plan against these common generated-page defaults and change anything that matches without a reason: a cream background with a serif and a terracotta accent; near-black with one acid accent; identical rounded cards with the same soft shadow; gradient washes; a tracked all-caps label above every heading; middle-dot meta strings; arrows appended to links; one headline word in a different color or italic; fade-up animation on every section; emoji as icons; purple gradients.

## Visual execution

- Spend boldness in one place: the direction's defining move, visible in the first viewport. Keep the rest quiet and disciplined.
- Typography carries personality. Use scale, weight, and spacing deliberately.
- Structural devices (numbers, rules, borders, labels) must encode something real about the content. Number things only if they are truly a sequence.
- Motion is optional. If used, make it one subtle moment that serves the design, and respect `prefers-reduced-motion`.
- Text contrast must be readable everywhere, including over images.

## Mobile

Design for 390px first and keep it usable at 360px. Body text at least 16px, tap targets at least 44px, no horizontal scrolling, no hover dependence. Adapt the direction's composition rather than collapsing everything into one stacked template. Use `svh` or `dvh`, never `vh`, for full-height sections.

## Silent check before finishing

- Could the page be described as "a header and a grid of photos"? If so, rework it.
- Are there at least three sections with visibly different layouts?
- Does it use 5 to 8 photos, at varied scales, with none shown as a same-size tile grid?
- Is any Instagram tell left in (counts, avatar, play markers, `@handle` heading)?
- Is every visible fact traceable to `profile_data.json`?

## Finish

Do not verify or run anything. Print a five-line summary only: direction used (exact heading from `DESIGN.md`), palette, fonts, the defining design move, and anything omitted because the source data did not support it.
