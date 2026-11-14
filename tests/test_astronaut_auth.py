from __future__ import annotations

import csv
import json
import os
import re
import sqlite3
import subprocess
import sys
import tempfile
import threading
import unittest
from datetime import datetime, timedelta, timezone
from email.utils import format_datetime
from io import BytesIO
from http.server import ThreadingHTTPServer
from http.cookiejar import CookieJar
from urllib.error import HTTPError
from urllib.request import HTTPCookieProcessor, Request, build_opener
from unittest.mock import patch

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "src"))
sys.path.insert(0, os.path.join(ROOT, "scripts"))

from healthmon.auth import AuthStore  # noqa: E402
from healthmon.features import BASE_FIELDS  # noqa: E402
from serve_api import App, DEFAULT_DATA, DEFAULT_MODEL, make_handler  # noqa: E402


class AstronautAuthTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.auth = AuthStore(os.path.join(self.temp_dir.name, "badges.sqlite3"))
        self.commander_badge = self.auth.issue_badge("CDR-1")
        self.specialist_badge = self.auth.issue_badge("MS-1")
        app = App(
            DEFAULT_DATA,
            DEFAULT_MODEL,
            os.path.join(self.temp_dir.name, "api-badges.sqlite3"),
            public_demo=getattr(self, "public_demo", False),
        )
        app.auth = self.auth
        self.app = app
        self.server = ThreadingHTTPServer(("127.0.0.1", 0), make_handler(app))
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.base_url = f"http://127.0.0.1:{self.server.server_port}"
        self.browser = build_opener(HTTPCookieProcessor(CookieJar()))

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=3)
        self.temp_dir.cleanup()

    def request(self, path, *, opener=None, method="GET", body=None):
        data = None if body is None else json.dumps(body).encode("utf-8")
        request = Request(self.base_url + path, data=data, method=method)
        if data is not None:
            request.add_header("Content-Type", "application/json")
        try:
            with (opener or build_opener()).open(request, timeout=5) as response:
                return response.status, json.loads(response.read())
        except HTTPError as response:
            return response.code, json.loads(response.read())

    def scan(self, badge_code):
        return self.request(
            "/api/scan",
            opener=self.browser,
            method="POST",
            body={"badge_code": badge_code},
        )

    def sign_in_with_mission_number(self, number, crew_id="CDR-1"):
        return self.request(
            "/api/mission-number",
            opener=self.browser,
            method="POST",
            body={"mission_number": number, "crew_id": crew_id},
        )

    def test_private_data_requires_login(self):
        self.assertEqual(self.request("/health")[0], 200)
        self.assertEqual(self.request("/api/me/report")[0], 401)
        self.assertEqual(self.request("/readings?crew=CDR-1")[0], 401)

    def test_public_page_offers_mission_number_login(self):
        with build_opener().open(self.base_url + "/", timeout=5) as response:
            self.assertEqual(response.status, 200)
            page = response.read().decode("utf-8")
        self.assertIn("Enter mission number", page)
        self.assertIn("/api/mission-number", page)
        self.assertIn('id="crewCards"', page)
        self.assertIn('element("button","astronaut-card")', page)
        self.assertIn("/assets/images/card_background.jpg", page)
        self.assertIn("Select an astronaut", page)
        self.assertIn('pattern="[0-9]{20}"', page)
        self.assertIn('src="/assets/videos/background.mp4"', page)
        self.assertIn('id="agentToggle"', page)
        self.assertIn('id="agentPreview"', page)
        self.assertIn('id="agentForm"', page)
        self.assertIn("/api/agent/news", page)
        self.assertIn("BBC feeds", page)
        self.assertIn('id="wearableReport"', page)
        self.assertIn('id="wearableSignalView"', page)
        self.assertIn('id="stressRatingView"', page)
        self.assertIn('id="stressRatingChart"', page)
        self.assertIn('id="wearableSignalChart"', page)
        self.assertIn('id="studyObservation"', page)
        self.assertIn("stage mean (0)", page)
        self.assertIn("session mean (0)", page)
        self.assertNotIn('id="indicatorCards"', page)
        self.assertIn("This dashboard combines historical study measurements with generated example values", page)
        self.assertIn("healthIndicators.map(indicator=>", page)
        self.assertIn('element("option","",indicator.label)', page)
        self.assertNotIn("Simulated demonstration value", page)
        self.assertIn("mission numbers MS1001–MS1004", page)
        self.assertIn("wearableMode?astronaut.mission_number:astronaut.name", page)
        self.assertNotIn("Avery Morgan", page)
        self.assertIn('id="earthEscalation"', page)
        self.assertIn("consult an Earth-based doctor or flight surgeon promptly", page)
        self.assertIn('transmitted:false', page)
        self.assertIn("without transmitting data", page)
        self.assertIn('id="wellbeingForm"', page)
        self.assertIn('id="weeklyPanel"', page)
        self.assertIn('id="emergencyPanel"', page)
        self.assertIn('id="bodyMapTitle"', page)
        self.assertIn('id="environmentMode"', page)
        self.assertIn('https://www.nasa.gov/hrp/', page)
        self.assertIn("Queueing saves the report on this server only", page)
        self.assertIn('id="doctorBoardToggle"', page)
        self.assertIn("synthetic demo review board", page)
        self.assertIn('id="enableReminder"', page)
        self.assertIn("cannot remind you after the app is closed", page)
        self.assertIn("Simulate ground-station acknowledgement", page)
        self.assertNotIn("BarcodeDetector", page)
        self.assertNotIn("Use camera to scan barcode", page)
        self.assertNotIn('id="scanner"', page)
        self.assertNotIn('name="password"', page)
        self.assertNotIn('name="username"', page)

    def test_public_news_endpoint_uses_allowlisted_live_feed_without_health_data(self):
        now=datetime.now(timezone.utc)
        newest=format_datetime(now-timedelta(hours=1))
        older=format_datetime(now-timedelta(hours=2))
        stale=format_datetime(now-timedelta(days=3))
        future=format_datetime(now+timedelta(hours=1))
        feed = BytesIO(f"""<rss><channel>
            <item><title>Older sports headline</title>
            <link>https://www.bbc.com/sport/older</link>
            <pubDate>{older}</pubDate></item>
            <item><title>Latest sports headline</title>
            <link>https://www.bbc.com/sport/example</link>
            <pubDate>{newest}</pubDate>
            <description>&lt;p&gt;Fresh summary.&lt;/p&gt;</description></item>
            <item><title>Stale headline</title>
            <link>https://www.bbc.com/sport/stale</link>
            <pubDate>{stale}</pubDate></item>
            <item><title>Future headline</title>
            <link>https://www.bbc.com/sport/future</link>
            <pubDate>{future}</pubDate></item>
            <item><title>Untrusted link</title>
            <link>https://example.com/story</link>
            <pubDate>{newest}</pubDate></item>
            </channel></rss>""".encode())
        with patch("serve_api.urlopen", return_value=feed) as open_feed:
            status, response = self.request("/api/agent/news?topic=sports")
        self.assertEqual(status, 200)
        self.assertEqual(response["source"], "BBC Sport")
        self.assertEqual(
            [item["title"] for item in response["articles"]],
            ["Latest sports headline", "Older sports headline"],
        )
        self.assertEqual(response["articles"][0]["summary"], "Fresh summary.")
        self.assertEqual(response["max_age_hours"], 48)
        self.assertIn("fetched_at", response)
        self.assertEqual(
            open_feed.call_args.args[0].full_url,
            "https://feeds.bbci.co.uk/sport/rss.xml",
        )
        self.assertEqual(open_feed.call_args.kwargs["timeout"], 5)

    def test_news_endpoint_rejects_unknown_topics_and_reports_feed_failure(self):
        with patch("serve_api.urlopen") as open_feed:
            self.assertEqual(
                self.request("/api/agent/news?topic=https://example.com")[0], 400
            )
            open_feed.assert_not_called()
        with patch("serve_api.urlopen", side_effect=OSError("offline")):
            status, response = self.request("/api/agent/news?topic=entertainment")
        self.assertEqual(status, 502)
        self.assertIn("unavailable", response["error"])

    def test_public_astronaut_list_contains_only_card_metadata(self):
        status, response = self.request("/api/astronauts")
        self.assertEqual(status, 200)
        self.assertEqual(len(response["astronauts"]), 4)
        self.assertEqual(
            {astronaut["crew_id"] for astronaut in response["astronauts"]},
            {"CDR-1", "MS-1", "MS-2", "PLT-1"},
        )
        self.assertTrue(
            all(set(astronaut) == {"crew_id", "name", "role"}
                for astronaut in response["astronauts"])
        )
        self.assertFalse(response["reports_public"])

    def test_public_demo_cards_open_only_the_selected_synthetic_report(self):
        app = App(
            DEFAULT_DATA,
            DEFAULT_MODEL,
            os.path.join(self.temp_dir.name, "api-badges.sqlite3"),
            public_demo=True,
        )
        server = ThreadingHTTPServer(("127.0.0.1", 0), make_handler(app))
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        base_url = f"http://127.0.0.1:{server.server_port}"
        try:
            with build_opener().open(base_url + "/api/astronauts", timeout=5) as response:
                roster = json.loads(response.read())
            self.assertTrue(roster["reports_public"])
            self.assertTrue(
                all(
                    {"heart_rate_bpm", "body_temp_c", "spo2_pct", "mission_day"}
                    <= set(astronaut["latest"])
                    for astronaut in roster["astronauts"]
                )
            )
            with build_opener().open(
                base_url + "/api/demo/report/CDR-1", timeout=5
            ) as response:
                report = json.loads(response.read())
            self.assertEqual(report["crew_id"], "CDR-1")
            self.assertNotIn("latent_stress_index", report["latest"])
            self.assertEqual(len(report["history"]), 180)
            self.assertTrue(all("risk_probability" in row for row in report["history"]))
            self.assertTrue(
                all("latent_stress_index" not in row for row in report["history"])
            )
            with build_opener().open(
                base_url + "/api/demo/doctor-dashboard", timeout=5
            ) as response:
                doctor_board = json.loads(response.read())
            self.assertEqual(
                doctor_board["data_mode"],
                "unchanged_synthetic_public_demo",
            )
            self.assertFalse(doctor_board["clinical_use"])
            self.assertEqual(len(doctor_board["crew"]), 4)
            self.assertEqual(len(doctor_board["crew"][0]["history"]), 7)
            self.assertIn("synthetic", doctor_board["note"].lower())
            with self.assertRaises(HTTPError) as unknown:
                build_opener().open(
                    base_url + "/api/demo/report/UNKNOWN", timeout=5
                )
            self.assertEqual(unknown.exception.code, 404)
            with self.assertRaises(HTTPError) as protected:
                build_opener().open(
                    base_url + "/readings?crew=CDR-1", timeout=5
                )
            self.assertEqual(protected.exception.code, 401)
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=3)

    def test_public_demo_rejects_non_default_dataset(self):
        not_default = os.path.join(self.temp_dir.name, "not-the-default.csv")
        with open(DEFAULT_DATA, "rb") as source, open(not_default, "wb") as target:
            target.write(source.read())
        with self.assertRaisesRegex(ValueError, "unchanged checked-in synthetic"):
            App(
                not_default,
                DEFAULT_MODEL,
                os.path.join(self.temp_dir.name, "public.sqlite3"),
                public_demo=True,
            )

    def test_astronaut_card_background_is_served_as_jpeg(self):
        with build_opener().open(
            self.base_url + "/assets/images/card_background.jpg", timeout=5
        ) as response:
            self.assertEqual(response.status, 200)
            self.assertEqual(response.headers.get_content_type(), "image/jpeg")
            self.assertGreater(len(response.read()), 0)

    def test_background_video_is_served_as_mp4(self):
        status, _ = self.request("/health")
        self.assertEqual(status, 200)
        with build_opener().open(
            self.base_url + "/assets/videos/background.mp4", timeout=5
        ) as response:
            self.assertEqual(response.status, 200)
            self.assertEqual(response.headers.get_content_type(), "video/mp4")
            self.assertGreater(len(response.read()), 0)

    def test_scan_report_and_crew_isolation(self):
        latest = dict(self.app.by_crew()["CDR-1"][-1])
        latest.update(mission_day=181, date_utc="2026-11-28", heart_rate_bpm=85.0)
        self.app.rows.append(latest)
        self.assertEqual(self.scan(self.commander_badge)[0], 200)
        status, report = self.request("/api/me/report", opener=self.browser)
        self.assertEqual(status, 200)
        self.assertEqual(report["crew_id"], "CDR-1")
        self.assertNotIn("latent_stress_index", report["latest"])
        self.assertIn(report["risk_indicator"]["state"], ("safe", "rising", "above_safe"))
        self.assertEqual(len(report["history"]), len(self.app.by_crew()["CDR-1"]))
        self.assertEqual(report["weekly_summary"]["readings_count"], 7)
        self.assertTrue(report["weekly_summary"]["illustrative_only"])
        self.assertTrue(report["companion"]["reminder_due"])
        self.assertFalse(report["companion"]["measurement_due"])
        self.assertEqual(report["status"]["level"], "watch")
        self.assertTrue(any("Personalized" in reason for reason in report["status"]["reasons"]))
        self.assertTrue(any("resting measurement" in advice for advice in report["advice"]))
        self.assertEqual(self.request("/readings?crew=MS-1", opener=self.browser)[0], 403)

        status, result = self.request(
            "/predict",
            opener=self.browser,
            method="POST",
            body={"reading": {"crew_id": "MS-1", "mission_day": 181, "heart_rate_bpm": 70}},
        )
        self.assertEqual(status, 200)
        self.assertEqual(result["predictions"][0]["crew_id"], "CDR-1")

        self.assertEqual(self.request("/api/logout", opener=self.browser, method="POST", body={})[0], 200)
        self.assertEqual(self.request("/api/me/report", opener=self.browser)[0], 401)

    def test_mission_number_sign_in_is_crew_scoped(self):
        number = self.auth.issue_mission_number("CDR-1")
        self.assertRegex(number, r"^[0-9]{20}$")
        self.assertEqual(
            self.sign_in_with_mission_number(number, "MS-1")[0], 401
        )
        status, response = self.sign_in_with_mission_number(number)
        self.assertEqual(status, 200)
        self.assertTrue(response["authenticated"])
        status, report = self.request("/api/me/report", opener=self.browser)
        self.assertEqual(status, 200)
        self.assertEqual(report["crew_id"], "CDR-1")
        self.assertEqual(self.request("/readings?crew=MS-1", opener=self.browser)[0], 403)
        self.assertEqual(
            self.request(
                "/api/mission-number",
                method="POST",
                body={"mission_number": "CDR-1"},
            )[0],
            401,
        )

    def test_revoked_badge_and_sessions_are_rejected(self):
        self.assertEqual(self.scan(self.commander_badge)[0], 200)
        self.assertEqual(self.auth.revoke_badges("CDR-1"), 1)
        self.assertEqual(self.request("/api/me/report", opener=self.browser)[0], 401)
        self.assertEqual(self.scan(self.commander_badge)[0], 401)

    def test_external_mission_number_reissue_revokes_active_session(self):
        number = self.auth.issue_mission_number("CDR-1")
        self.assertEqual(self.sign_in_with_mission_number(number)[0], 200)
        AuthStore(self.auth.path).issue_mission_number("CDR-1")
        self.assertEqual(self.request("/api/me/report", opener=self.browser)[0], 401)

    def test_issuing_new_badge_revokes_previous_badge(self):
        replacement = self.auth.issue_badge("CDR-1")
        self.assertIsNone(self.auth.authenticate_badge(self.commander_badge))
        self.assertEqual(self.auth.authenticate_badge(replacement), "CDR-1")
        self.assertEqual(self.auth.authenticate_badge(self.specialist_badge), "MS-1")

    def test_indicator_covers_safe_rising_and_above_safe(self):
        ms2 = self.app.by_crew()["MS-2"][-1]
        ms2["body_temp_c"] = 38.0
        self.assertEqual(self.app.report("CDR-1")["risk_indicator"]["state"], "safe")
        self.assertEqual(self.app.report("MS-2")["risk_indicator"]["state"], "rising")
        report = self.app.report("PLT-1")
        self.assertEqual(report["risk_indicator"]["state"], "above_safe")
        self.assertTrue(any(
            "Earth-based doctor or flight surgeon" in advice
            for advice in report["advice"]
        ))

    def test_preflight_b_score_is_the_personal_comparison_line(self):
        baseline = self.app.auth.preflight_baseline_for_crew("CDR-1")
        self.assertIsNone(baseline)
        self.app.auth.set_preflight_baseline("CDR-1", 1.0, self.app.model_signature)
        indicator = self.app.report("CDR-1")["risk_indicator"]
        self.assertTrue(indicator["baseline_set"])
        self.assertEqual(indicator["personal_baseline"], 0.01)
        self.assertEqual(indicator["state"], "above_safe")
        self.app.auth.set_preflight_baseline("CDR-1", 1.0, "old-model-signature")
        stale = self.app.report("CDR-1")["risk_indicator"]
        self.assertTrue(stale["baseline_stale"])
        self.assertFalse(stale["baseline_set"])
        with self.assertRaises(ValueError):
            self.app.auth.set_preflight_baseline("CDR-1", 101.0, self.app.model_signature)

    def test_preflight_checkup_file_is_scored_and_recorded(self):
        auth_db = os.path.join(self.temp_dir.name, "ground-checkup.sqlite3")
        reading_path = os.path.join(self.temp_dir.name, "ground-checkup.json")
        reading = dict(self.app.by_crew()["CDR-1"][0])
        reading.pop("latent_stress_index", None)
        with open(reading_path, "w", encoding="utf-8") as file:
            json.dump(reading, file)
        result = subprocess.run(
            [
                sys.executable,
                os.path.join(ROOT, "scripts", "set_preflight_baseline.py"),
                "CDR-1",
                "--auth-db", auth_db,
                "--reading-file", reading_path,
            ],
            capture_output=True,
            text=True,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        baseline = AuthStore(auth_db).preflight_baseline_for_crew("CDR-1")
        self.assertIsNotNone(baseline)
        self.assertGreaterEqual(baseline[0], 0)
        self.assertLessEqual(baseline[0], 100)
        self.assertEqual(baseline[2], self.app.model_signature)
        measurements = AuthStore(auth_db).preflight_measurements_for_crew("CDR-1")
        self.assertEqual(set(measurements), set(BASE_FIELDS))
        self.assertIsInstance(measurements["heart_rate_bpm"], float)

    def test_wellbeing_checkin_validation_streak_and_crew_isolation(self):
        self.assertEqual(self.scan(self.commander_badge)[0], 200)
        checkin = {
            "sleep_hours": 7.5,
            "exercise_minutes": 30,
            "exercise_type": "aerobic",
            "stress_score": 4,
        }
        status, response = self.request(
            "/api/me/checkin",
            opener=self.browser,
            method="POST",
            body=checkin,
        )
        self.assertEqual(status, 201)
        self.assertFalse(response["companion"]["reminder_due"])
        self.assertEqual(response["companion"]["total_checkins"], 1)
        self.assertEqual(response["companion"]["current_streak"], 1)
        self.assertEqual(response["companion"]["badges"][0]["id"], "first-checkin")

        invalid = dict(checkin, exercise_type=[])
        self.assertEqual(
            self.request(
                "/api/me/checkin",
                opener=self.browser,
                method="POST",
                body=invalid,
            )[0],
            400,
        )

        self.assertEqual(self.sign_in_with_mission_number(
            self.auth.issue_mission_number("MS-1"), "MS-1"
        )[0], 200)
        status, report = self.request("/api/me/report", opener=self.browser)
        self.assertEqual(status, 200)
        self.assertEqual(report["companion"]["total_checkins"], 0)
        self.assertTrue(report["companion"]["reminder_due"])

    def test_above_safe_report_can_be_queued_locally_without_transmission(self):
        self.assertEqual(self.scan(self.commander_badge)[0], 200)
        self.assertEqual(
            self.request(
                "/api/me/emergency-report",
                opener=self.browser,
                method="POST",
                body={},
            )[0],
            409,
        )

        latest = self.app.by_crew()["CDR-1"][-1]
        latest["spo2_pct"] = 80
        status, response = self.request(
            "/api/me/emergency-report",
            opener=self.browser,
            method="POST",
            body={},
        )
        self.assertEqual(status, 201)
        self.assertEqual(response["handoff"]["delivery_status"], "queued_local")
        self.assertFalse(response["handoff"]["transmitted"])
        self.assertFalse(response["delivery"]["transmitted"])
        _, report = self.request("/api/me/report", opener=self.browser)
        self.assertEqual(len(report["local_handoffs"]), 1)
        self.assertEqual(
            report["local_handoffs"][0]["report"]["delivery"]["status"],
            "queued_local",
        )
        handoff_id = report["local_handoffs"][0]["id"]
        status, response = self.request(
            "/api/me/mock-handoff-ack",
            opener=self.browser,
            method="POST",
            body={"handoff_id": handoff_id},
        )
        self.assertEqual(status, 200)
        self.assertEqual(response["handoff"]["delivery_status"], "mock_acknowledged")
        self.assertFalse(response["handoff"]["transmitted"])
        self.assertIn("No report was sent", response["note"])
        self.assertEqual(
            self.request(
                "/api/me/mock-handoff-ack",
                opener=self.browser,
                method="POST",
                body={"handoff_id": handoff_id},
            )[0],
            404,
        )
        _, updated_report = self.request("/api/me/report", opener=self.browser)
        self.assertEqual(
            updated_report["local_handoffs"][0]["delivery_status"],
            "mock_acknowledged",
        )

    def test_self_reported_urgent_symptoms_bypass_a_safe_demo_score(self):
        self.assertEqual(self.scan(self.commander_badge)[0], 200)
        status, response = self.request(
            "/api/me/emergency-report",
            opener=self.browser,
            method="POST",
            body={"urgent_symptoms_confirmed": True},
        )
        self.assertEqual(status, 201)
        self.assertEqual(
            response["handoff"]["delivery_status"],
            "queued_local",
        )
        _, report = self.request("/api/me/report", opener=self.browser)
        self.assertEqual(
            report["local_handoffs"][0]["report"]["trigger"],
            "astronaut_self_reported_urgent_symptoms",
        )

    def test_daily_measurement_is_validated_scored_and_persisted(self):
        self.assertEqual(self.scan(self.commander_badge)[0], 200)
        measurements = {
            field: float(self.app.by_crew()["CDR-1"][-1][field])
            for field in BASE_FIELDS
        }
        status, response = self.request(
            "/api/me/readings",
            opener=self.browser,
            method="POST",
            body=measurements,
        )
        self.assertEqual(status, 201)
        self.assertEqual(response["reading"]["mission_day"], 181)
        self.assertEqual(len(self.app.by_crew()["CDR-1"]), 181)
        self.assertEqual(response["reading"]["date_utc"], "2026-11-28")
        self.assertEqual(
            self.request("/api/me/readings", opener=self.browser, method="POST", body={"heart_rate_bpm": 1})[0],
            400,
        )
        self.assertFalse(self.app.companion.state("CDR-1")["measurement_due"])

        restarted = App(
            DEFAULT_DATA,
            DEFAULT_MODEL,
            os.path.join(self.temp_dir.name, "api-badges.sqlite3"),
        )
        self.assertEqual(len(restarted.by_crew()["CDR-1"]), 181)

    def test_badge_issuance_creates_barcode_and_stores_only_digest(self):
        auth_db = os.path.join(self.temp_dir.name, "issued.sqlite3")
        badge_dir = os.path.join(self.temp_dir.name, "barcodes")
        result = subprocess.run(
            [
                sys.executable,
                os.path.join(ROOT, "scripts", "manage_badges.py"),
                "--auth-db", auth_db,
                "--badge-dir", badge_dir,
                "issue-mission-number", "CDR-1",
            ],
            check=True,
            capture_output=True,
            text=True,
        )
        code = re.search(r"Private mission number \(store securely\): (\S+)", result.stdout)
        self.assertIsNotNone(code)
        badge_code = code.group(1)
        self.assertRegex(badge_code, r"^[0-9]{20}$")
        self.assertEqual(AuthStore(auth_db).authenticate_badge(badge_code), "CDR-1")
        files = os.listdir(badge_dir)
        self.assertEqual(len(files), 1)
        with open(os.path.join(badge_dir, files[0]), encoding="utf-8") as file:
            svg = file.read()
        self.assertIn("<svg", svg)
        self.assertNotIn(badge_code, svg)
        db = sqlite3.connect(auth_db)
        try:
            stored_hash = db.execute("SELECT token_hash FROM badges").fetchone()[0]
        finally:
            db.close()
        self.assertNotEqual(stored_hash, badge_code)

    def test_issue_all_saves_private_codes_for_each_crew_member(self):
        auth_db = os.path.join(self.temp_dir.name, "all-issued.sqlite3")
        badge_dir = os.path.join(self.temp_dir.name, "all-barcodes")
        codes_file = os.path.join(self.temp_dir.name, "badge_codes.csv")
        result = subprocess.run(
            [
                sys.executable,
                os.path.join(ROOT, "scripts", "manage_badges.py"),
                "--auth-db", auth_db,
                "--badge-dir", badge_dir,
                "issue-all",
                "--codes-file", codes_file,
            ],
            check=True,
            capture_output=True,
            text=True,
        )
        self.assertIn("Issued 4 private mission numbers.", result.stdout)
        with open(codes_file, encoding="utf-8", newline="") as file:
            records = list(csv.DictReader(file))
        self.assertEqual(
            {record["crew_id"] for record in records},
            {"CDR-1", "MS-1", "MS-2", "PLT-1"},
        )
        auth = AuthStore(auth_db)
        for record in records:
            self.assertRegex(record["mission_number"], r"^[0-9]{20}$")
            self.assertEqual(auth.authenticate_badge(record["mission_number"]), record["crew_id"])
            self.assertTrue(os.path.isfile(os.path.join(ROOT, record["barcode_file"])))
        self.assertEqual(len(os.listdir(badge_dir)), 4)

    def test_scan_attempts_are_rate_limited(self):
        for _ in range(5):
            self.assertEqual(self.scan("invalid-badge-code")[0], 401)
        self.assertEqual(self.scan(self.commander_badge)[0], 429)


if __name__ == "__main__":
    unittest.main()
