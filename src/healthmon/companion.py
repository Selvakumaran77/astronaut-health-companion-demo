"""Local demo storage for astronaut wellbeing check-ins and handoff requests."""

from __future__ import annotations

import json
import os
import sqlite3
from contextlib import contextmanager
from datetime import date, datetime, timedelta, timezone
from typing import Iterator


class CompanionStore:
    """Persist demonstration check-ins and unsent report handoffs."""

    def __init__(self, path: str):
        self.path = path
        os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
        with self._connect() as db:
            db.execute(
                """CREATE TABLE IF NOT EXISTS wellbeing_checkins (
                    crew_id TEXT NOT NULL,
                    checkin_date TEXT NOT NULL,
                    sleep_hours REAL NOT NULL,
                    exercise_minutes INTEGER NOT NULL,
                    exercise_type TEXT NOT NULL,
                    stress_score INTEGER NOT NULL,
                    created_at TEXT NOT NULL,
                    PRIMARY KEY (crew_id, checkin_date)
                )"""
            )
            db.execute(
                """CREATE TABLE IF NOT EXISTS daily_measurements (
                    crew_id TEXT NOT NULL,
                    mission_day INTEGER NOT NULL,
                    date_utc TEXT NOT NULL,
                    readings_json TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    PRIMARY KEY (crew_id, mission_day)
                )"""
            )
            db.execute(
                """CREATE TABLE IF NOT EXISTS local_handoff_queue (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    crew_id TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    report_json TEXT NOT NULL,
                    delivery_status TEXT NOT NULL DEFAULT 'queued_local'
                )"""
            )

    @contextmanager
    def _connect(self) -> Iterator[sqlite3.Connection]:
        db = sqlite3.connect(self.path, timeout=10)
        db.row_factory = sqlite3.Row
        try:
            yield db
            db.commit()
        except Exception:
            db.rollback()
            raise
        finally:
            db.close()

    @staticmethod
    def _utc_now(now: datetime | None = None) -> datetime:
        value = now or datetime.now(timezone.utc)
        if value.tzinfo is None:
            value = value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc)

    def save_checkin(
        self,
        crew_id: str,
        *,
        sleep_hours: float,
        exercise_minutes: int,
        exercise_type: str,
        stress_score: int,
        now: datetime | None = None,
    ) -> dict:
        created_at = self._utc_now(now)
        day = created_at.date().isoformat()
        with self._connect() as db:
            db.execute(
                """INSERT INTO wellbeing_checkins
                   (crew_id, checkin_date, sleep_hours, exercise_minutes,
                    exercise_type, stress_score, created_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?)
                   ON CONFLICT(crew_id, checkin_date) DO UPDATE SET
                       sleep_hours = excluded.sleep_hours,
                       exercise_minutes = excluded.exercise_minutes,
                       exercise_type = excluded.exercise_type,
                       stress_score = excluded.stress_score,
                       created_at = excluded.created_at""",
                (
                    crew_id,
                    day,
                    sleep_hours,
                    exercise_minutes,
                    exercise_type,
                    stress_score,
                    created_at.isoformat(),
                ),
            )
        return {
            "crew_id": crew_id,
            "date": day,
            "sleep_hours": sleep_hours,
            "exercise_minutes": exercise_minutes,
            "exercise_type": exercise_type,
            "stress_score": stress_score,
            "created_at": created_at.isoformat(),
        }

    def save_measurement(
        self,
        crew_id: str,
        mission_day: int,
        date_utc: str,
        readings: dict[str, float],
        now: datetime | None = None,
    ) -> dict:
        created_at = self._utc_now(now).isoformat()
        with self._connect() as db:
            db.execute(
                """INSERT INTO daily_measurements
                   (crew_id, mission_day, date_utc, readings_json, created_at)
                   VALUES (?, ?, ?, ?, ?)""",
                (
                    crew_id,
                    mission_day,
                    date_utc,
                    json.dumps(readings, separators=(",", ":")),
                    created_at,
                ),
            )
        return {
            "crew_id": crew_id,
            "mission_day": mission_day,
            "date_utc": date_utc,
            **readings,
            "created_at": created_at,
        }

    def measurements_for_crew(self, crew_id: str) -> list[dict]:
        with self._connect() as db:
            rows = db.execute(
                """SELECT mission_day, date_utc, readings_json
                   FROM daily_measurements WHERE crew_id = ?
                   ORDER BY mission_day""",
                (crew_id,),
            ).fetchall()
        return [
            {
                "crew_id": crew_id,
                "mission_day": int(row["mission_day"]),
                "date_utc": row["date_utc"],
                **json.loads(row["readings_json"]),
            }
            for row in rows
        ]

    def all_measurements(self) -> list[dict]:
        with self._connect() as db:
            rows = db.execute(
                """SELECT crew_id, mission_day, date_utc, readings_json
                   FROM daily_measurements ORDER BY crew_id, mission_day"""
            ).fetchall()
        return [
            {
                "crew_id": row["crew_id"],
                "mission_day": int(row["mission_day"]),
                "date_utc": row["date_utc"],
                **json.loads(row["readings_json"]),
            }
            for row in rows
        ]

    def state(
        self,
        crew_id: str,
        now: datetime | None = None,
        latest_measurement_date: str | None = None,
    ) -> dict:
        today = self._utc_now(now).date()
        with self._connect() as db:
            rows = db.execute(
                """SELECT checkin_date, sleep_hours, exercise_minutes,
                          exercise_type, stress_score, created_at
                   FROM wellbeing_checkins WHERE crew_id = ?
                   ORDER BY checkin_date DESC LIMIT 30""",
                (crew_id,),
            ).fetchall()
        checkins = [
            {
                "date": row["checkin_date"],
                "sleep_hours": row["sleep_hours"],
                "exercise_minutes": row["exercise_minutes"],
                "exercise_type": row["exercise_type"],
                "stress_score": row["stress_score"],
                "created_at": row["created_at"],
            }
            for row in rows
        ]
        completed_dates = {date.fromisoformat(row["date"]) for row in checkins}
        streak = 0
        cursor = max(completed_dates, default=None)
        if cursor and (today - cursor).days <= 1:
            while cursor in completed_dates:
                streak += 1
                cursor -= timedelta(days=1)
        total_checkins = self._total_checkins(crew_id)
        measurements = self.measurements_for_crew(crew_id)
        stored_measurement_date = (
            measurements[-1]["date_utc"] if measurements else None
        )
        last_measurement_date = max(
            (day for day in (stored_measurement_date, latest_measurement_date) if day),
            default=None,
        )
        badges = []
        if total_checkins:
            badges.append({"id": "first-checkin", "label": "First check-in"})
        if streak >= 3:
            badges.append({"id": "three-day-streak", "label": "3-day streak"})
        if streak >= 7:
            badges.append({"id": "seven-day-streak", "label": "7-day streak"})
        return {
            "today": today.isoformat(),
            "reminder_due": today not in completed_dates,
            "measurement_due": (
                last_measurement_date is None
                or last_measurement_date < today.isoformat()
            ),
            "last_measurement_date": last_measurement_date,
            "total_checkins": total_checkins,
            "current_streak": streak,
            "badges": badges,
            "checkins": checkins,
        }

    def _total_checkins(self, crew_id: str) -> int:
        with self._connect() as db:
            row = db.execute(
                "SELECT COUNT(*) FROM wellbeing_checkins WHERE crew_id = ?",
                (crew_id,),
            ).fetchone()
        return int(row[0])

    def queue_handoff(
        self,
        crew_id: str,
        report: dict,
        now: datetime | None = None,
    ) -> dict:
        created_at = self._utc_now(now).isoformat()
        with self._connect() as db:
            cursor = db.execute(
                """INSERT INTO local_handoff_queue
                   (crew_id, created_at, report_json, delivery_status)
                   VALUES (?, ?, ?, 'queued_local')""",
                (crew_id, created_at, json.dumps(report, separators=(",", ":"))),
            )
            report_id = int(cursor.lastrowid)
        return {
            "id": report_id,
            "crew_id": crew_id,
            "created_at": created_at,
            "delivery_status": "queued_local",
            "transmitted": False,
        }

    def handoffs_for_crew(self, crew_id: str, limit: int = 20) -> list[dict]:
        with self._connect() as db:
            rows = db.execute(
                """SELECT id, created_at, report_json, delivery_status
                   FROM local_handoff_queue WHERE crew_id = ?
                   ORDER BY id DESC LIMIT ?""",
                (crew_id, limit),
            ).fetchall()
        return [
            {
                "id": int(row["id"]),
                "created_at": row["created_at"],
                "delivery_status": row["delivery_status"],
                "transmitted": False,
                "report": json.loads(row["report_json"]),
            }
            for row in rows
        ]

    def simulate_handoff_acknowledgement(
        self,
        crew_id: str,
        handoff_id: int,
        now: datetime | None = None,
    ) -> dict | None:
        acknowledged_at = self._utc_now(now).isoformat()
        with self._connect() as db:
            cursor = db.execute(
                """UPDATE local_handoff_queue
                   SET delivery_status = 'mock_acknowledged'
                   WHERE id = ? AND crew_id = ? AND delivery_status = 'queued_local'""",
                (handoff_id, crew_id),
            )
            if cursor.rowcount != 1:
                return None
            row = db.execute(
                """SELECT id, created_at, report_json, delivery_status
                   FROM local_handoff_queue WHERE id = ? AND crew_id = ?""",
                (handoff_id, crew_id),
            ).fetchone()
        return {
            "id": int(row["id"]),
            "created_at": row["created_at"],
            "acknowledged_at": acknowledged_at,
            "delivery_status": row["delivery_status"],
            "transmitted": False,
            "report": json.loads(row["report_json"]),
        }
