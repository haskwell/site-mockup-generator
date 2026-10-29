# Instagram Site Mockup Generator

Scrapes Instagram profile data, extracts business information, and uses `agy` to build bespoke, responsive static websites under `WEBSITES_ROOT`.

## Setup

1. **Environment and dependencies**:
   ```bash
   python3 -m venv .venv
   source .venv/bin/activate  # On Windows: .venv\Scripts\activate
   python -m pip install -r requirements.txt
   playwright install chromium
   ```

2. **Configuration (`.env`)**:
   Copy `.env.example` to `.env`:
   ```bash
   cp .env.example .env
   ```

3. **`agy` CLI**:
   Install and authenticate `agy` separately. It must be accessible on your system `PATH` or at `~/.local/bin/agy`. The generator invokes `agy` to design and revise site mockups.

4. **Accounts and Credentials**:
   - Accounts: Put Instagram handles or profile URLs (one per line) in [config/accounts.txt](config/accounts.txt).
   - Saved Instagram session (optional): [config/auth.json](config/auth.json) (can be generated directly from the dashboard login tool).
   - Google Sheets credentials (optional): Service account JSON at [config/creds.json](config/creds.json).

## Storage Modes: Local vs. Cloud

- **Local mode (default)**: When Cloudflare variables in `.env` are left blank, Studio runs fully local and offline. Lead data and revisions are saved to [dashboard.sqlite3](dashboard.sqlite3), and website mockups are stored under `WEBSITES_ROOT`.
- **Cloud mode (Cloudflare D1 + R2)**: For multi-user teams, specify Cloudflare D1 and R2 variables in `.env`:
  - `CLOUDFLARE_ACCOUNT_ID`, `CLOUDFLARE_API_TOKEN`, `D1_DATABASE_ID`
  - `R2_ACCESS_KEY_ID`, `R2_SECRET_ACCESS_KEY`, `R2_BUCKET_NAME`
  - `TEAM_MEMBER_NAME` (optional; defaults to OS user)
  If Cloudflare D1 is unreachable at startup, the dashboard automatically falls back to local SQLite and presents an offline status banner.

## Dashboard Features

Start the dashboard with `python app.py` and open `http://127.0.0.1:8765`.

- **Pipeline & Stages**: Track leads across sales outreach stages: `new`, `built`, `recorded`, `sent`, `replied`, `won`, and `lost`.
- **Photo Selection**: Filter and select which scraped Instagram post photos should be incorporated into the website mockup before building.
- **Revisions & Undo**: Queue prompt revisions against any mockup. Each revision creates a timestamped site backup under `<handle>/backups/`. Revisions can be undone with one click, restoring the previous snapshot and syncing to R2.
- **Walkthrough Recordings**: Record animated site walkthroughs across desktop, tablet, and mobile viewport frames using region capture. Videos can be replayed in the built-in cinema player or downloaded directly.
- **ZIP & CSV Export**: Export individual site mockups or full lead asset folders as ZIP archives. Export lead tables to CSV with built-in protection against spreadsheet formula injection.
- **Team Concurrency & Atomic Locking**: Leads are locked conditionally upon queueing so multiple teammates do not overwrite each other's active work. Stale locks (>15 minutes) expire automatically.

## Launchers & Setup

- **Desktop Launcher**: Run `python launch.py` for a dedicated desktop window launcher with system tray integration.
- **Windows Shortcuts**: Run `launch-setup.bat` (or [launch-setup.ps1](launch-setup.ps1)) to generate desktop launch shortcuts pointing to your project directory.
- **Batch Command**: On Windows, double-click `launch.bat` to launch the dashboard server.

## Migration Scripts

- **Migrate to Cloudflare D1**:
  ```bash
  python scripts/migrate_to_d1.py [path/to/dashboard.sqlite3]
  ```
  Exports local SQLite lead records, revisions, logs, and settings into Cloudflare D1.

- **Migrate to Cloudflare R2**:
  ```bash
  python scripts/migrate_to_r2.py [websites_root] --update-db
  ```
  Uploads local site mockups and media assets to Cloudflare R2 and updates database records with private preview links.

