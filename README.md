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

Start the dashboard desktop application with `python main.py` (or headless server with `python main.py --server`) and open `http://127.0.0.1:8765`.

- **Pipeline & Stages**: Track leads across sales outreach stages: `new`, `built`, `recorded`, `sent`, `replied`, `won`, and `lost`.
- **Photo Selection**: Filter and select which scraped Instagram post photos should be incorporated into the website mockup before building.
- **Revisions & Undo**: Queue prompt revisions against any mockup. Each revision creates a timestamped site backup under `<handle>/backups/`. Revisions can be undone with one click, restoring the previous snapshot and syncing to R2.
- **Walkthrough Recordings**: Record animated site walkthroughs across desktop, tablet, and mobile viewport frames using region capture. Videos can be replayed in the built-in cinema player or downloaded directly.
- **ZIP & CSV Export**: Export individual site mockups or full lead asset folders as ZIP archives. Export lead tables to CSV with built-in protection against spreadsheet formula injection.
- **Team Concurrency & Atomic Locking**: Leads are locked conditionally upon queueing so multiple teammates do not overwrite each other's active work. Stale locks (>15 minutes) expire automatically.

## Launchers & Setup

- **Desktop Launcher**: Run `python main.py` for a dedicated desktop window launcher.
- **Server Only**: Run `python main.py --server` to start only the background FastAPI server without launching a browser window.
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

## Important Notes & Security

- **Pakistan-Tuned Extraction**: Contact extraction in [src/profile_summary.py](src/profile_summary.py) includes specialized pattern recognition for Pakistani phone formats (`03xx`, `+923xx`, `00923xx`) and major Pakistani cities (Lahore, Karachi, Islamabad, Rawalpindi, Faisalabad, etc.).
- **Local-Only Warning**: The dashboard server has **no authentication** and runs build tools with broad local permissions. **Do not bind the dashboard to `0.0.0.0` or expose it over the public internet.** It is strictly designed for local loopback use (`127.0.0.1` / `localhost`). Incoming requests with non-loopback Host headers are rejected to protect against DNS rebinding, and state-changing endpoints require custom anti-CSRF headers.
- **Untrusted Input**: Instagram biographies, scraped profile text, and client revision instructions are untrusted inputs. Automated builds run with `--dangerously-skip-permissions` inside the local repository workspace.

## Project Layout

```text
├── assets/                     Icons and branding graphics
├── config/                     Account lists and local credentials
├── logs/                       Application and server logs
├── prompts/
│   ├── GEMINI.md               Generation instructions for agy
│   └── SKILL.md                Craft and design guidance rules
├── scripts/
│   ├── migrate_to_d1.py        SQLite -> Cloudflare D1 migration script
│   └── migrate_to_r2.py        Local websites -> Cloudflare R2 migration script
├── src/
│   ├── core/                   Infrastructure, logging, and desktop launcher
│   │   ├── common.py           Process helpers, constants, and utilities
│   │   ├── launcher.py         Desktop Chromium window and server lifecycle manager
│   │   └── logging.py          Consistently formatted console and event logger
│   ├── pipeline/               Site build, revision, scraping, and design pipeline
│   │   ├── builder.py          Site build orchestration and HTML/CSS validation
│   │   ├── design.py           Visual theme and palette generation
│   │   ├── revisions.py        Mockup revision processing engine
│   │   ├── scraper.py          Playwright Instagram profile scraper
│   │   ├── sheets.py           Google Sheets lead synchronization
│   │   └── summary.py          Profile bio, contact, and city extraction
│   ├── server/                 FastAPI dashboard backend
│   │   └── app.py              API endpoints, SSE streams, and worker queues
│   └── storage/                Database and cloud asset management
│       ├── credentials.py      Secrets and environment credential manager
│       ├── d1.py               Cloudflare D1 HTTP client and SQLite adapter
│       └── r2.py               Cloudflare R2 / S3 storage and asset synchronization
├── tests/
│   ├── __init__.py             Test package marker
│   ├── test_fixes.py           Audit fixes test suite
│   └── test_r2_private_access.py R2 private access test suite
├── web/
│   ├── index.html              Single-page studio dashboard interface
│   ├── script.js               Dashboard frontend interaction logic
│   └── styles.css              Dashboard stylesheets
├── build_exe.bat               Windows standalone executable build script
├── main.py                     Unified desktop launcher and subprocess entrypoint
├── requirements.txt            Python dependencies
└── studio.spec                 PyInstaller packaging specification
```
