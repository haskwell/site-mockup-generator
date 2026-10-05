# Instagram Site Mockup Generator

Scrapes each Instagram account, creates a compact business summary JSON, and
uses `agy` to build a static site mockup under `WEBSITES_ROOT`.

Each account's single `agy` call chooses one visual archetype from a curated
menu after inspecting the account profile and a few downloaded photos, then
builds the site in that direction. The archetype menu is a Markdown file copied
into each account folder; it does not add another model call. This replaces the
old sequential design rotation, so the selected layout can fit the actual
business and imagery.

## Run

```bash
./run.sh
```

Pass an alternate account list with `./run.sh path/to/accounts.txt`. The default
list is `config/accounts.txt`. Use `FORCE=1` to rebuild existing sites (reuses
scraped data and lets `agy` choose an archetype again).

## Project layout

```text
config/                 Account list
prompts/GEMINI.md       Shared content and design instructions copied per account
prompts/DESIGN.md       Curated archetype menu copied per account
src/                    Scraper, summary, and sheet update utilities
run.sh                  Per-account workflow and site generation
```

## Optional decorative imagery

Generated mockups use the business's Instagram photos as their actual product
and portfolio images. A design may use one remotely linked stock image only when
it needs a decorative hero, atmospheric backdrop, or image-based section
transition that the account photos or CSS cannot provide. Stock imagery must
not be presented as the business's products, people, premises, or work. Remote
images need an internet connection and may become unavailable if the source
changes or removes the image; any source attribution requirements must be
honored.