## Running Tests

Execute the automated test suite with Python's built-in `unittest`:
```bash
python -m unittest discover -s tests
```
Or run individual test modules:
```bash
python -m unittest tests/test_fixes.py
python -m unittest tests/test_r2_private_access.py
```

## CLI Usage

### Build Batch
```bash
python run.py [path/to/accounts.txt]
```
Outputs sites to `<WEBSITES_ROOT>/YYYY-MM-DD/<handle>/site/index.html`. Set `WEBSITES_ROOT` in `.env` or settings (default: `~/websites`). Set `FORCE=1` to force rebuilds of previously built leads.

### Revise Sites via CLI
Add revision instructions under handle headers in [config/REVISIONS.md](config/REVISIONS.md):
```markdown
# example_handle
Make the contact button larger and fix hero text alignment.
```
Then run:
```bash
python revisions.py
```

## Important Notes & Security

- **Pakistan-Tuned Extraction**: Contact extraction in [src/profile_summary.py](src/profile_summary.py) includes specialized pattern recognition for Pakistani phone formats (`03xx`, `+923xx`, `00923xx`) and major Pakistani cities (Lahore, Karachi, Islamabad, Rawalpindi, Faisalabad, etc.).
- **Local-Only Warning**: The dashboard server has **no authentication** and runs build tools with broad local permissions. **Do not bind the dashboard to `0.0.0.0` or expose it over the public internet.** It is strictly designed for local loopback use (`127.0.0.1` / `localhost`). Incoming requests with non-loopback Host headers are rejected to protect against DNS rebinding, and state-changing endpoints require custom anti-CSRF headers.
- **Untrusted Input**: Instagram biographies, scraped profile text, and client revision instructions are untrusted inputs. Automated builds run with `--dangerously-skip-permissions` inside the local repository workspace.

## Project Layout

```text
├── assets/                     Icons and branding graphics
├── config/                     Account lists, revision requests, local credentials
├── logs/                       Timestamped CLI and session build logs
├── prompts/
│   ├── GEMINI.md               Generation instructions for agy
│   └── SKILL.md                Craft and design guidance rules
├── scripts/
│   ├── migrate_to_d1.py        SQLite -> Cloudflare D1 migration script
│   ├── migrate_to_r2.py        Local websites -> Cloudflare R2 migration script
│   ├── open_accounts.py        Bulk Instagram profile browser opener
│   └── open_all.py             Batch website index browser opener
├── src/
│   ├── app.py                  FastAPI local dashboard server and API endpoints
│   ├── credentials_manager.py  Secrets and credentials manager
│   ├── d1_client.py            Cloudflare D1 HTTP client with SQLite fallback
│   ├── design.py               Visual theme and palette generation
│   ├── logging_config.py       Structured logging configuration
│   ├── pipeline_common.py      Shared constants, CLI helpers, process runners
│   ├── profile_summary.py      Business bio, phone, and city extraction
│   ├── r2_storage.py           Cloudflare R2 storage client and asset sync
│   ├── revisions.py            Revision processing workflow
│   ├── run.py                  Main CLI pipeline and site HTML/CSS validation
│   ├── scraper.py              Playwright Instagram profile scraper
│   └── update_sheet.py         Google Sheets sync with serial race guard
├── tests/
│   ├── __init__.py             Test package marker
│   ├── test_fixes.py           Audit fixes test suite
│   └── test_r2_private_access.py R2 private access test suite
├── web/
│   ├── index.html              Single-page studio dashboard interface
│   ├── script.js               Dashboard frontend interaction logic
│   └── styles.css              Dashboard stylesheets
├── app.py                      Dashboard compatibility entrypoint
├── build_exe.bat               Windows standalone executable build script
├── entrypoint.py               Subprocess and executable dispatcher
├── launch.py                   Desktop dashboard launcher
├── requirements.txt            Python dependencies
├── revisions.py                CLI revision entrypoint
├── run.py                      CLI build command entrypoint
└── studio.spec                 PyInstaller packaging specification
```
