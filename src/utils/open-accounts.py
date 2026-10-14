
#!/usr/bin/env python3

from pathlib import Path
import subprocess
import shutil

ACCOUNTS_FILE = Path("config/accounts.txt")

# Find Zen Browser executable
BROWSER = shutil.which("zen") or shutil.which("zen-browser")

if not BROWSER:
    print("Error: Zen Browser not found (looked for 'zen' and 'zen-browser').")
    raise SystemExit(1)

if not ACCOUNTS_FILE.is_file():
    print(f"Error: File not found: {ACCOUNTS_FILE}")
    raise SystemExit(1)

with ACCOUNTS_FILE.open("r", encoding="utf-8") as f:
    accounts = [
        line.strip()
        for line in f
        if line.strip() and not line.strip().startswith("#")
    ]

for account in accounts:
    if account.startswith(("https://", "http://")):
        url = account
    else:
        username = account.lstrip("@")
        url = f"https://www.instagram.com/{username}/"

    print(f"Opening: {url}")
    subprocess.Popen([BROWSER, url])

print(f"Done. Opened {len(accounts)} account(s).")
