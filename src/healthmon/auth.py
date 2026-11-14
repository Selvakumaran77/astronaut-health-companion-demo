"""Revocable astronaut badge credentials and in-memory web sessions."""

from __future__ import annotations

import hashlib
import json
import math
import os
import secrets
import sqlite3
import threading
import time
from contextlib import contextmanager
from typing import Iterator

SESSION_TTL_SECONDS = 12 * 60 * 60
LOGIN_WINDOW_SECONDS = 15 * 60
LOGIN_ATTEMPT_LIMIT = 5
BADGE_BYTES = 32
MISSION_NUMBER_DIGITS = 20


def _badge_digest(code: str) -> str:
    return hashlib.sha256(code.encode("utf-8")).hexdigest()


class AuthStore:
    def __init__(self, path: str):
        self.path = path
        os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
        self._lock = threading.Lock()
        self._sessions: dict[str, tuple[str, float, str]] = {}
        self._login_failures: dict[str, list[float]] = {}
        with self._connect() as db:
            db.execute("PRAGMA journal_mode=WAL")
            db.execute(
                """CREATE TABLE IF NOT EXISTS badges (
                    token_hash TEXT PRIMARY KEY,
                    crew_id TEXT NOT NULL,
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    revoked_at TEXT
                )"""
            )
            db.execute(
                """CREATE TABLE IF NOT EXISTS preflight_baselines (
                    crew_id TEXT PRIMARY KEY,
                    score REAL NOT NULL CHECK (score >= 0 AND score <= 100),
                    model_signature TEXT NOT NULL,
                    measurements_json TEXT,
                    recorded_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                )"""
            )
            baseline_columns = {
                row[1] for row in db.execute("PRAGMA table_info(preflight_baselines)")
            }
            if "model_signature" not in baseline_columns:
                db.execute(
                    "ALTER TABLE preflight_baselines "
                    "ADD COLUMN model_signature TEXT NOT NULL DEFAULT ''"
                )
            if "measurements_json" not in baseline_columns:
                db.execute(
                    "ALTER TABLE preflight_baselines ADD COLUMN measurements_json TEXT"
                )

    @contextmanager
    def _connect(self) -> Iterator[sqlite3.Connection]:
        db = sqlite3.connect(self.path, timeout=10)
        try:
            yield db
            db.commit()
        except Exception:
            db.rollback()
            raise
        finally:
            db.close()

    def issue_badge(self, crew_id: str) -> str:
        code = secrets.token_urlsafe(BADGE_BYTES)
        return self._issue_credential(crew_id, code)

    def issue_mission_number(self, crew_id: str) -> str:
        number = f"{secrets.randbelow(10 ** MISSION_NUMBER_DIGITS):0{MISSION_NUMBER_DIGITS}d}"
        return self._issue_credential(crew_id, number)

    def _issue_credential(self, crew_id: str, code: str) -> str:
        with self._connect() as db:
            db.execute(
                """UPDATE badges SET revoked_at = CURRENT_TIMESTAMP
                   WHERE crew_id = ? AND revoked_at IS NULL""",
                (crew_id,),
            )
            db.execute(
                "INSERT INTO badges (token_hash, crew_id) VALUES (?, ?)",
                (_badge_digest(code), crew_id),
            )
        self._revoke_sessions_for_crew(crew_id)
        return code

    def authenticate_badge(self, code: str) -> str | None:
        if not code or len(code) > 128:
            return None
        with self._connect() as db:
            row = db.execute(
                "SELECT crew_id FROM badges WHERE token_hash = ? AND revoked_at IS NULL",
                (_badge_digest(code),),
            ).fetchone()
        return row[0] if row else None

    def revoke_badges(self, crew_id: str) -> int:
        with self._connect() as db:
            cursor = db.execute(
                """UPDATE badges SET revoked_at = CURRENT_TIMESTAMP
                   WHERE crew_id = ? AND revoked_at IS NULL""",
                (crew_id,),
            )
            count = cursor.rowcount
        self._revoke_sessions_for_crew(crew_id)
        return count

    def set_preflight_baseline(
        self,
        crew_id: str,
        score_percent: float,
        model_signature: str,
        measurements: dict[str, float] | None = None,
    ) -> None:
        if not math.isfinite(score_percent) or not 0 <= score_percent <= 100:
            raise ValueError("Preflight B-score must be a percentage from 0 to 100.")
        if not model_signature:
            raise ValueError("A model signature is required for baseline comparison.")
        measurements_json = (
            json.dumps(measurements, separators=(",", ":"))
            if measurements is not None else None
        )
        with self._connect() as db:
            db.execute(
                """INSERT INTO preflight_baselines
                   (crew_id, score, model_signature, measurements_json)
                   VALUES (?, ?, ?, ?)
                   ON CONFLICT(crew_id) DO UPDATE SET
                       score = excluded.score,
                       model_signature = excluded.model_signature,
                       measurements_json = COALESCE(
                           excluded.measurements_json,
                           preflight_baselines.measurements_json
                       ),
                       recorded_at = CURRENT_TIMESTAMP""",
                (crew_id, score_percent, model_signature, measurements_json),
            )

    def preflight_measurements_for_crew(self, crew_id: str) -> dict[str, float] | None:
        with self._connect() as db:
            row = db.execute(
                """SELECT measurements_json FROM preflight_baselines
                   WHERE crew_id = ?""",
                (crew_id,),
            ).fetchone()
        if not row or not row[0]:
            return None
        measurements = json.loads(row[0])
        if not isinstance(measurements, dict):
            raise ValueError("Stored preflight measurements are invalid.")
        return measurements

    def preflight_baseline_for_crew(
        self,
        crew_id: str,
    ) -> tuple[float, str, str] | None:
        with self._connect() as db:
            row = db.execute(
                """SELECT score, recorded_at, model_signature
                   FROM preflight_baselines WHERE crew_id = ?""",
                (crew_id,),
            ).fetchone()
        return (float(row[0]), str(row[1]), str(row[2])) if row else None

    def create_session(self, crew_id: str, credential: str) -> str:
        token = secrets.token_urlsafe(32)
        with self._lock:
            self._purge_sessions()
            self._sessions[token] = (
                crew_id,
                time.monotonic() + SESSION_TTL_SECONDS,
                _badge_digest(credential),
            )
        return token

    def crew_for_session(self, token: str | None) -> str | None:
        if not token:
            return None
        with self._lock:
            session = self._sessions.get(token)
            if session is None:
                return None
            crew_id, expires_at, credential_hash = session
            if expires_at <= time.monotonic():
                del self._sessions[token]
                return None
        with self._connect() as db:
            row = db.execute(
                """SELECT 1 FROM badges
                   WHERE token_hash = ? AND crew_id = ? AND revoked_at IS NULL""",
                (credential_hash, crew_id),
            ).fetchone()
        if row is None:
            self.revoke_session(token)
            return None
        return crew_id

    def revoke_session(self, token: str | None) -> None:
        if token:
            with self._lock:
                self._sessions.pop(token, None)

    def scan_is_limited(self, client: str) -> bool:
        now = time.monotonic()
        with self._lock:
            recent = [
                attempt for attempt in self._login_failures.get(client, [])
                if attempt > now - LOGIN_WINDOW_SECONDS
            ]
            if recent:
                self._login_failures[client] = recent
            else:
                self._login_failures.pop(client, None)
            return len(recent) >= LOGIN_ATTEMPT_LIMIT

    def record_scan_failure(self, client: str) -> None:
        with self._lock:
            self._login_failures.setdefault(client, []).append(time.monotonic())

    def clear_scan_failures(self, client: str) -> None:
        with self._lock:
            self._login_failures.pop(client, None)

    def _revoke_sessions_for_crew(self, crew_id: str) -> None:
        with self._lock:
            self._sessions = {
                token: session for token, session in self._sessions.items()
                if session[0] != crew_id
            }

    def _purge_sessions(self) -> None:
        now = time.monotonic()
        self._sessions = {
            token: session for token, session in self._sessions.items()
            if session[1] > now
        }
