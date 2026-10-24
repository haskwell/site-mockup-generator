# Instagram Site Mockup Generator

Scrapes Instagram profile data, creates a business summary, and uses `agy` to
build a static site under `WEBSITES_ROOT`.

## Setup

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
playwright install chromium
```

Install and authenticate `agy` separately. It must be available on `PATH` or
installed at `~/.local/bin/agy`; the dashboard checks both locations. Put
account handles or Instagram profile URLs, one per line, in
`config/accounts.txt`. Optional saved browser state belongs in
`config/auth.json`; Google Sheets credentials belong in `config/creds.json`.
Both are ignored by git.

## Build

```bash
python run.py [path/to/accounts.txt]
```

The default account list is `config/accounts.txt`. By default output goes to
`~/websites/YYYY-MM-DD/<handle>/site/`. Set `WEBSITES_ROOT` to choose another
root. `FORCE=1 python run.py` rebuilds existing sites and removes stale files
from the deployed site directory. A copy of the previous site is kept under
`<handle>/backups/` before a build or revision. Google Sheets updates happen
after a successful build and are non-fatal.

Run output, including scraper and summary messages, is written to a timestamped
session log in `logs/`; full `agy` output is also stored per account.

## Local dashboard

Start the local-only dashboard with `python app.py` and open
`http://127.0.0.1:8765`. It stores leads, outreach fields, live logs, and
revision history in `dashboard.sqlite3`. Select a batch date, paste or import
account handles, then run builds and review sites in the embedded preview.
Google Sheets sync is optional and runs after a successful build. The dashboard
does not bind to the network; keep the URL local because it can launch a
Playwright login window and run local build tools.

## Revise existing sites

`config/REVISIONS.md` uses one section per handle:

```markdown
# example_handle

Make the contact button more prominent.
```

Run `python revisions.py`, enter the output date (`YYYY-MM-DD`), and only
non-empty sections for configured accounts are applied. Successfully applied
sections are cleared; failed requests remain in the file. Existing notes are
preserved when `run.py` refreshes the list of account headings.

## Project layout

```text
config/                 Account list, revision requests, local credentials
prompts/GEMINI.md       Generation instructions
prompts/SKILL.md        Design guidance
src/                    Scraper, summary, design, and Sheets utility
pipeline_common.py      Shared settings, logger, process and account helpers
run.py                  Build workflow
revisions.py            Revision workflow
requirements.txt        Python dependencies
```
