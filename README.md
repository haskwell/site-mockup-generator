# Instagram Site Mockup Generator

Scrapes each Instagram account, creates a compact business summary JSON, and
uses `agy` to build a static site mockup under `WEBSITES_ROOT`.

## Run

```bash
./run.sh
```

Pass an alternate account list with `./run.sh path/to/accounts.txt`. The default
list is `config/accounts.txt`. Use `FORCE=1 ./run.sh` to rebuild existing sites.

## Project layout

```text
config/                 Account list
prompts/GEMINI.md       Design instructions copied into each business folder
src/                    Scraper, summary, sheet update, and design generators
                        design.py writes a rotating DESIGN.md into each business folder
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
