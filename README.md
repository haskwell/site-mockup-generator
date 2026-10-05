# Instagram Site Mockup Generator

Scrapes each Instagram account, creates a compact business summary JSON, and
uses `agy` to build a static site mockup under `WEBSITES_ROOT`.

Each account gets one design direction from the menu in `prompts/DESIGN.md`,
assigned by its position in the accounts file (so neighbouring accounts always
differ). Only the shared guardrails and that one direction are copied into the
account folder. The single `agy` call curates 5 to 8 photos and builds a
website, not a mirror of the Instagram profile. Force a direction while
testing with `ARCHETYPE="Colour Blocks" FORCE=1 ./run.sh`.

## Run

```bash
./run.sh
```

Pass an alternate account list with `./run.sh path/to/accounts.txt`. The default
list is `config/accounts.txt`. Use `FORCE=1` to rebuild existing sites (reuses
scraped data and rebuilds with the same assigned direction).

## Project layout

```text
config/                 Account list
prompts/GEMINI.md       Shared content and design instructions copied per account
prompts/DESIGN.md       Shared guardrails + design directions (one is copied per account)
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
