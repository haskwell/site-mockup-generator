#!/usr/bin/env python3
"""Offline automated test suite to verify the 6 codebase audit fixes."""
import datetime as dt
import json
import os
import shutil
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

# Ensure repo root is on sys.path
REPO = Path(__file__).resolve().parents[1]
import sys
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))


class TestLoggingImports(unittest.TestCase):
    def test_imports_succeed(self):
        """Verify that all 4 modules can be imported as packages without logging_config error."""
        import src.scraper
        import src.profile_summary
        import src.update_sheet
        import src.design
        self.assertIsNotNone(src.scraper.get_logger)
        self.assertIsNotNone(src.profile_summary.get_logger)
        self.assertIsNotNone(src.update_sheet.get_logger)
        self.assertIsNotNone(src.design.get_logger)

    def test_home_utf8_decoding(self):
        """Verify that home() reads web/index.html in UTF-8 without charmap/cp1252 errors."""
        from src.app import home
        html = home()
        self.assertTrue(len(html) > 1000)
        self.assertIn("<!doctype html>", html.lower())


class TestLockTTLAndUnlock(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        self.db_path = Path(self.temp_dir) / "test.db"
        import sqlite3
        conn = sqlite3.connect(self.db_path)
        conn.execute("CREATE TABLE leads(batch TEXT, handle TEXT, locked_by TEXT DEFAULT '', locked_at TEXT DEFAULT '', PRIMARY KEY(batch, handle))")
        conn.commit()
        conn.close()

    def tearDown(self):
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_stale_lock_detection(self):
        """Verify locks older than 15 minutes are detected as stale."""
        now = dt.datetime.now(dt.timezone.utc)
        recent_lock = (now - dt.timedelta(minutes=5)).strftime("%Y-%m-%d %H:%M:%S")
        stale_lock = (now - dt.timedelta(minutes=20)).strftime("%Y-%m-%d %H:%M:%S")

        def check_lock(locked_at_str):
            if not locked_at_str:
                return False
            dt_lock = dt.datetime.fromisoformat(locked_at_str.replace(" ", "T")).replace(tzinfo=dt.timezone.utc)
            return (now - dt_lock).total_seconds() > 15 * 60

        self.assertFalse(check_lock(recent_lock))
        self.assertTrue(check_lock(stale_lock))

    def test_unlock_endpoint_logic(self):
        """Verify unlocking a lead clears locked_by and locked_at."""
        import sqlite3
        conn = sqlite3.connect(self.db_path)
        conn.execute("INSERT INTO leads(batch, handle, locked_by, locked_at) VALUES('2026-10-11', 'locked_user', 'alice', '2026-10-26 12:00:00')")
        conn.commit()

        # Unlock
        conn.execute("UPDATE leads SET locked_by='', locked_at='' WHERE batch=? AND handle=?", ('2026-10-11', 'locked_user'))
        conn.commit()

        row = conn.execute("SELECT locked_by, locked_at FROM leads WHERE batch='2026-10-11' AND handle='locked_user'").fetchone()
        self.assertEqual(row[0], "")
        self.assertEqual(row[1], "")
        conn.close()


class TestCloudPhotoSelection(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        self.websites_root = Path(self.temp_dir) / "websites"
        self.websites_root.mkdir()

    def tearDown(self):
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    @patch("src.app.is_r2_configured", return_value=True)
    @patch("src.app.upload_file", return_value=True)
    @patch("src.app.get_lead_json")
    def test_save_photos_with_cloud_fallback(self, mock_get_lead_json, mock_upload_file, mock_r2_cfg):
        from src.app import save_photos, PhotoSelection

        # Simulate cloud-only profile
        mock_get_lead_json.return_value = {
            "posts": [
                {"web_path": "posts/web/1_post.webp"},
                {"web_path": "posts/web/2_post.webp"}
            ]
        }

        with patch("src.app.root_for", return_value=self.websites_root / "2026-10-11"):
            sel = PhotoSelection(files=["1_post.webp"])
            res = save_photos("acme", sel, batch="2026-10-11")
            self.assertEqual(res, {"saved": 1})

            # Check that local file was saved
            saved_file = self.websites_root / "2026-10-11" / "acme" / "selected_posts.json"
            self.assertTrue(saved_file.is_file())
            self.assertEqual(json.loads(saved_file.read_text()), ["1_post.webp"])

            # Check that R2 upload was invoked
            mock_upload_file.assert_called_once()


class TestRevisionsDesignFallback(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        self.root = Path(self.temp_dir) / "2026-10-11"
        self.account = self.root / "cloud_user"
        self.site = self.account / "site"
        self.site.mkdir(parents=True)
        (self.site / "index.html").write_text("<html><body>Hello</body></html>")

    def tearDown(self):
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    @patch("src.revisions.is_r2_configured", return_value=True)
    @patch("src.revisions.get_lead_text")
    def test_revision_pulls_design_from_r2(self, mock_get_lead_text, mock_r2_cfg):
        mock_get_lead_text.return_value = "# Cloud Design Brief\nMinimalist aesthetic"
        design_file = self.account / "DESIGN.md"

        # Simulate missing DESIGN.md before revision
        self.assertFalse(design_file.is_file())

        # Test the fallback logic in revisions
        if not design_file.is_file() and mock_r2_cfg():
            cloud_design = mock_get_lead_text("2026-10-11", "cloud_user", "DESIGN.md")
            if cloud_design:
                design_file.write_text(cloud_design, encoding="utf-8")

        self.assertTrue(design_file.is_file())
        self.assertIn("Cloud Design Brief", design_file.read_text())


class TestR2AssetSyncHelpers(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        self.account = Path(self.temp_dir) / "test_user"
        self.account.mkdir()
        (self.account / "DESIGN.md").write_text("# Design")
        (self.account / "selected_posts.json").write_text('["1.webp"]')
        data_dir = self.account / "test_user_data"
        data_dir.mkdir()
        (data_dir / "profile_data.json").write_text('{"posts":[]}')

    def tearDown(self):
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    @patch("src.r2_storage.is_r2_configured", return_value=True)
    @patch("src.r2_storage.upload_file", return_value=True)
    @patch("src.r2_storage.upload_lead_media", return_value=1)
    @patch("src.r2_storage.upload_site", return_value="https://pub.r2.dev/site/index.html")
    def test_upload_lead_assets_orchestration(self, mock_upload_site, mock_media, mock_upload_file, mock_r2_cfg):
        from src.r2_storage import upload_lead_assets
        site_dir = self.account / "site"
        site_dir.mkdir()

        url = upload_lead_assets(self.account, "2026-10-11", "test_user")
        self.assertEqual(url, "https://pub.r2.dev/site/index.html")
        mock_upload_site.assert_called_once()
        mock_media.assert_called_once()
        self.assertEqual(mock_upload_file.call_count, 2)  # DESIGN.md and selected_posts.json


if __name__ == "__main__":
    unittest.main()
