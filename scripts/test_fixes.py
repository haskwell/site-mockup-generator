#!/usr/bin/env python3
"""Automated test suite to verify codebase audit fixes directly against src/ modules."""
import datetime as dt
import json
import os
import shutil
import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

# Ensure repo root is on sys.path
REPO = Path(__file__).resolve().parents[1]
import sys
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from fastapi.testclient import TestClient
from src.app import app, clean_handle, export_leads, unlock_lead, resolve_credentials_path, resolve_websites_root
import src.r2_storage as r2_storage
from src.run import validate_site


class TestLoggingAndDecodings(unittest.TestCase):
    def test_imports_succeed(self):
        """Verify that all pipeline modules import without error."""
        import src.scraper
        import src.profile_summary
        import src.update_sheet
        import src.design
        self.assertIsNotNone(src.scraper.get_logger)
        self.assertIsNotNone(src.profile_summary.get_logger)
        self.assertIsNotNone(src.update_sheet.get_logger)
        self.assertIsNotNone(src.design.get_logger)

    def test_home_utf8_decoding(self):
        """Verify that home() reads web/index.html in UTF-8 without errors."""
        from src.app import home
        html = home()
        self.assertTrue(len(html) > 1000)
        self.assertIn("<!doctype html>", html.lower())


class TestLockTTLAndUnlock(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        self.db_path = Path(self.temp_dir) / "test.db"
        conn = sqlite3.connect(self.db_path)
        conn.execute("CREATE TABLE leads(batch TEXT, handle TEXT, name TEXT DEFAULT '', phone TEXT DEFAULT '', area TEXT DEFAULT '', followers TEXT DEFAULT '', status TEXT DEFAULT 'queued', error TEXT DEFAULT '', site_path TEXT DEFAULT '', notes TEXT DEFAULT '', stage TEXT DEFAULT 'new', follow_up TEXT DEFAULT '', price TEXT DEFAULT '', qa TEXT DEFAULT '', created_at TEXT DEFAULT CURRENT_TIMESTAMP, updated_at TEXT DEFAULT CURRENT_TIMESTAMP, locked_by TEXT DEFAULT '', locked_at TEXT DEFAULT '', PRIMARY KEY(batch, handle))")
        conn.commit()
        conn.close()

    def tearDown(self):
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_unlock_lead_endpoint(self):
        """Verify unlock_lead() in src.app clears locked_by and locked_at in the database."""
        conn = sqlite3.connect(self.db_path)
        conn.execute("INSERT INTO leads(batch, handle, locked_by, locked_at) VALUES('2026-10-11', 'locked_user', 'alice', '2026-10-26 12:00:00')")
        conn.commit()
        conn.close()

        def custom_connect():
            c = sqlite3.connect(self.db_path)
            c.row_factory = sqlite3.Row
            return c

        with patch("src.app.connect", side_effect=custom_connect):
            res = unlock_lead("locked_user", batch="2026-10-11")
            self.assertEqual(res, {"unlocked": True})

        conn = sqlite3.connect(self.db_path)
        row = conn.execute("SELECT locked_by, locked_at FROM leads WHERE batch='2026-10-11' AND handle='locked_user'").fetchone()
        self.assertEqual(row[0], "")
        self.assertEqual(row[1], "")
        conn.close()


class TestSqlite3RowRegression(unittest.TestCase):
    """Regression test ensuring sqlite3.Row objects are never accessed with .get()."""

    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        self.db_path = Path(self.temp_dir) / "test.db"
        conn = sqlite3.connect(self.db_path)
        conn.execute("CREATE TABLE leads(batch TEXT, handle TEXT, name TEXT DEFAULT '', phone TEXT DEFAULT '', area TEXT DEFAULT '', followers TEXT DEFAULT '', status TEXT DEFAULT 'queued', error TEXT DEFAULT '', site_path TEXT DEFAULT '', notes TEXT DEFAULT '', stage TEXT DEFAULT 'new', follow_up TEXT DEFAULT '', price TEXT DEFAULT '', qa TEXT DEFAULT '', created_at TEXT DEFAULT CURRENT_TIMESTAMP, updated_at TEXT DEFAULT CURRENT_TIMESTAMP, locked_by TEXT DEFAULT '', locked_at TEXT DEFAULT '', has_recording INTEGER DEFAULT 0, PRIMARY KEY(batch, handle))")
        conn.execute("INSERT INTO leads(batch, handle, status, site_path) VALUES('2026-10-11', 'rowuser', 'built', '/path/to/site')")
        conn.commit()
        conn.close()

    def tearDown(self):
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_sqlite3_row_has_no_get_method(self):
        """Confirm that real sqlite3.Row objects lack .get() and dict(row) must be used."""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        row = conn.execute("SELECT * FROM leads WHERE handle='rowuser'").fetchone()
        self.assertIsInstance(row, sqlite3.Row)
        with self.assertRaises(AttributeError):
            _ = row.get("site_path")
        row_dict = dict(row)
        self.assertEqual(row_dict.get("site_path"), "/path/to/site")
        conn.close()

    def test_save_recording_with_real_sqlite_row(self):
        """Test save_recording with real sqlite3.Row factory does not raise AttributeError."""
        from src.app import save_recording
        def custom_connect():
            c = sqlite3.connect(self.db_path)
            c.row_factory = sqlite3.Row
            return c

        mock_request = MagicMock()
        async def fake_body():
            return b"test video bytes"
        mock_request.body = fake_body

        import asyncio
        with patch("src.app.connect", side_effect=custom_connect):
            with patch("src.app.is_r2_configured", return_value=False):
                with patch("src.app.root_for", return_value=Path(self.temp_dir)):
                    res = asyncio.run(save_recording("rowuser", mock_request, batch="2026-10-11", screen="desktop"))
                    self.assertEqual(res["screen"], "desktop")


class TestCSVExportFormulaInjection(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        self.db_path = Path(self.temp_dir) / "test.db"
        conn = sqlite3.connect(self.db_path)
        conn.execute("CREATE TABLE leads(batch TEXT, handle TEXT, name TEXT, phone TEXT, area TEXT, followers TEXT, status TEXT, stage TEXT, notes TEXT, PRIMARY KEY(batch, handle))")
        conn.execute("INSERT INTO leads VALUES('2026-10-11', 'safe_lead', '=cmd|calc!A1', '+1234567890', '-500', '@mention', 'done', 'won', 'note')")
        conn.commit()
        conn.close()

    def tearDown(self):
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_formula_injection_cells_prefixed(self):
        """Verify export_leads prefixes cells starting with = + - @ with a single quote."""
        def custom_connect():
            c = sqlite3.connect(self.db_path)
            c.row_factory = sqlite3.Row
            return c

        with patch("src.app.connect", side_effect=custom_connect):
            resp = export_leads("2026-10-11")
            content = resp.body.decode("utf-8")
            self.assertIn("'=cmd|calc!A1", content)
            self.assertIn("'+1234567890", content)
            self.assertIn("'-500", content)
            self.assertIn("'@mention", content)


class TestSecurityMiddleware(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(app)

    def test_dns_rebinding_rejected(self):
        """Requests with unauthorized Host header must be rejected."""
        resp = self.client.get("/api/health", headers={"Host": "attacker.com"})
        self.assertEqual(resp.status_code, 403)

    def test_state_changing_without_x_studio_rejected(self):
        """POST/PUT/DELETE requests without X-Studio header must be rejected."""
        resp = self.client.post("/api/cancel", headers={"Host": "127.0.0.1", "Content-Type": "application/json"})
        self.assertEqual(resp.status_code, 403)

    def test_state_changing_without_json_content_type_rejected(self):
        """POST/PUT/DELETE requests with non-JSON Content-Type must be rejected."""
        resp = self.client.post("/api/cancel", headers={"Host": "127.0.0.1", "X-Studio": "1", "Content-Type": "text/plain"})
        self.assertEqual(resp.status_code, 415)


class TestSiteValidation(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        self.site_dir = Path(self.temp_dir) / "site"
        self.site_dir.mkdir()

    def tearDown(self):
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_shortcut_icon_checked(self):
        """validate_site should detect missing files referenced by rel='shortcut icon'."""
        html = "<!doctype html><html><head><link rel='shortcut icon' href='favicon.ico'></head><body>" + ("<!-- padding -->" * 60) + "</body></html>"
        (self.site_dir / "index.html").write_text(html, encoding="utf-8")
        errors = validate_site(self.site_dir)
        self.assertTrue(any("favicon.ico" in e for e in errors))

    def test_css_url_checked(self):
        """validate_site should detect missing files referenced by CSS url()."""
        html = "<!doctype html><html><head><link rel='stylesheet' href='style.css'></head><body>" + ("<!-- padding -->" * 60) + "</body></html>"
        (self.site_dir / "index.html").write_text(html, encoding="utf-8")
        (self.site_dir / "style.css").write_text("body { background: url('missing_bg.webp'); }", encoding="utf-8")
        errors = validate_site(self.site_dir)
        self.assertTrue(any("missing_bg.webp" in e for e in errors))


if __name__ == "__main__":
    unittest.main()
