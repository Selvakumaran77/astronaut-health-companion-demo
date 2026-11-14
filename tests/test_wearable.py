from __future__ import annotations

import csv
import io
import json
import os
import sys
import tempfile
import threading
import unittest
from unittest.mock import patch
from http.server import ThreadingHTTPServer
from urllib.error import HTTPError
from urllib.request import build_opener

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "src"))
sys.path.insert(0, os.path.join(ROOT, "scripts"))

from healthmon.wearable import (  # noqa: E402
    ACTIVITIES,
    PARTICIPANTS,
    SIGNALS,
    STRESS_STAGES,
    health_indicator_catalog,
    load_wearable_dataset,
    participant_roster,
)
from serve_api import App, DEFAULT_DATA, DEFAULT_MODEL, main, make_handler  # noqa: E402


def create_wearable_fixture(root: str) -> None:
    os.makedirs(root, exist_ok=True)
    labels_path = os.path.join(root, "Stress_Level_v2.csv")
    with open(labels_path, "w", newline="", encoding="utf-8") as file:
        writer = csv.writer(file)
        writer.writerow(["", *STRESS_STAGES])
        for participant_index, participant_id in enumerate(PARTICIPANTS):
            writer.writerow([
                participant_id,
                *[float((participant_index + index) % 11) for index in range(7)],
            ])

    for participant_index, participant_id in enumerate(PARTICIPANTS):
        for directory, _ in ACTIVITIES.values():
            folder = os.path.join(
                root, "Wearable_Dataset", directory, participant_id
            )
            os.makedirs(folder, exist_ok=True)
            for code, (_, _, _) in SIGNALS.items():
                sample_rate = 1 if code == "HR" else 4
                first_value = 60 + participant_index if code == "HR" else 1 + participant_index
                path = os.path.join(folder, f"{code}.csv")
                with open(path, "w", newline="", encoding="utf-8") as file:
                    writer = csv.writer(file)
                    writer.writerow(["2013-06-12 16:19:08"])
                    writer.writerow([sample_rate])
                    writer.writerows(
                        [first_value + index % 20] for index in range(500)
                    )


class WearableDatasetTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.dataset_path = os.path.join(self.temp_dir.name, "wearable")
        create_wearable_fixture(self.dataset_path)

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_loads_only_four_participants_with_all_sessions_and_stage_scores(self):
        participants = load_wearable_dataset(self.dataset_path)
        self.assertEqual(tuple(participants), PARTICIPANTS)
        self.assertEqual(
            set(participants["f01"]["activities"]), set(ACTIVITIES)
        )
        self.assertEqual(
            [item["stage"] for item in participants["f01"]["stress_ratings"]],
            list(STRESS_STAGES),
        )
        self.assertNotIn("age", participants["f01"]["profile"])
        self.assertNotIn("gender", participants["f01"]["profile"])
        signal = participants["f01"]["activities"]["stress"]["signals"]["heart_rate_bpm"]
        self.assertEqual(signal["sample_count"], 500)
        self.assertEqual(signal["source"], "dataset")
        self.assertEqual(signal["average"], 69.5)
        self.assertEqual(signal["minimum"], 60)
        self.assertEqual(signal["maximum"], 79)
        self.assertLessEqual(len(signal["points"]), 240)
        self.assertEqual(signal["start_utc"], "2013-06-12 16:19:08")
        simulated = participants["f01"]["activities"]["stress"]["signals"]["spo2_pct"]
        self.assertEqual(simulated["source"], "simulated")
        self.assertEqual(len(simulated["points"]), 120)
        self.assertNotIn("sample_rate_hz", simulated)

    def test_indicator_catalog_covers_reference_and_research_signals(self):
        catalog = health_indicator_catalog()
        by_key = {indicator["key"]: indicator for indicator in catalog}
        expected = {
            "heart_rate_bpm", "systolic_bp_mmHg", "diastolic_bp_mmHg",
            "spo2_pct", "resp_rate_bpm", "body_temp_c", "sleep_hours",
            "mood_score_1_10", "cognitive_score_0_100",
            "bone_density_pct_change", "muscle_mass_pct_change",
            "wbc_1e9_per_L", "crp_mg_per_L", "radiation_dose_mSv_day",
            "radiation_dose_cumulative_mSv", "cabin_co2_ppm", "eda_us",
            "skin_temp_c",
        }
        self.assertEqual(set(by_key), expected)
        self.assertEqual(by_key["heart_rate_bpm"]["source"], "dataset")
        self.assertEqual(by_key["eda_us"]["source"], "dataset")
        self.assertEqual(by_key["skin_temp_c"]["source"], "dataset")
        self.assertTrue(all(
            by_key[key]["source"] == "simulated"
            for key in expected - {"heart_rate_bpm", "eda_us", "skin_temp_c"}
        ))

    def test_roster_contains_only_summary_values_for_four_selected_people(self):
        roster = participant_roster(load_wearable_dataset(self.dataset_path))
        self.assertEqual([item["participant_id"] for item in roster], list(PARTICIPANTS))
        self.assertEqual(
            [item["mission_number"] for item in roster],
            ["MS1001", "MS1002", "MS1003", "MS1004"],
        )
        self.assertTrue(all("stress_rating_baseline" in item for item in roster))
        self.assertTrue(all("heart_rate_bpm" in item for item in roster))
        self.assertTrue(all("age" not in item and "gender" not in item for item in roster))

    def test_missing_signals_are_reported(self):
        os.remove(
            os.path.join(
                self.dataset_path, "Wearable_Dataset", "STRESS", "f01", "HR.csv"
            )
        )
        with self.assertRaises(FileNotFoundError):
            load_wearable_dataset(self.dataset_path)

    def test_wearable_demo_refuses_non_localhost_binding(self):
        error = io.StringIO()
        with patch(
            "serve_api.sys.argv",
            ["serve_api.py", "--wearable-demo", "--host", "0.0.0.0"],
        ), patch("sys.stderr", error):
            self.assertEqual(main(), 1)
        self.assertIn("only bind to localhost", error.getvalue())

    def test_wearable_demo_api_exposes_only_four_reported_study_sessions(self):
        app = App(
            DEFAULT_DATA,
            DEFAULT_MODEL,
            os.path.join(self.temp_dir.name, "wearable-auth.sqlite3"),
            wearable_dataset=self.dataset_path,
        )
        server = ThreadingHTTPServer(("127.0.0.1", 0), make_handler(app))
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        base_url = f"http://127.0.0.1:{server.server_port}"
        try:
            with build_opener().open(base_url + "/api/astronauts", timeout=5) as response:
                roster = json.loads(response.read())
            self.assertTrue(roster["participant_demo"])
            self.assertTrue(roster["reports_public"])
            self.assertEqual(
                {item["key"] for item in roster["health_indicators"]},
                {item["key"] for item in health_indicator_catalog()},
            )
            self.assertEqual(
                {person["participant_id"] for person in roster["astronauts"]},
                set(PARTICIPANTS),
            )
            self.assertEqual(
                [person["mission_number"] for person in roster["astronauts"]],
                ["MS1001", "MS1002", "MS1003", "MS1004"],
            )
            with build_opener().open(
                base_url + "/api/wearable/report/f01", timeout=5
            ) as response:
                report = json.loads(response.read())
            self.assertEqual(report["participant_id"], "f01")
            self.assertEqual(report["profile"]["mission_number"], "MS1001")
            self.assertNotIn("name", report["profile"])
            self.assertEqual(len(report["activities"]), 3)
            self.assertEqual(len(report["stress_ratings"]), 7)
            self.assertEqual(
                set(report["activities"]["stress"]["signals"]),
                {item["key"] for item in health_indicator_catalog()},
            )
            self.assertNotIn("risk_indicator", report)
            self.assertNotIn("prediction", report)
            self.assertNotIn("age", report["profile"])
            with self.assertRaises(HTTPError) as unknown:
                build_opener().open(
                    base_url + "/api/wearable/report/f05", timeout=5
                )
            self.assertEqual(unknown.exception.code, 404)
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=3)


if __name__ == "__main__":
    unittest.main()
