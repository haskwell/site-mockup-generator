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

    def test_video_src_checked(self):
        """validate_site should detect missing files referenced directly by <video src='...'>."""
        html = "<!doctype html><html><head></head><body><video src='missing_clip.mp4'></video>" + ("<!-- padding -->" * 60) + "</body></html>"
        (self.site_dir / "index.html").write_text(html, encoding="utf-8")
        errors = validate_site(self.site_dir)
        self.assertTrue(any("missing_clip.mp4" in e for e in errors))


class TestHighImpactAndEdgeCases(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        self.db_path = Path(self.temp_dir) / "dashboard.sqlite3"
        self.client = TestClient(app, headers={"Host": "127.0.0.1", "X-Studio": "1", "Content-Type": "application/json"})

    def tearDown(self):
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_1_events_stream_returns_streaming_response_and_releases_lock(self):
        """Bug 1: /api/events must return a StreamingResponse and not hold event_lock while streaming."""
        import asyncio
        from fastapi.responses import StreamingResponse
        from src.app import stream, emit, event_lock, subscribers
        resp = stream(MagicMock())
        self.assertIsInstance(resp, StreamingResponse)
        self.assertEqual(resp.media_type, "text/event-stream")
        # event_lock must NOT be held while waiting for events, so emit() works without deadlocking
        self.assertFalse(event_lock.locked())
        with patch("src.app.connect", side_effect=Exception("skip db")):
            emit("testhandle", "log", "hello stream", "2026-10-27")
        gen = resp.body_iterator
        chunk = asyncio.run(gen.__anext__())
        self.assertIn("data: ", chunk)
        asyncio.run(gen.aclose())
        self.assertEqual(len(subscribers), 0)

    def test_2_rescrape_not_skipped_for_built_site(self):
        """Bug 2: process_account must not skip an already-built site when rescrape is True."""
        from src.run import process_account
        from src.pipeline_common import MIN_SIZE
        root = Path(self.temp_dir) / "2026-10-27"
        site = root / "acc1" / "site"
        site.mkdir(parents=True)
        (site / "index.html").write_text("x" * (MIN_SIZE + 100), encoding="utf-8")
        logger = MagicMock()
        # With force=False and rescrape=False, returns 2 (skipped)
        rc_skip = process_account("acc1", root, "python", False, logger, options={"rescrape": False})
        self.assertEqual(rc_skip, 2)
        # With force=False and rescrape=True, proceeds to scraper instead of returning 2
        with patch("src.run.run_streaming", return_value=(1, False)) as mock_run:
            rc_rescrape = process_account("acc1", root, "python", False, logger, options={"rescrape": True})
            self.assertEqual(rc_rescrape, 1)
            self.assertTrue(any("--force" in call.args[0] for call in mock_run.call_args_list))

    def test_3_offline_d1_changes_merged_back_on_restart(self):
        """Bug 3: Offline SQLite changes made in manual local mode are merged when manual sync is invoked."""
        from src.app import init_db
        from src.d1_client import set_local_mode, is_local_mode, sync_local_to_d1, D1Row, D1Cursor
        env = {
            "CLOUDFLARE_ACCOUNT_ID": "acc123",
            "CLOUDFLARE_API_TOKEN": "tok123",
            "D1_DATABASE_ID": "db123",
            "DASHBOARD_DB": str(self.db_path),
        }
        with patch.dict(os.environ, env):
            with patch("src.app.DB", self.db_path):
                # 1. Manually enable local mode
                set_local_mode(True)
                init_db()
                self.assertTrue(is_local_mode())

                # Make offline edits in local SQLite
                conn = sqlite3.connect(self.db_path)
                conn.execute(
                    "INSERT INTO leads(batch, handle, name, stage, updated_at) VALUES('2026-10-27', 'offline_lead', 'Offline Cafe', 'built', '2026-10-27 12:00:00')"
                )
                conn.execute(
                    "INSERT INTO revisions(batch, handle, request, status) VALUES('2026-10-27', 'offline_lead', 'Make header blue', 'pending')"
                )
                conn.commit()
                conn.close()

                # Turn off local mode
                set_local_mode(False)
                self.assertFalse(is_local_mode())

                # 2. Manual sync merges offline changes into D1
                d1_queries = []
                def fake_d1_query(sql, params=None):
                    d1_queries.append((sql, params))
                    return D1Cursor([])

                with patch("src.d1_client.D1Connection._query", side_effect=fake_d1_query):
                    from src.d1_client import D1Connection
                    d1 = D1Connection("acc123", "db123", "tok123")
                    sync_local_to_d1(self.db_path, d1)
                    self.assertTrue(
                        any("INSERT OR REPLACE INTO leads" in q[0] and "offline_lead" in (q[1] or []) for q in d1_queries)
                    )
                    self.assertTrue(
                        any("revisions" in q[0] and "Make header blue" in (q[1] or []) for q in d1_queries)
                    )

    def test_4_failed_revision_missing_index_restores_backup_and_records_path(self):
        """Bug 4: If agy exits 0 but removes site/index.html, backup is restored and recorded for Undo."""
        from src.app import revision_worker
        from src.pipeline_common import MIN_SIZE
        batch_dir = Path(self.temp_dir) / "2026-10-27"
        account = batch_dir / "revlead"
        site_dir = account / "site"
        site_dir.mkdir(parents=True)
        original_html = "<!doctype html><html><head></head><body>" + ("x" * MIN_SIZE) + "</body></html>"
        (site_dir / "index.html").write_text(original_html, encoding="utf-8")
        (account / "DESIGN.md").write_text("# Design", encoding="utf-8")

        conn = sqlite3.connect(self.db_path)
        conn.execute("CREATE TABLE revisions(id INTEGER PRIMARY KEY AUTOINCREMENT, batch TEXT, handle TEXT, request TEXT, status TEXT DEFAULT 'pending', created_at TEXT DEFAULT CURRENT_TIMESTAMP, applied_at TEXT, backup_path TEXT DEFAULT '')")
        rid = conn.execute("INSERT INTO revisions(batch, handle, request) VALUES('2026-10-27', 'revlead', 'Break index')").lastrowid
        conn.commit()
        conn.close()

        def custom_connect():
            c = sqlite3.connect(self.db_path)
            c.row_factory = sqlite3.Row
            return c

        def remove_index_and_exit_0(*args, **kwargs):
            (site_dir / "index.html").unlink()
            return 0, False

        with patch("src.app.connect", side_effect=custom_connect), \
             patch("src.app.root_for", return_value=batch_dir), \
             patch("src.app.settings", return_value={"model": "m", "timeout": 30}), \
             patch("src.app.emit"), \
             patch("src.revisions.is_r2_configured", return_value=False), \
             patch("src.revisions.find_agy", return_value="/usr/bin/agy"), \
             patch("src.revisions.run_streaming", side_effect=remove_index_and_exit_0):
            revision_worker("revlead", "2026-10-27", rid, "Break index")

        # Site index.html must be restored from backup
        self.assertTrue((site_dir / "index.html").is_file())
        self.assertEqual((site_dir / "index.html").read_text(encoding="utf-8"), original_html)
        # Revision row must be marked failed AND have backup_path recorded
        conn = sqlite3.connect(self.db_path)
        row = conn.execute("SELECT status, backup_path FROM revisions WHERE id=?", (rid,)).fetchone()
        conn.close()
        self.assertEqual(row[0], "failed")
        self.assertTrue(bool(row[1]) and Path(row[1]).is_dir())

    def test_5_cloud_exports_prefer_newer_r2_and_fail_on_partial_download(self):
        """Bug 5: zip_site prefers newer R2 files, and download_lead_folder returns False on mid-stream error."""
        import zipfile
        batch_dir = Path(self.temp_dir) / "2026-10-27"
        site_dir = batch_dir / "ziplead" / "site"
        site_dir.mkdir(parents=True)
        local_index = site_dir / "index.html"
        local_index.write_text("stale local", encoding="utf-8")
        os.utime(local_index, (1000.0, 1000.0))

        def fake_download_site(batch, handle, dest):
            (dest / "index.html").write_text("fresh from R2", encoding="utf-8")
            return True

        with patch("src.app.root_for", return_value=batch_dir), \
             patch("src.app.is_r2_configured", return_value=True), \
             patch("src.app.get_r2_mtime", return_value=2000.0), \
             patch("src.app.download_site", side_effect=fake_download_site):
            resp = self.client.get("/api/lead/ziplead/zip?batch=2026-10-27&mode=site")
            self.assertEqual(resp.status_code, 200)
            import io
            with zipfile.ZipFile(io.BytesIO(resp.content)) as zf:
                self.assertEqual(zf.read("index.html").decode("utf-8"), "fresh from R2")

        # Partial download error after first object in download_lead_folder must return False
        mock_s3 = MagicMock()
        mock_paginator = MagicMock()
        mock_paginator.paginate.return_value = [{
            "Contents": [
                {"Key": "2026-10-27/ziplead/file1.txt"},
                {"Key": "2026-10-27/ziplead/file2.txt"},
            ]
        }]
        mock_s3.get_paginator.return_value = mock_paginator
        def fail_on_second(Bucket, Key):
            if Key.endswith("file2.txt"):
                raise RuntimeError("network drop")
            m = MagicMock()
            m.__getitem__.return_value.read.return_value = b"first"
            return m
        mock_s3.get_object.side_effect = fail_on_second
        with patch("src.r2_storage.is_r2_configured", return_value=True), \
             patch("src.r2_storage.get_s3_client", return_value=mock_s3), \
             patch.dict(os.environ, {"R2_BUCKET_NAME": "b"}):
            dest = Path(self.temp_dir) / "dl_dest"
            self.assertFalse(r2_storage.download_lead_folder("2026-10-27", "ziplead", dest))

    def test_6_d1_migration_includes_has_recording_and_logs(self):
        """Bug 6: scripts/migrate_to_d1.py creates has_recording and migrates logs rows."""
        import scripts.migrate_to_d1 as migrate_to_d1
        conn = sqlite3.connect(self.db_path)
        conn.executescript("""
            CREATE TABLE leads(batch TEXT, handle TEXT, has_recording INTEGER DEFAULT 1, PRIMARY KEY(batch, handle));
            CREATE TABLE settings(key TEXT PRIMARY KEY, value TEXT);
            CREATE TABLE revisions(id INTEGER PRIMARY KEY, batch TEXT, handle TEXT, request TEXT, status TEXT, created_at TEXT, applied_at TEXT, backup_path TEXT);
            CREATE TABLE logs(id INTEGER PRIMARY KEY, batch TEXT, handle TEXT, status TEXT, line TEXT, created_at TEXT);
            INSERT INTO leads(batch, handle, has_recording) VALUES('2026-10-27', 'mlead', 1);
            INSERT INTO logs(id, batch, handle, status, line, created_at) VALUES(1, '2026-10-27', 'mlead', 'done', 'Built site', '2026-10-27 10:00:00');
        """)
        conn.commit()
        conn.close()

        d1_dest = Path(self.temp_dir) / "d1_simulated.sqlite3"
        d1_conn = sqlite3.connect(d1_dest)
        d1_conn.row_factory = sqlite3.Row
        with patch("scripts.migrate_to_d1.is_d1_configured", return_value=True), \
             patch("scripts.migrate_to_d1.get_db_connection", return_value=d1_conn):
            rc = migrate_to_d1.main(self.db_path)
            self.assertEqual(rc, 0)

        lead_row = d1_conn.execute("SELECT handle, has_recording FROM leads WHERE handle='mlead'").fetchone()
        log_row = d1_conn.execute("SELECT handle, status, line FROM logs WHERE handle='mlead'").fetchone()
        d1_conn.close()
        self.assertEqual(lead_row["has_recording"], 1)
        self.assertEqual(log_row["line"], "Built site")

    def test_7_cancel_immediately_after_queue_run_sets_token(self):
        """Bug 7: queue_run attaches cancellation Event before starting worker thread."""
        import threading
        import time
        import src.app as app_mod
        started_event = threading.Event()
        observed_cancelled = []

        def fake_worker(handles, batch, force, rescrape, scrape_only, jid, token=None):
            started_event.wait(timeout=2)
            observed_cancelled.append(token.is_set() if token else False)
            with app_mod.job_lock:
                app_mod.active_job = None

        with patch("src.app.run_worker", side_effect=fake_worker):
            res = app_mod.queue_run(["testuser"], "2026-10-27", False, False, False)
            self.assertIn("job_id", res)
            # Cancel before worker thread proceeds
            cancel_res = app_mod.cancel()
            self.assertTrue(cancel_res["cancelled"])
            started_event.set()
        # Wait briefly for daemon thread to finish
        for _ in range(20):
            if observed_cancelled:
                break
            time.sleep(0.02)
        self.assertEqual(observed_cancelled, [True])

    def test_8_and_12_frontend_recording_and_settings_validation(self):
        """Bugs 8 & 12: Verify web/index.html only advances stage inside upload try-block and validates numeric settings."""
        html = (REPO / "web" / "index.html").read_text(encoding="utf-8")
        # Bug 8: setStage("recorded") is inside the try block before catch (e)
        rec_idx = html.find('/recording?${qs}')
        set_stage_idx = html.find('setStage("recorded")', rec_idx)
        catch_idx = html.find('toast(`Download saved; server upload failed:', rec_idx)
        self.assertTrue(rec_idx < set_stage_idx < catch_idx)

        # Bug 12: backend rejects 0 or empty numeric settings
        def custom_connect():
            c = sqlite3.connect(self.db_path)
            c.row_factory = sqlite3.Row
            c.execute("CREATE TABLE IF NOT EXISTS settings(key TEXT PRIMARY KEY, value TEXT)")
            return c
        with patch("src.app.connect", side_effect=custom_connect):
            resp = self.client.put("/api/settings", json={"values": {"timeout": 0}})
            self.assertEqual(resp.status_code, 400)
            resp2 = self.client.put("/api/settings", json={"values": {"attempts": ""}})
            self.assertEqual(resp2.status_code, 400)
            resp3 = self.client.put("/api/settings", json={"values": {"timeout": 120, "attempts": 3, "max_posts": 12, "parallelism": 2}})
            self.assertEqual(resp3.status_code, 200)
            self.assertEqual(resp3.json()["timeout"], 120)

    def test_9_r2_media_upload_raises_on_error(self):
        """Bug 9: upload_lead_media does not swallow per-file S3 upload exceptions."""
        account_dir = Path(self.temp_dir) / "acc_media"
        data_dir = account_dir / "acc_media_data"
        data_dir.mkdir(parents=True)
        (data_dir / "profile_data.json").write_text("{}", encoding="utf-8")
        mock_s3 = MagicMock()
        mock_s3.put_object.side_effect = RuntimeError("S3 put failed")
        with patch("src.r2_storage.is_r2_configured", return_value=True), \
             patch("src.r2_storage.get_s3_client", return_value=mock_s3), \
             patch.dict(os.environ, {"R2_BUCKET_NAME": "b"}):
            with self.assertRaises(RuntimeError):
                r2_storage.upload_lead_media(account_dir, "2026-10-27", "acc_media")

    def test_10_r2_recording_deletion_failure_returns_502(self):
        """Bug 10: R2 recording deletion errors are not swallowed and return 502 from API."""
        mock_s3 = MagicMock()
        mock_s3.get_paginator.side_effect = RuntimeError("R2 unavailable")
        with patch("src.r2_storage.is_r2_configured", return_value=True), \
             patch("src.r2_storage.get_s3_client", return_value=mock_s3), \
             patch.dict(os.environ, {"R2_BUCKET_NAME": "b"}):
            with self.assertRaises(RuntimeError):
                r2_storage.delete_recording("2026-10-27", "lead1", screen="desktop")

        with patch("src.app.is_r2_configured", return_value=True), \
             patch("src.app.root_for", return_value=Path(self.temp_dir)), \
             patch("src.app.delete_recording", side_effect=RuntimeError("R2 delete failed")):
            resp = self.client.delete("/api/lead/lead1/recording/desktop?batch=2026-10-27")
            self.assertEqual(resp.status_code, 502)

    def test_11_revisions_cli_appends_date_to_websites_root(self):
        """Bug 11: src/revisions.py main() resolves WEBSITES_ROOT/<date>."""
        import src.revisions as revisions_mod
        ws_root = Path(self.temp_dir) / "custom_websites"
        dated_dir = ws_root / "2026-10-27"
        dated_dir.mkdir(parents=True)
        cfg_dir = Path(self.temp_dir) / "config"
        cfg_dir.mkdir(parents=True)
        (cfg_dir / "REVISIONS.md").write_text("# user1\nfix hero\n", encoding="utf-8")
        (cfg_dir / "accounts.txt").write_text("user1\n", encoding="utf-8")

        with patch.dict(os.environ, {"WEBSITES_ROOT": str(ws_root)}), \
             patch("src.revisions.REPO", Path(self.temp_dir)), \
             patch("builtins.input", return_value="2026-10-27"), \
             patch("src.revisions.revise", return_value=0) as mock_revise:
            rc = revisions_mod.main()
            self.assertEqual(rc, 0)
            self.assertEqual(mock_revise.call_args.args[2], dated_dir.resolve())

    def test_13_concurrent_update_sheet_no_duplicate_serials(self):
        """Bug 13: Concurrent update_sheet calls serialize and assign unique serial numbers."""
        from concurrent.futures import ThreadPoolExecutor
        import time
        from src.update_sheet import update_sheet

        creds = Path(self.temp_dir) / "creds.json"
        creds.write_text("{}", encoding="utf-8")
        sheet_rows = [["S.No", "Name", "Instagram", "Phone", "Area", "Followers"]]

        class FakeWorksheet:
            def get(self, rng):
                time.sleep(0.02)
                return [list(r) for r in sheet_rows]
            def col_values(self, col):
                time.sleep(0.02)
                return [str(r[0]) for r in sheet_rows]
            def append_row(self, row, value_input_option="RAW"):
                time.sleep(0.02)
                sheet_rows.append([str(x) for x in row])

        fake_ws = FakeWorksheet()
        mock_client = MagicMock()
        mock_client.open.return_value.sheet1 = fake_ws

        with patch("google.oauth2.service_account.Credentials.from_service_account_file"), \
             patch("gspread.authorize", return_value=mock_client):
            with ThreadPoolExecutor(max_workers=4) as pool:
                futs = [
                    pool.submit(update_sheet, {"handle": f"user_{i}", "name": f"User {i}"}, creds)
                    for i in range(4)
                ]
                results = [f.result() for f in futs]

        serials = sorted(s for _, s in results)
        self.assertEqual(serials, [1, 2, 3, 4])

    def test_14_launch_respects_custom_port(self):
        """Bug 14: launch.py uses PORT environment variable for probing and opening browser."""
        import launch
        with patch.dict(os.environ, {"PORT": "9876"}):
            self.assertEqual(launch._current_url(), "http://127.0.0.1:9876")
            self.assertEqual(launch._current_state_url(), "http://127.0.0.1:9876/api/state")

    def test_15_preview_and_media_use_no_cache(self):
        """Lower-priority issue: preview and media return no-cache headers so refreshed assets aren't stale."""
        websites_root = Path(self.temp_dir) / "ws_cache"
        site_dir = websites_root / "lead1" / "site"
        site_dir.mkdir(parents=True)
        (site_dir / "style.css").write_text("body { color: red; }", encoding="utf-8")
        data_dir = websites_root / "lead1" / "lead1_data"
        data_dir.mkdir(parents=True)
        (data_dir / "pfp.jpg").write_bytes(b"imgbytes")

        with patch("src.app.root_for", return_value=websites_root), \
             patch("src.app.is_r2_configured", return_value=False):
            r_css = self.client.get("/preview/2026-10-27/lead1/style.css")
            self.assertEqual(r_css.status_code, 200)
            self.assertIn("no-cache", r_css.headers.get("Cache-Control", ""))

            r_med = self.client.get("/media/2026-10-27/lead1/pfp.jpg")
            self.assertEqual(r_med.status_code, 200)
            self.assertIn("no-cache", r_med.headers.get("Cache-Control", ""))


if __name__ == "__main__":
    unittest.main()
