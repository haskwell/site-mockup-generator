# Instagram Site Mockup Generator

Scrapes each Instagram account, creates a compact business summary JSON, and
uses `agy` to build a static site mockup under `WEBSITES_ROOT`.

The shared generation instructions and design skill are copied into each
account folder for the single `agy` call. A deterministic design direction is
generated as `DESIGN.md` and copied into the website directory before `agy`
runs. It curates 5 to 8 photos and builds a website, not a mirror of the
Instagram profile.

## Run

```bash
./run.sh
```

Pass an alternate account list with `./run.sh path/to/accounts.txt`. The default
list is `config/accounts.txt`. Use `FORCE=1` to rebuild existing sites (reuses
scraped data and rebuilds with the same assigned direction).

## Revise existing sites

After `run.sh` finishes, it clears `REVISIONS.md` and adds a heading for each
built or already-existing site. Add revision instructions under the relevant
headings, then run:

```bash
./revisions.sh
```

Running `run.sh` replaces all existing content in `REVISIONS.md`, so save any
revision requests you still need before starting a new run. Only sections with
non-blank instructions are sent to `agy`. The account names
must match entries in `config/accounts.txt`; blank sections are skipped. The
script runs `agy` from each account directory, where it can access the existing
`site/` and generation context. It does not scrape profiles or regenerate site
files before the revision. By default, both scripts use
`/home/frost/websites/YYYY-MM-DD`, creating a separate root for each day. Set
`WEBSITES_ROOT` to use a different directory. Each `run.sh` or `revisions.sh` invocation writes its terminal
output to a separate timestamped log in `logs/`, such as
`2026-10-06_14-32-10_run_12345.log` or
`2026-10-06_15-05-42_revisions_12346.log`. Python files run manually log to the
terminal only. The scripts also keep detailed `agy` output in per-account
`logs/` directories.

## Project layout

```text
config/                 Account list
REVISIONS.md            Per-site revision requests for revisions.sh
prompts/GEMINI.md       Shared project, content, and output instructions copied per account
prompts/SKILL.md        Shared design guidance copied per account
src/                    Scraper, summary, design, and sheet update utilities
run.sh                  Per-account workflow and site generation
revisions.sh            Apply non-empty revision sections with agy
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
