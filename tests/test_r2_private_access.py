#!/usr/bin/env python3
"""Comprehensive test suite for R2 Private API-Based Access."""
import os
import shutil
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

REPO = Path(__file__).resolve().parents[1]
import sys
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from fastapi.testclient import TestClient
from src.server.app import app, init_db
import src.storage.r2 as r2_storage


class TestR2PrivateAccess(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        self.db_path = Path(self.temp_dir) / "test_dashboard.sqlite3"
        self.env_patcher = patch.dict(os.environ, {
            "R2_BUCKET_NAME": "test-mockups-bucket",
            "CLOUDFLARE_ACCOUNT_ID": "test-account",
            "R2_ACCESS_KEY_ID": "test-access",
            "R2_SECRET_ACCESS_KEY": "test-secret",
        })
        self.env_patcher.start()
        self.client = TestClient(app, headers={"Host": "127.0.0.1", "X-Studio": "1", "Content-Type": "application/json"})

    def tearDown(self):
        self.env_patcher.stop()
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_database_migration_http_to_preview(self):
        """Verify that init_db() migrates historical http% site_path links to /preview/..."""
        import sqlite3
        conn = sqlite3.connect(self.db_path)
        conn.execute("""CREATE TABLE leads(
            batch TEXT, handle TEXT, name TEXT DEFAULT '', phone TEXT DEFAULT '',
            area TEXT DEFAULT '', followers TEXT DEFAULT '', status TEXT DEFAULT 'queued',
            error TEXT DEFAULT '', site_path TEXT DEFAULT '', notes TEXT DEFAULT '',
            stage TEXT DEFAULT 'new', follow_up TEXT DEFAULT '', price TEXT DEFAULT '',
            qa TEXT DEFAULT '', created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT DEFAULT CURRENT_TIMESTAMP, locked_by TEXT DEFAULT '',
            locked_at TEXT DEFAULT '', PRIMARY KEY(batch, handle)
        )""")
        conn.execute(
            "INSERT INTO leads(batch, handle, site_path) VALUES (?, ?, ?)",
            ("2026-10-15", "testlead", "https://files.indicesai.net/2026-10-15/testlead/site/index.html")
        )
        conn.commit()
        conn.close()

        with patch("src.server.app.DB", self.db_path):
            with patch("src.server.app.connect") as mock_connect:
                import sqlite3
                conn = sqlite3.connect(self.db_path)
                mock_connect.return_value = conn
                init_db()

        conn = sqlite3.connect(self.db_path)
        row = conn.execute("SELECT site_path FROM leads WHERE handle='testlead'").fetchone()
        conn.close()
        self.assertEqual(row[0], "/preview/2026-10-15/testlead/index.html")

    def test_path_traversal_prevention(self):
        """Verify that ../ path traversal attempts in preview and media return 400."""
        from fastapi import HTTPException
        from src.server.app import preview, media

        # Direct handler checks
        with self.assertRaises(HTTPException) as cm:
            preview("2026-10-27", "handle1", "../secret.txt")
        self.assertEqual(cm.exception.status_code, 400)
        self.assertIn("Invalid path", cm.exception.detail)

        with self.assertRaises(HTTPException) as cm:
            media("2026-10-27", "handle1", "folder/../../secret.png")
        self.assertEqual(cm.exception.status_code, 400)
        self.assertIn("Invalid path", cm.exception.detail)

        # HTTP level check with encoded traversal
        resp = self.client.get("/preview/2026-10-27/handle1/%2e%2e/secret.txt")
        self.assertEqual(resp.status_code, 400)
        self.assertIn("Invalid path", resp.text)

    def test_preview_isolation_csp(self):
        """Verify that preview responses enforce CSP sandbox."""
        # Create a dummy local preview file
        websites_root = Path(self.temp_dir) / "websites"
        site_dir = websites_root / "testlead" / "site"
        site_dir.mkdir(parents=True, exist_ok=True)
        (site_dir / "index.html").write_text("<html><body>Hello</body></html>", encoding="utf-8")

        with patch("src.server.app.root_for", return_value=websites_root):
            with patch("src.server.app.is_r2_configured", return_value=False):
                resp = self.client.get("/preview/2026-10-27/testlead/index.html")
                self.assertEqual(resp.status_code, 200)
                self.assertIn("Content-Security-Policy", resp.headers)
                csp = resp.headers["Content-Security-Policy"]
                self.assertIn("sandbox", csp)
                self.assertIn("allow-scripts", csp)

    def test_preview_r2_fetch_no_redirect(self):
        """Verify that preview fetches from R2 directly via API without 302 redirect."""
        with patch("src.server.app.is_r2_configured", return_value=True):
            with patch("src.server.app.get_r2_mtime", return_value=123456789.0):
                with patch("src.server.app.get_r2_object", return_value=(b"<h1>R2 Site</h1>", "text/html")):
                    with patch("src.server.app.root_for", return_value=Path(self.temp_dir)):
                        resp = self.client.get("/preview/2026-10-27/testlead/index.html", follow_redirects=False)
                        self.assertEqual(resp.status_code, 200)
                        self.assertEqual(resp.content, b"<h1>R2 Site</h1>")
                        self.assertIn("text/html", resp.headers["content-type"])
                        self.assertIn("sandbox", resp.headers.get("content-security-policy", ""))

    def test_media_r2_fetch_no_redirect(self):
        """Verify that media fetches from R2 directly via API without 302 redirect."""
        with patch("src.server.app.is_r2_configured", return_value=True):
            with patch("src.server.app.get_r2_object", return_value=(b"fake_image_bytes", "image/jpeg")):
                with patch("src.server.app.root_for", return_value=Path(self.temp_dir)):
                    resp = self.client.get("/media/2026-10-27/testlead/photo1.jpg", follow_redirects=False)
                    self.assertEqual(resp.status_code, 200)
                    self.assertEqual(resp.content, b"fake_image_bytes")
                    self.assertEqual(resp.headers["content-type"], "image/jpeg")
                    self.assertIn("Cache-Control", resp.headers)

    def test_recording_presigned_redirect(self):
        """Verify that recording route redirects to presigned URL for valid screen sizes."""
        # Invalid screen size returns 400
        resp = self.client.get("/api/lead/testlead/recording/ultrawide")
        self.assertEqual(resp.status_code, 400)
        self.assertIn("Invalid screen size", resp.text)

        # Valid screen with presigned URL returns 302 redirect to signed URL
        with patch("src.server.app.is_r2_configured", return_value=True):
            with patch("src.server.app.list_recordings", return_value=["testlead-desktop.webm"]):
                with patch("src.server.app.get_presigned_recording_url", return_value="https://bucket.r2.cloudflarestorage.com/rec?X-Amz-Signature=123"):
                    with patch("src.server.app.root_for", return_value=Path(self.temp_dir)):
                        resp = self.client.get("/api/lead/testlead/recording/desktop", follow_redirects=False)
                        self.assertEqual(resp.status_code, 302)
                        self.assertEqual(resp.headers["location"], "https://bucket.r2.cloudflarestorage.com/rec?X-Amz-Signature=123")

    def test_has_r2_site_and_preview_url_verification(self):
        """Verify that get_preview_url with verify_exists=True returns None when site is missing in R2."""
        with patch("src.storage.r2.is_r2_configured", return_value=True):
            with patch("src.storage.r2.has_r2_site", return_value=False):
                url = r2_storage.get_preview_url("batch1", "lead1", verify_exists=True)
                self.assertIsNone(url)

            with patch("src.storage.r2.has_r2_site", return_value=True):
                url = r2_storage.get_preview_url("batch1", "lead1", verify_exists=True)
                self.assertEqual(url, "/preview/batch1/lead1/index.html")

    def test_get_lead_text_finds_site_design_md(self):
        """Verify that get_lead_text looks under site/DESIGN.md in R2."""
        with patch("src.storage.r2.is_r2_configured", return_value=True):
            mock_s3 = MagicMock()
            # Simulate site/DESIGN.md being found
            def mock_get_object(Bucket, Key):
                if Key == "2026-10-11/mylead/site/DESIGN.md":
                    mock_resp = MagicMock()
                    mock_resp.__getitem__.return_value.read.return_value = b"# Site Design Direction"
                    return mock_resp
                raise Exception("Not found")

            mock_s3.get_object.side_effect = mock_get_object
            with patch("src.storage.r2.get_s3_client", return_value=mock_s3):
                content = r2_storage.get_lead_text("2026-10-11", "mylead", "DESIGN.md")
                self.assertEqual(content, "# Site Design Direction")

    def test_preview_auto_syncs_newer_r2_to_local_disk(self):
        """Verify that preview() updates stale local disk files when R2 is newer."""
        websites_root = Path(self.temp_dir) / "websites_sync"
        site_dir = websites_root / "lead_sync" / "site"
        site_dir.mkdir(parents=True, exist_ok=True)
        local_index = site_dir / "index.html"
        local_index.write_text("<h1>v1.0</h1>", encoding="utf-8")
        os.utime(local_index, (1000.0, 1000.0))

        with patch("src.server.app.is_r2_configured", return_value=True):
            with patch("src.server.app.get_r2_mtime", return_value=2000.0):
                with patch("src.server.app.get_r2_object", return_value=(b"<h1>v1.1 from R2</h1>", "text/html")):
                    with patch("src.server.app.root_for", return_value=websites_root):
                        resp = self.client.get("/preview/2026-10-27/lead_sync/index.html")
                        self.assertEqual(resp.status_code, 200)
                        self.assertEqual(resp.content, b"<h1>v1.1 from R2</h1>")
                        # Local file should now be updated to v1.1
                        self.assertEqual(local_index.read_text(encoding="utf-8"), "<h1>v1.1 from R2</h1>")
                        self.assertEqual(local_index.stat().st_mtime, 2000.0)

    def test_revisions_pulls_newer_r2_version_before_revising(self):
        """Verify that revise() pulls latest files when R2 has a newer version."""
        from src.pipeline.revisions import revise
        websites_root = Path(self.temp_dir) / "websites_rev"
        account = websites_root / "lead_rev"
        site_dir = account / "site"
        site_dir.mkdir(parents=True, exist_ok=True)
        local_index = site_dir / "index.html"
        local_index.write_text("<h1>v1.0 (local)</h1>" + "x" * 2000, encoding="utf-8")
        os.utime(local_index, (1000.0, 1000.0))
        (account / "DESIGN.md").write_text("# Design", encoding="utf-8")

        mock_download_site = MagicMock()
        with patch("src.pipeline.revisions.is_r2_configured", return_value=True):
            with patch("src.pipeline.revisions.get_r2_mtime", return_value=3000.0):
                with patch("src.pipeline.revisions.download_site", mock_download_site):
                    with patch("src.pipeline.revisions.find_agy", return_value=None):
                        # agy is None so revise will exit right after downloading/preparing
                        logger = MagicMock()
                        revise("lead_rev", "Change background color", websites_root, {"lead_rev"}, logger)
                        mock_download_site.assert_called_once_with(websites_root.name, "lead_rev", site_dir)

    def test_has_recording_flag_and_state(self):
        """Verify has_recording column migration, state detection, and save_recording update."""
        import sqlite3
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        conn.execute("""CREATE TABLE leads(
            batch TEXT, handle TEXT, name TEXT DEFAULT '', phone TEXT DEFAULT '',
            area TEXT DEFAULT '', followers TEXT DEFAULT '', status TEXT DEFAULT 'queued',
            error TEXT DEFAULT '', site_path TEXT DEFAULT '', notes TEXT DEFAULT '',
            stage TEXT DEFAULT 'new', follow_up TEXT DEFAULT '', price TEXT DEFAULT '',
            qa TEXT DEFAULT '', created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT DEFAULT CURRENT_TIMESTAMP, locked_by TEXT DEFAULT '',
            locked_at TEXT DEFAULT '', PRIMARY KEY(batch, handle)
        )""")
        conn.execute(
            "INSERT INTO leads(batch, handle, stage) VALUES (?, ?, ?)",
            ("2026-10-27", "lead_with_stage", "recorded")
        )
        conn.execute(
            "INSERT INTO leads(batch, handle, stage) VALUES (?, ?, ?)",
            ("2026-10-27", "lead_disk_rec", "built")
        )
        conn.execute(
            "INSERT INTO leads(batch, handle, stage) VALUES (?, ?, ?)",
            ("2026-10-27", "lead_no_rec", "new")
        )
        conn.commit()
        conn.close()

        # Run init_db() to test ALTER TABLE migration adding has_recording
        with patch("src.server.app.DB", self.db_path):
            with patch("src.server.app.connect", side_effect=lambda: sqlite3.connect(self.db_path)):
                init_db()

        # Verify column exists
        conn = sqlite3.connect(self.db_path)
        cols = [r[1] for r in conn.execute("PRAGMA table_info(leads)").fetchall()]
        self.assertIn("has_recording", cols)
        conn.close()

        # Create mock websites directory with a recording file for lead_disk_rec
        websites_root = Path(self.temp_dir) / "sites"
        batch_dir = websites_root / "2026-10-27"
        rec_dir = batch_dir / "lead_disk_rec" / "recordings"
        rec_dir.mkdir(parents=True, exist_ok=True)
        (rec_dir / "lead_disk_rec-desktop.webm").write_bytes(b"dummy_video_bytes")

        # Query /api/state
        with patch("src.server.app.DB", self.db_path):
            def custom_connect():
                c = sqlite3.connect(self.db_path)
                c.row_factory = sqlite3.Row
                return c
            with patch("src.server.app.connect", side_effect=custom_connect):
                with patch("src.server.app.settings", return_value={"websites_root": str(websites_root)}):
                    with patch("src.server.app.root_for", return_value=batch_dir):
                        resp = self.client.get("/api/state?batch=2026-10-27")
                        self.assertEqual(resp.status_code, 200)
                        leads = {l["handle"]: l for l in resp.json()["leads"]}
                        # lead_with_stage has stage='recorded' without a physical file, so has_recording=0 per bug 18
                        self.assertEqual(leads["lead_with_stage"]["has_recording"], 0)
                        # lead_disk_rec has video file in recordings/
                        self.assertEqual(leads["lead_disk_rec"]["has_recording"], 1)
                        # lead_no_rec has no recording
                        self.assertEqual(leads["lead_no_rec"]["has_recording"], 0)

    def test_save_recording_updates_has_recording_in_db(self):
        """Verify POST /api/lead/{handle}/recording updates has_recording to 1."""
        import sqlite3
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        conn.execute("""CREATE TABLE leads(
            batch TEXT, handle TEXT, name TEXT DEFAULT '', phone TEXT DEFAULT '',
            area TEXT DEFAULT '', followers TEXT DEFAULT '', status TEXT DEFAULT 'queued',
            error TEXT DEFAULT '', site_path TEXT DEFAULT '', notes TEXT DEFAULT '',
            stage TEXT DEFAULT 'new', follow_up TEXT DEFAULT '', price TEXT DEFAULT '',
            qa TEXT DEFAULT '', created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT DEFAULT CURRENT_TIMESTAMP, locked_by TEXT DEFAULT '',
            locked_at TEXT DEFAULT '', has_recording INTEGER DEFAULT 0,
            PRIMARY KEY(batch, handle)
        )""")
        conn.execute(
            "INSERT INTO leads(batch, handle, status, has_recording) VALUES (?, ?, 'done', 0)",
            ("2026-10-27", "testsave")
        )
        conn.commit()
        conn.close()

        websites_root = Path(self.temp_dir) / "sites"
        batch_dir = websites_root / "2026-10-27"
        account_dir = batch_dir / "testsave"
        site_dir = account_dir / "site"
        site_dir.mkdir(parents=True, exist_ok=True)
        (site_dir / "index.html").write_text("<h1>Site</h1>", encoding="utf-8")

        def custom_connect():
            c = sqlite3.connect(self.db_path)
            c.row_factory = sqlite3.Row
            return c

        with patch("src.server.app.DB", self.db_path):
            with patch("src.server.app.connect", side_effect=custom_connect):
                with patch("src.server.app.root_for", return_value=batch_dir):
                    with patch("src.server.app.is_r2_configured", return_value=False):
                        resp = self.client.post(
                            "/api/lead/testsave/recording?batch=2026-10-27&screen=desktop&extension=webm",
                            content=b"test_video_data_123"
                        )
                        self.assertEqual(resp.status_code, 200)
                        self.assertEqual(resp.json()["screen"], "desktop")

        conn = sqlite3.connect(self.db_path)
        row = conn.execute("SELECT has_recording FROM leads WHERE handle='testsave'").fetchone()
        conn.close()
        self.assertEqual(row[0], 1)

    def test_delete_recording_r2(self):
        """Verify delete_recording() removes objects from R2."""
        with patch("src.storage.r2.is_r2_configured", return_value=True):
            mock_s3 = MagicMock()
            mock_paginator = MagicMock()
            mock_paginator.paginate.return_value = [
                {
                    "Contents": [
                        {"Key": "2026-10-27/deltest/recordings/deltest-desktop.webm"},
                        {"Key": "2026-10-27/deltest/recordings/deltest-phone.webm"},
                    ]
                }
            ]
            mock_s3.get_paginator.return_value = mock_paginator
            with patch("src.storage.r2.get_s3_client", return_value=mock_s3):
                with patch.dict(os.environ, {"R2_BUCKET_NAME": "test-bucket"}):
                    # Delete phone only
                    deleted = r2_storage.delete_recording("2026-10-27", "deltest", screen="phone")
                    self.assertEqual(deleted, 1)
                    mock_s3.delete_objects.assert_called_with(
                        Bucket="test-bucket",
                        Delete={"Objects": [{"Key": "2026-10-27/deltest/recordings/deltest-phone.webm"}]}
                    )

                    # Delete all
                    deleted_all = r2_storage.delete_recording("2026-10-27", "deltest", screen="all")
                    self.assertEqual(deleted_all, 2)

    def test_delete_lead_recording_endpoint(self):
        """Verify DELETE /api/lead/{handle}/recording endpoint updates DB, files, and stage."""
        import sqlite3
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        conn.execute("""CREATE TABLE leads(
            batch TEXT, handle TEXT, name TEXT DEFAULT '', phone TEXT DEFAULT '',
            area TEXT DEFAULT '', followers TEXT DEFAULT '', status TEXT DEFAULT 'done',
            error TEXT DEFAULT '', site_path TEXT DEFAULT '', notes TEXT DEFAULT '',
            stage TEXT DEFAULT 'recorded', follow_up TEXT DEFAULT '', price TEXT DEFAULT '',
            qa TEXT DEFAULT 'available', created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT DEFAULT CURRENT_TIMESTAMP, locked_by TEXT DEFAULT '',
            locked_at TEXT DEFAULT '', has_recording INTEGER DEFAULT 1,
            PRIMARY KEY(batch, handle)
        )""")
        conn.execute(
            "INSERT INTO leads(batch, handle, site_path, stage, has_recording) VALUES (?, ?, ?, ?, ?)",
            ("2026-10-27", "multirec", "/preview/2026-10-27/multirec/index.html", "recorded", 1)
        )
        conn.commit()
        conn.close()

        websites_root = Path(self.temp_dir) / "sites"
        batch_dir = websites_root / "2026-10-27"
        account_dir = batch_dir / "multirec"
        rec_dir = account_dir / "recordings"
        site_dir = account_dir / "site"
        site_dir.mkdir(parents=True, exist_ok=True)
        (site_dir / "index.html").write_text("<h1>Site</h1>", encoding="utf-8")
        rec_dir.mkdir(parents=True, exist_ok=True)
        (rec_dir / "multirec-desktop.webm").write_bytes(b"desktop_bytes")
        (rec_dir / "multirec-phone.webm").write_bytes(b"phone_bytes")

        def custom_connect():
            c = sqlite3.connect(self.db_path)
            c.row_factory = sqlite3.Row
            return c

        with patch("src.server.app.DB", self.db_path):
            with patch("src.server.app.connect", side_effect=custom_connect):
                with patch("src.server.app.root_for", return_value=batch_dir):
                    with patch("src.server.app.is_r2_configured", return_value=False):
                        # 1. Test invalid screen
                        resp = self.client.delete("/api/lead/multirec/recording/tv?batch=2026-10-27")
                        self.assertEqual(resp.status_code, 400)

                        # 2. Delete phone recording
                        resp = self.client.delete("/api/lead/multirec/recording/phone?batch=2026-10-27")
                        self.assertEqual(resp.status_code, 200)
                        data = resp.json()
                        self.assertTrue(data["deleted"])
                        self.assertEqual(data["deleted_local"], 1)
                        self.assertEqual(data["has_recording"], 1)
                        self.assertIn("desktop", data["remaining"])
                        self.assertNotIn("phone", data["remaining"])
                        # File for desktop still exists, phone deleted
                        self.assertTrue((rec_dir / "multirec-desktop.webm").is_file())
                        self.assertFalse((rec_dir / "multirec-phone.webm").is_file())

                        # Check DB: has_recording should still be 1, stage still "recorded"
                        conn = sqlite3.connect(self.db_path)
                        row = conn.execute("SELECT has_recording, stage FROM leads WHERE handle='multirec'").fetchone()
                        conn.close()
                        self.assertEqual(row[0], 1)
                        self.assertEqual(row[1], "recorded")

                        # 3. Delete desktop recording (last remaining)
                        resp = self.client.delete("/api/lead/multirec/recording/desktop?batch=2026-10-27")
                        self.assertEqual(resp.status_code, 200)
                        data = resp.json()
                        self.assertTrue(data["deleted"])
                        self.assertEqual(data["has_recording"], 0)
                        self.assertEqual(len(data["remaining"]), 0)
                        self.assertEqual(data["stage"], "built")

                        # Check DB: has_recording is 0, stage reverted to "built"
                        conn = sqlite3.connect(self.db_path)
                        row = conn.execute("SELECT has_recording, stage FROM leads WHERE handle='multirec'").fetchone()
                        conn.close()
                        self.assertEqual(row[0], 0)
                        self.assertEqual(row[1], "built")

    def test_delete_desktop_does_not_delete_phone(self):
        """Verify deleting desktop recording leaves phone recording intact."""
        import sqlite3
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        conn.execute("""CREATE TABLE leads(
            batch TEXT, handle TEXT, name TEXT DEFAULT '', phone TEXT DEFAULT '',
            area TEXT DEFAULT '', followers TEXT DEFAULT '', status TEXT DEFAULT 'done',
            error TEXT DEFAULT '', site_path TEXT DEFAULT '', notes TEXT DEFAULT '',
            stage TEXT DEFAULT 'recorded', follow_up TEXT DEFAULT '', price TEXT DEFAULT '',
            qa TEXT DEFAULT 'available', created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT DEFAULT CURRENT_TIMESTAMP, locked_by TEXT DEFAULT '',
            locked_at TEXT DEFAULT '', has_recording INTEGER DEFAULT 1,
            PRIMARY KEY(batch, handle)
        )""")
        conn.execute(
            "INSERT INTO leads(batch, handle, site_path, stage, has_recording) VALUES (?, ?, ?, ?, ?)",
            ("2026-10-27", "twoscreens", "/preview/2026-10-27/twoscreens/index.html", "recorded", 1)
        )
        conn.commit()
        conn.close()

        websites_root = Path(self.temp_dir) / "sites"
        batch_dir = websites_root / "2026-10-27"
        account_dir = batch_dir / "twoscreens"
        rec_dir = account_dir / "recordings"
        rec_dir.mkdir(parents=True, exist_ok=True)
        (rec_dir / "twoscreens-desktop.webm").write_bytes(b"desktop_bytes")
        (rec_dir / "twoscreens-phone.webm").write_bytes(b"phone_bytes")

        def custom_connect():
            c = sqlite3.connect(self.db_path)
            c.row_factory = sqlite3.Row
            return c

        with patch("src.server.app.DB", self.db_path):
            with patch("src.server.app.connect", side_effect=custom_connect):
                with patch("src.server.app.root_for", return_value=batch_dir):
                    with patch("src.server.app.is_r2_configured", return_value=False):
                        # Delete desktop only
                        resp = self.client.delete("/api/lead/twoscreens/recording/desktop?batch=2026-10-27")
                        self.assertEqual(resp.status_code, 200)
                        data = resp.json()
                        self.assertTrue(data["deleted"])
                        self.assertEqual(data["deleted_local"], 1)
                        self.assertEqual(data["has_recording"], 1)
                        # Phone must remain!
                        self.assertIn("phone", data["remaining"])
                        self.assertNotIn("desktop", data["remaining"])
                        self.assertTrue((rec_dir / "twoscreens-phone.webm").is_file())
                        self.assertFalse((rec_dir / "twoscreens-desktop.webm").is_file())

                        # Check DB: has_recording is still 1
                        conn = sqlite3.connect(self.db_path)
                        row = conn.execute("SELECT has_recording, stage FROM leads WHERE handle='twoscreens'").fetchone()
                        conn.close()
                        self.assertEqual(row[0], 1)
                        self.assertEqual(row[1], "recorded")


if __name__ == "__main__":
    unittest.main()
