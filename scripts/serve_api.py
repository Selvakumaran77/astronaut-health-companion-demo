"""
healthmon HTTP API
==================

A dependency-free, authenticated JSON API and astronaut report UI.

    py scripts/serve_api.py                 # http://127.0.0.1:8000
    py scripts/serve_api.py --port 9000

Public: GET /, GET /health, GET /api/agent/news, POST /api/mission-number,
POST /api/scan. The opt-in localhost-only wearable demo also exposes its
four selected, downsampled research-participant reports.
Authenticated: GET /api/me/report and the existing crew, reading, alert,
summary, notification, model and prediction endpoints. Each account is scoped
to one crew ID.

The model predicts the probability that a crew member will be in an elevated
state (watch/alert) on the following mission day, using only current and past data.
"""

from __future__ import annotations

import argparse
import csv
import html
import http.client
import hashlib
import json
import math
import os
import re
import sys
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from http.cookies import CookieError, SimpleCookie
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse
from urllib.request import Request as URLRequest, urlopen

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "src"))

from healthmon.alerts import RULES, evaluate_row, summarize  # noqa: E402
from healthmon.auth import AuthStore, SESSION_TTL_SECONDS  # noqa: E402
from healthmon.companion import CompanionStore  # noqa: E402
from healthmon.features import BASE_FIELDS, build_dataset  # noqa: E402
from healthmon.model import LogisticRegression, top_features  # noqa: E402
from healthmon.notifications import build_notifications, summarize_notifications  # noqa: E402
from healthmon.wearable import (  # noqa: E402
    health_indicator_catalog,
    load_wearable_dataset,
    participant_roster,
)

DEFAULT_DATA = os.path.join(ROOT, "data", "synthetic", "crew_vitals_simulated.csv")
DEFAULT_MODEL = os.path.join(ROOT, "models", "risk_model.json")
DEFAULT_WEARABLE_DATASET = os.path.abspath(os.path.join(
    ROOT,
    os.pardir,
    os.pardir,
    "wearable-device-dataset-from-induced-stress-and-structured-exercise-sessions-1.0.1",
))
LOGIN_PAGE = os.path.join(ROOT, "app", "astronaut.html")
PROFILES = os.path.join(ROOT, "data", "crew_profiles.json")
DEFAULT_AUTH_DB = os.path.join(ROOT, "data", "astronaut_badges.sqlite3")
PUBLIC_DEMO_DATA_SHA256 = "02d73b9913578944e6d69daf9f81f8d408362028e2f4190ebb0de554084abb12"
PUBLIC_DEMO_PROFILES_SHA256 = "a08f36ddfc4f4dbcefad31c9d263d364250f2c447a98de29e15c6eba32d873b6"
NEWS_FEEDS = {
    "sports": {
        "source": "BBC Sport",
        "url": "https://feeds.bbci.co.uk/sport/rss.xml",
    },
    "entertainment": {
        "source": "BBC Entertainment & Arts",
        "url": "https://feeds.bbci.co.uk/news/entertainment_and_arts/rss.xml",
    },
}
NEWS_MAX_AGE = timedelta(hours=48)


def _normalized_file_sha256(path: str) -> str:
    with open(path, "rb") as file:
        content = file.read().replace(b"\r\n", b"\n")
    return hashlib.sha256(content).hexdigest()


ADVICE_BY_FIELD = {
    "spo2_pct": "Repeat the measurement only as allowed by mission protocol; promptly contact the flight surgeon if it remains low or symptoms occur.",
    "heart_rate_bpm": "Repeat a resting measurement under mission protocol and report persistent elevation or concerning symptoms to the flight surgeon.",
    "body_temp_c": "Verify the reading with an approved device and report persistent elevation or fever symptoms to the flight surgeon.",
    "crp_mg_per_L": "CRP requires clinical interpretation; contact the flight surgeon for review and do not self-treat based on this report.",
    "wbc_1e9_per_L": "White blood cell results require clinical interpretation; contact the flight surgeon for review.",
    "sleep_hours": "Discuss persistent reduced sleep with the flight surgeon and follow mission-approved sleep and workload procedures.",
    "mood_score_1_10": "If low mood persists or worsens, use the mission's established confidential behavioral-health support channel.",
    "cabin_co2_ppm": "Report the cabin reading to mission control for environmental review and follow mission procedures.",
}

NUMERIC = {
    "mission_day", "heart_rate_bpm", "systolic_bp_mmHg", "diastolic_bp_mmHg",
    "spo2_pct", "resp_rate_bpm", "body_temp_c", "sleep_hours", "mood_score_1_10",
    "cognitive_score_0_100", "bone_density_pct_change", "muscle_mass_pct_change",
    "wbc_1e9_per_L", "crp_mg_per_L", "radiation_dose_mSv_day",
    "radiation_dose_cumulative_mSv", "cabin_co2_ppm", "latent_stress_index",
}


def coerce(row: dict) -> dict:
    for k in list(row.keys()):
        if k in NUMERIC:
            try:
                row[k] = float(row[k])
            except (TypeError, ValueError):
                pass
    return row


def load_rows(path: str) -> list[dict]:
    with open(path, newline="", encoding="utf-8") as f:
        return [coerce(r) for r in csv.DictReader(f)]


def fetch_news(topic: str, *, now: datetime | None = None) -> dict:
    """Fetch recent, source-linked headlines from a fixed public RSS feed."""
    feed = NEWS_FEEDS.get(topic)
    if feed is None:
        raise ValueError("Unsupported news topic.")

    request = URLRequest(
        feed["url"],
        headers={"User-Agent": "SpaceAppsHealthMonitor/1.0"},
    )
    with urlopen(request, timeout=5) as response:
        payload = response.read(1_000_001)
    if len(payload) > 1_000_000:
        raise ValueError("News feed response exceeded the size limit.")

    root = ET.fromstring(payload)
    fetched_at = now or datetime.now(timezone.utc)
    if fetched_at.tzinfo is None:
        fetched_at = fetched_at.replace(tzinfo=timezone.utc)
    articles = []
    for item in root.findall(".//item"):
        title = (item.findtext("title") or "").strip()
        link = (item.findtext("link") or "").strip()
        published = (item.findtext("pubDate") or "").strip()
        try:
            published_at = parsedate_to_datetime(published)
        except (TypeError, ValueError, OverflowError):
            continue
        if published_at.tzinfo is None:
            published_at = published_at.replace(tzinfo=timezone.utc)
        published_at = published_at.astimezone(timezone.utc)
        age = fetched_at.astimezone(timezone.utc) - published_at
        parsed_link = urlparse(link)
        if (
            not title
            or age < timedelta(0)
            or age > NEWS_MAX_AGE
            or parsed_link.scheme != "https"
            or not parsed_link.hostname
            or not (
                parsed_link.hostname == "bbc.co.uk"
                or parsed_link.hostname.endswith(".bbc.co.uk")
                or parsed_link.hostname == "bbc.com"
                or parsed_link.hostname.endswith(".bbc.com")
            )
        ):
            continue
        description = html.unescape(
            item.findtext("description") or ""
        )
        description = re.sub(r"<[^>]*>", " ", description)
        description = re.sub(r"\s+", " ", description).strip()[:420]
        articles.append({
            "title": title,
            "url": link,
            "published": published_at.isoformat(),
            "summary": description,
        })
    articles.sort(key=lambda article: article["published"], reverse=True)

    return {
        "topic": topic,
        "source": feed["source"],
        "fetched_at": fetched_at.astimezone(timezone.utc).isoformat(),
        "max_age_hours": int(NEWS_MAX_AGE.total_seconds() / 3600),
        "articles": articles[:6],
    }


class App:
    """Holds the loaded data + model and the request handlers."""

    def __init__(
        self,
        data_path: str,
        model_path: str,
        users_db: str,
        public_demo: bool = False,
        wearable_dataset: str | None = None,
    ):
        if public_demo and wearable_dataset is not None:
            raise ValueError("Choose either the synthetic or wearable demo mode.")
        self.rows = load_rows(data_path)
        if public_demo:
            data_signature = _normalized_file_sha256(data_path)
            profiles_signature = _normalized_file_sha256(PROFILES)
            if (
                os.path.abspath(data_path) != os.path.abspath(DEFAULT_DATA)
                or data_signature != PUBLIC_DEMO_DATA_SHA256
                or profiles_signature != PUBLIC_DEMO_PROFILES_SHA256
            ):
                raise ValueError(
                    "Public-demo reports are permitted only with the unchanged "
                    "checked-in synthetic crew dataset and profiles."
                )
        self.public_demo = public_demo
        self.wearable_demo = wearable_dataset is not None
        self.wearable_participants = (
            load_wearable_dataset(wearable_dataset)
            if self.wearable_demo else {}
        )
        self.model = LogisticRegression.load(model_path)
        with open(model_path, "rb") as model_file:
            self.model_signature = hashlib.sha256(model_file.read()).hexdigest()
        self.auth = AuthStore(users_db)
        self.companion = CompanionStore(users_db)
        self.rows.extend(self.companion.all_measurements())
        with open(PROFILES, encoding="utf-8") as f:
            self.profiles = json.load(f)
        self.features = list(self.model.feature_names)
        # training mean per raw indicator, used to impute partial readings
        self._base_mean = {
            name: self.model.mean[i]
            for i, name in enumerate(self.model.feature_names)
            if name in BASE_FIELDS
        }

    def impute(self, rows: list[dict]) -> list[dict]:
        """Fill missing raw indicators with the training mean so that partial
        readings (e.g. an ad-hoc POST) score sensibly instead of treating the
        absent value as a real zero."""
        out = []
        for r in rows:
            r = dict(r)
            for b in BASE_FIELDS:
                if r.get(b, None) in (None, ""):
                    r[b] = self._base_mean.get(b, 0.0)
            out.append(r)
        return out

    # -- helpers -----------------------------------------------------------
    def by_crew(self) -> dict[str, list[dict]]:
        out: dict[str, list[dict]] = {}
        for r in self.rows:
            out.setdefault(r["crew_id"], []).append(r)
        for seq in out.values():
            seq.sort(key=lambda r: float(r.get("mission_day", 0)))
        return out

    def score_rows(self, rows: list[dict]) -> list[dict]:
        """Return per-row next-day risk using only current/past data."""
        if not rows:
            return []
        ds = build_dataset(self.impute(rows), with_target=False)
        probs = self.model.predict_proba(ds["X"])
        out = []
        for meta, p, feats in zip(ds["meta"], probs, ds["X"]):
            out.append({
                "crew_id": meta["crew_id"],
                "mission_day": meta["mission_day"],
                "date_utc": meta["date_utc"],
                "rule_level": meta["level"],
                "risk_probability": round(p, 4),
                "risk_level": "elevated" if p >= self.model.threshold else "low",
                "top_contributors": self._contributors(feats),
            })
        return out

    def _contributors(self, feats: dict, k: int = 3) -> list[dict]:
        """Largest standardized feature*weight contributions for one reading.

        Only features actually present in the reading are considered, so an
        omitted value never shows up as a spurious driver.
        """
        contribs = []
        for idx, (name, w) in enumerate(zip(self.model.feature_names, self.model.weights)):
            if feats.get(name, None) in (None, ""):
                continue
            try:
                v = float(feats[name])
            except (TypeError, ValueError):
                continue
            z = (v - self.model.mean[idx]) / (self.model.std[idx] or 1.0)
            contribs.append({"feature": name, "contribution": round(w * z, 4)})
        contribs.sort(key=lambda c: abs(c["contribution"]), reverse=True)
        return contribs[:k]

    # -- endpoint payloads -------------------------------------------------
    def model_info(self) -> dict:
        return {
            "algorithm": "logistic_regression (L2, standardized features)",
            "task": self.model.metrics.get("task")
                    or "predict elevated (watch/alert) risk on the next mission day",
            "threshold": self.model.threshold,
            "created": self.model.created,
            "n_features": len(self.model.feature_names),
            "feature_names": self.model.feature_names,
            "metrics": self.model.metrics,
            "top_features": top_features(self.model, 12),
        }

    def crew(self, crew_id: str | None = None) -> list[dict]:
        out = []
        for crew, seq in sorted(self.by_crew().items()):
            if crew_id and crew != crew_id:
                continue
            latest = seq[-1]
            scored = self.score_rows(seq)[-1]
            out.append({
                "crew_id": crew,
                "name": self.profiles.get(crew, {}).get("name", crew),
                "role": self.profiles.get(crew, {}).get("role", ""),
                "readings": len(seq),
                "latest_date": latest["date_utc"],
                "latest_mission_day": latest["mission_day"],
                "rule_level": evaluate_row(latest, self.profiles).level,
                "reasons": evaluate_row(latest, self.profiles).messages,
                "next_day_risk_probability": scored["risk_probability"],
                "next_day_risk_level": scored["risk_level"],
            })
        return out

    def readings(self, crew: str | None, limit: int) -> list[dict]:
        rows = self.rows
        if crew:
            rows = [r for r in rows if r["crew_id"] == crew]
        rows = sorted(rows, key=lambda r: (r["crew_id"], -float(r.get("mission_day", 0))))
        return rows[:limit]

    def weekly_summary(self, crew_id: str) -> dict:
        rows = self.by_crew().get(crew_id, [])
        if not rows:
            raise KeyError(crew_id)
        latest_day = float(rows[-1].get("mission_day", 0))
        window = [
            row for row in rows
            if latest_day - 6 <= float(row.get("mission_day", 0)) <= latest_day
        ]
        predictions = self.score_rows(window)
        fields = (
            "heart_rate_bpm",
            "spo2_pct",
            "sleep_hours",
            "body_temp_c",
        )
        averages = {}
        for field in fields:
            values = []
            for row in window:
                try:
                    value = float(row[field])
                except (KeyError, TypeError, ValueError):
                    continue
                values.append(value)
            if values:
                averages[field] = round(sum(values) / len(values), 2)
        status_counts = {"normal": 0, "watch": 0, "alert": 0}
        for row in window:
            status_counts[evaluate_row(row, self.profiles).level] += 1
        mission_day = int(latest_day)
        mission_phase = (
            "Early mission" if mission_day <= 30
            else "Long-duration mission" if mission_day <= 150
            else "Return preparation"
        )
        return {
            "mission_phase": mission_phase,
            "window": "latest 7 recorded mission days",
            "readings_count": len(window),
            "from_mission_day": int(float(window[0].get("mission_day", 0))),
            "to_mission_day": mission_day,
            "average_indicators": averages,
            "rule_status_counts": status_counts,
            "average_model_risk_probability": round(
                sum(item["risk_probability"] for item in predictions) / len(predictions),
                4,
            ) if predictions else None,
            "latest_model_risk_probability": (
                predictions[-1]["risk_probability"] if predictions else None
            ),
            "illustrative_only": True,
        }

    def report_history(self, crew_id: str) -> list[dict]:
        crew_rows = self.by_crew().get(crew_id, [])
        predictions = self.score_rows(crew_rows)
        return [
            {
                **{
                    key: value
                    for key, value in row.items()
                    if key != "latent_stress_index"
                },
                "risk_probability": prediction["risk_probability"],
            }
            for row, prediction in zip(crew_rows, predictions)
        ]

    def alerts(self, level: str | None, crew: str | None) -> list[dict]:
        out = []
        for r in self.rows:
            if crew and r["crew_id"] != crew:
                continue
            f = evaluate_row(r, self.profiles)
            if f.level == "normal":
                continue
            if level and f.level != level:
                continue
            out.append({
                "crew_id": r["crew_id"], "date_utc": r["date_utc"],
                "mission_day": r["mission_day"], "level": f.level, "reasons": f.messages,
            })
        out.sort(key=lambda r: ({"alert": 0, "watch": 1}[r["level"]], r["crew_id"], r["mission_day"]))
        return out

    def report(self, crew_id: str) -> dict:
        rows = self.by_crew().get(crew_id, [])
        if not rows:
            raise KeyError(crew_id)
        latest = rows[-1]
        finding = evaluate_row(latest, self.profiles)
        predictions = self.score_rows(rows)
        prediction = predictions[-1]
        stored_baseline = self.auth.preflight_baseline_for_crew(crew_id)
        baseline_matches_model = (
            stored_baseline is not None
            and stored_baseline[2] == self.model_signature
        )
        preflight_baseline = stored_baseline if baseline_matches_model else None
        personal_baseline = preflight_baseline[0] / 100 if preflight_baseline else None
        personal_safe_line = min(
            self.model.threshold,
            personal_baseline if personal_baseline is not None else self.model.threshold,
        )
        rising_line = personal_safe_line * 0.75
        if prediction["risk_probability"] >= personal_safe_line or finding.level == "alert":
            indicator = "above_safe"
            if finding.level == "alert":
                indicator_label = "Above safe line — rule alert"
            elif personal_baseline is not None and prediction["risk_probability"] >= personal_baseline:
                indicator_label = "Above preflight B-score"
            else:
                indicator_label = "Above trained-model safe line"
        elif prediction["risk_probability"] >= rising_line or finding.level == "watch":
            indicator = "rising"
            indicator_label = (
                "Rising toward preflight B-score"
                if personal_baseline is not None else "Rising toward model safe line"
            )
        else:
            indicator = "safe"
            indicator_label = (
                "Below preflight B-score"
                if personal_baseline is not None else "Below model safe line"
            )

        personal_thresholds = self.profiles.get(crew_id, {}).get("thresholds", [])
        override_columns = {rule["col"] for rule in personal_thresholds}
        thresholds = [rule for rule in RULES if rule["col"] not in override_columns]
        thresholds.extend(personal_thresholds)
        flags: list[dict] = []
        seen: set[str] = set()
        for rule in thresholds:
            value = latest.get(rule["col"])
            if value in (None, ""):
                continue
            try:
                number = float(value)
            except (TypeError, ValueError):
                continue
            hit = number < rule["val"] if rule["op"] == "<" else number > rule["val"]
            if hit and rule["col"] not in seen:
                seen.add(rule["col"])
                flags.append(rule)
        advice = [ADVICE_BY_FIELD.get(rule["col"],
                  "Review this reading with the flight surgeon and follow mission medical protocols.")
                  for rule in flags]
        if indicator == "above_safe":
            advice.append("The above-safe indicator was triggered by the risk score or a rule alert. Contact an Earth-based doctor or flight surgeon promptly using mission protocols and share this report for personalized review.")
        elif indicator == "rising":
            advice.append("This result is approaching or crossing a configured review threshold. Recheck as directed by mission protocol and discuss the trend with the flight surgeon.")
        elif not advice:
            advice.append("Continue scheduled monitoring, compare against your personal baseline, and follow mission-approved health guidance.")

        test_metrics = self.model.metrics.get("test", {})
        return {
            "crew_id": crew_id,
            "profile": {
                "name": self.profiles.get(crew_id, {}).get("name", crew_id),
                "role": self.profiles.get(crew_id, {}).get("role", ""),
            },
            "latest": {key: value for key, value in latest.items()
                       if key != "latent_stress_index"},
            "status": {"level": finding.level, "reasons": finding.messages},
            "prediction": {
                "risk_probability": prediction["risk_probability"],
                "risk_level": prediction["risk_level"],
                "threshold": self.model.threshold,
                "target": "elevated rule-based status on the next mission day",
            },
            "risk_indicator": {
                "state": indicator,
                "label": indicator_label,
                "personal_baseline": (
                    round(personal_baseline, 4) if personal_baseline is not None else None
                ),
                "baseline_recorded_at": (
                    stored_baseline[1] if stored_baseline else None
                ),
                "safe_line": round(personal_safe_line, 4),
                "rising_line": round(rising_line, 4),
                "baseline_set": preflight_baseline is not None,
                "baseline_stale": stored_baseline is not None and not baseline_matches_model,
                "preflight_measurements": self.auth.preflight_measurements_for_crew(
                    crew_id
                ) if baseline_matches_model else None,
                "flight_surgeon_follow_up": indicator != "safe",
                "basis": "Earth-side preflight B-score (when recorded), model threshold, and current rule status; illustrative, not clinically validated",
            },
            "model_test_auc": test_metrics.get("roc_auc"),
            "advice": advice,
            "disclaimer": "Synthetic-data demonstration, not clinically validated or diagnostic. Follow mission protocols and consult the flight surgeon.",
        }


def make_handler(app: App):
    class Handler(BaseHTTPRequestHandler):
        server_version = "healthmon/1.0"

        def log_message(self, fmt, *args):  # quieter, single-line
            sys.stderr.write("%s - %s\n" % (self.address_string(), fmt % args))

        def _send(self, code: int, body: bytes, ctype: str, headers: dict | None = None):
            self.send_response(code)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store, no-cache, must-revalidate, max-age=0")
            self.send_header("Pragma", "no-cache")
            self.send_header("Expires", "0")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("X-Frame-Options", "DENY")
            self.send_header("Referrer-Policy", "same-origin")
            self.send_header(
                "Content-Security-Policy",
                "default-src 'self'; script-src 'self' 'unsafe-inline'; "
                "style-src 'self' 'unsafe-inline'; img-src 'self' data:; media-src 'self'; "
                "connect-src 'self'; frame-ancestors 'none'",
            )
            for name, value in (headers or {}).items():
                self.send_header(name, value)
            self.end_headers()
            if self.command != "HEAD":
                self.wfile.write(body)

        def _json(self, obj, code: int = 200, headers: dict | None = None):
            self._send(code, json.dumps(obj, indent=2).encode("utf-8"),
                       "application/json; charset=utf-8", headers)

        def _token(self) -> str | None:
            cookie = SimpleCookie()
            try:
                cookie.load(self.headers.get("Cookie", ""))
            except CookieError:
                return None
            morsel = cookie.get("healthmon_session")
            return morsel.value if morsel else None

        def _crew_id(self) -> str | None:
            return app.auth.crew_for_session(self._token())

        def _body(self):
            try:
                length = int(self.headers.get("Content-Length") or 0)
            except ValueError:
                return None, "invalid content length"
            if length < 0 or length > 1_000_000:
                return None, "request body too large"
            if self.headers.get_content_type() != "application/json":
                return None, "Content-Type must be application/json"
            try:
                return json.loads(self.rfile.read(length) or b"{}"), None
            except (json.JSONDecodeError, UnicodeDecodeError) as exc:
                return None, f"invalid JSON: {exc}"

        def do_OPTIONS(self):
            self._send(204, b"", "text/plain")

        def do_GET(self):
            u = urlparse(self.path)
            path, q = u.path, parse_qs(u.query)

            if path == "/favicon.ico":
                # tiny inline SVG favicon (a heartbeat pulse) so the console stays clean
                svg = (b'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 32 32">'
                       b'<rect width="32" height="32" rx="7" fill="#0b1020"/>'
                       b'<path d="M4 17h6l3-8 4 14 3-6h8" fill="none" stroke="#5ea0ff" '
                       b'stroke-width="2.5" stroke-linejoin="round" stroke-linecap="round"/></svg>')
                return self._send(200, svg, "image/svg+xml")

            if path in ("/", "/index.html", "/dashboard.html", "/astronaut.html"):
                if os.path.exists(LOGIN_PAGE):
                    with open(LOGIN_PAGE, "rb") as f:
                        return self._send(200, f.read(), "text/html; charset=utf-8")
                return self._send(404, b"astronaut.html is missing",
                                  "text/plain; charset=utf-8")

            if path == "/api":
                return self._json({
                    "service": "Crew Health Monitor API",
                    "public_endpoints": [
                        "/health", "/api/astronauts", "/api/agent/news",
                        "/api/wearable/report/{participant_id}",
                        "/api/mission-number", "/api/scan"
                    ],
                    "authenticated_endpoints": ["/api/me/report", "/model", "/crew",
                                                "/readings", "/alerts", "/summary",
                                                "/notifications", "/predict"],
                })
            if path == "/health":
                return self._json({"status": "ok"})

            if path == "/api/agent/news":
                topic = (q.get("topic") or [""])[0]
                if topic not in NEWS_FEEDS:
                    return self._json(
                        {"error": "Choose sports or entertainment headlines."}, 400
                    )
                try:
                    return self._json(fetch_news(topic))
                except (
                    http.client.HTTPException,
                    OSError,
                    ET.ParseError,
                    ValueError,
                ) as exc:
                    sys.stderr.write(f"news feed request failed for {topic}: {exc}\n")
                    return self._json(
                        {"error": "Live headlines are temporarily unavailable. Try again later."},
                        502,
                    )

            if path == "/api/astronauts":
                if app.wearable_demo:
                    return self._json({
                        "astronauts": participant_roster(app.wearable_participants),
                        "health_indicators": health_indicator_catalog(),
                        "reports_public": True,
                        "participant_demo": True,
                    })
                astronauts = []
                latest_by_crew = app.by_crew() if app.public_demo else {}
                for crew_id, profile in sorted(app.profiles.items()):
                    astronaut = {
                        "crew_id": crew_id,
                        "name": profile.get("name", crew_id),
                        "role": profile.get("role", ""),
                    }
                    rows = latest_by_crew.get(crew_id, [])
                    if rows:
                        latest = rows[-1]
                        astronaut["latest"] = {
                            key: latest.get(key)
                            for key in (
                                "date_utc",
                                "mission_day",
                                "heart_rate_bpm",
                                "body_temp_c",
                                "spo2_pct",
                            )
                        }
                    astronauts.append(astronaut)
                return self._json({
                    "astronauts": astronauts,
                    "reports_public": app.public_demo,
                })

            if path == "/api/demo/doctor-dashboard":
                if not app.public_demo:
                    return self._json({"error": "not found", "path": path}, 404)
                crew_summaries = []
                for crew_id, profile in sorted(app.profiles.items()):
                    report = app.report(crew_id)
                    crew_summaries.append({
                        "crew_id": crew_id,
                        "name": profile.get("name", crew_id),
                        "role": profile.get("role", ""),
                        "risk_indicator": report["risk_indicator"],
                        "status": report["status"],
                        "latest": report["latest"],
                        "weekly_summary": app.weekly_summary(crew_id),
                        "history": app.report_history(crew_id)[-7:],
                    })
                return self._json({
                    "data_mode": "unchanged_synthetic_public_demo",
                    "crew": crew_summaries,
                    "clinical_use": False,
                    "note": "Synthetic demonstration records only; not a clinician console and not clinical data.",
                })

            if path.startswith("/api/wearable/report/"):
                if not app.wearable_demo:
                    return self._json({"error": "not found", "path": path}, 404)
                participant_id = path.removeprefix("/api/wearable/report/")
                participant = app.wearable_participants.get(participant_id)
                if participant is None:
                    return self._json({"error": "Unknown study participant."}, 404)
                return self._json(participant)

            if path.startswith("/api/demo/report/"):
                if not app.public_demo:
                    return self._json({"error": "not found", "path": path}, 404)
                crew_id = path.removeprefix("/api/demo/report/")
                if crew_id not in app.profiles:
                    return self._json({"error": "Unknown astronaut."}, 404)
                try:
                    report = app.report(crew_id)
                    report["history"] = app.report_history(crew_id)
                    report["weekly_summary"] = app.weekly_summary(crew_id)
                    return self._json(report)
                except KeyError:
                    return self._json(
                        {"error": "No readings are available for this astronaut."},
                        404,
                    )

            if path == "/assets/videos/background.mp4":
                video_path = os.path.join(
                    ROOT, "app", "assets", "videos", "background.mp4"
                )
                if not os.path.isfile(video_path):
                    return self._send(404, b"background video is missing",
                                      "text/plain; charset=utf-8")
                with open(video_path, "rb") as video_file:
                    return self._send(200, video_file.read(), "video/mp4")

            if path == "/assets/images/card_background.jpg":
                image_path = os.path.join(
                    ROOT, "app", "assets", "images", "card_background.jpg"
                )
                if not os.path.isfile(image_path):
                    return self._send(404, b"astronaut card background is missing",
                                      "text/plain; charset=utf-8")
                with open(image_path, "rb") as image_file:
                    return self._send(200, image_file.read(), "image/jpeg")

            if path == "/api/scan":
                return self._json({"error": "method not allowed"}, 405)

            crew_id = self._crew_id()
            if not crew_id:
                return self._json({"error": "Authentication required."}, 401)

            if path == "/api/me/report":
                try:
                    report = app.report(crew_id)
                    report["history"] = app.report_history(crew_id)
                    report["weekly_summary"] = app.weekly_summary(crew_id)
                    report["companion"] = app.companion.state(
                        crew_id,
                        latest_measurement_date=str(
                            app.by_crew()[crew_id][-1]["date_utc"]
                        ),
                    )
                    report["local_handoffs"] = app.companion.handoffs_for_crew(
                        crew_id
                    )
                    return self._json(report)
                except KeyError:
                    return self._json({"error": "No readings are available for this account."}, 404)
            if path == "/model":
                return self._json(app.model_info())
            if path == "/crew":
                return self._json({"crew": app.crew(crew_id)})
            if path == "/readings":
                requested_crew = (q.get("crew") or [crew_id])[0]
                if requested_crew != crew_id:
                    return self._json({"error": "Access denied."}, 403)
                try:
                    limit = max(1, min(500, int((q.get("limit") or ["50"])[0])))
                except ValueError:
                    return self._json({"error": "limit must be an integer"}, 400)
                readings = app.readings(crew_id, limit)
                return self._json({"count": len(readings), "readings": readings})
            if path == "/alerts":
                level = (q.get("level") or [None])[0]
                requested_crew = (q.get("crew") or [crew_id])[0]
                if requested_crew != crew_id:
                    return self._json({"error": "Access denied."}, 403)
                items = app.alerts(level, crew_id)
                return self._json({"count": len(items), "alerts": items})
            if path == "/summary":
                own_rows = app.by_crew().get(crew_id, [])
                return self._json(summarize(own_rows, app.profiles))
            if path == "/notifications":
                requested_crew = (q.get("crew") or [crew_id])[0]
                if requested_crew != crew_id:
                    return self._json({"error": "Access denied."}, 403)
                own_rows = app.by_crew().get(crew_id, [])
                typ = (q.get("type") or [None])[0]
                try:
                    limit = max(1, min(500, int((q.get("limit") or ["50"])[0])))
                except ValueError:
                    return self._json({"error": "limit must be an integer"}, 400)
                events = build_notifications(own_rows, app.profiles)
                if typ:
                    events = [e for e in events if e["type"] == typ]
                recent = list(reversed(events))[:limit]  # newest first
                return self._json({
                    "summary": summarize_notifications(own_rows, app.profiles),
                    "count": len(events),
                    "notifications": recent,
                })
            if path == "/predict":
                requested_crew = (q.get("crew") or [crew_id])[0]
                if requested_crew != crew_id:
                    return self._json({"error": "Access denied."}, 403)
                seq = app.by_crew().get(crew_id)
                if not seq:
                    return self._json({"error": "No readings are available for this account."}, 404)
                return self._json({"crew_id": crew_id, "predictions": app.score_rows(seq)})

            return self._json({"error": "not found", "path": path}, 404)

        def do_POST(self):
            u = urlparse(self.path)
            if u.path not in (
                "/api/scan", "/api/mission-number", "/api/logout", "/predict",
                "/api/me/checkin", "/api/me/readings", "/api/me/emergency-report",
                "/api/me/mock-handoff-ack",
            ):
                return self._json({"error": "not found", "path": u.path}, 404)
            body, error = self._body()
            if error:
                return self._json({"error": error}, 400)

            if u.path in ("/api/scan", "/api/mission-number"):
                client = self.client_address[0]
                if app.auth.scan_is_limited(client):
                    return self._json({"error": "Too many sign-in attempts. Try again in 15 minutes."},
                                      429, {"Retry-After": "900"})
                credential_field = (
                    "mission_number" if u.path == "/api/mission-number" else "badge_code"
                )
                code = body.get(credential_field) if isinstance(body, dict) else None
                valid_credential = isinstance(code, str) and bool(code) and len(code) <= 128
                valid_number = (
                    valid_credential
                    and (
                        u.path != "/api/mission-number"
                        or (
                            len(code) == 20
                            and code.isascii()
                            and code.isdigit()
                        )
                    )
                )
                if not valid_number:
                    app.auth.record_scan_failure(client)
                    return self._json({"error": "Invalid mission number. Ask mission support for help."}, 401)
                crew_id = app.auth.authenticate_badge(code)
                requested_crew = body.get("crew_id") if isinstance(body, dict) else None
                if (
                    not crew_id
                    or (
                        u.path == "/api/mission-number"
                        and requested_crew != crew_id
                    )
                ):
                    app.auth.record_scan_failure(client)
                    return self._json({"error": "Invalid mission number. Ask mission support for help."}, 401)
                app.auth.clear_scan_failures(client)
                token = app.auth.create_session(crew_id, code)
                secure = "; Secure" if getattr(app, "secure_cookies", False) else ""
                return self._json(
                    {"authenticated": True},
                    headers={"Set-Cookie": f"healthmon_session={token}; Max-Age={SESSION_TTL_SECONDS}; Path=/; HttpOnly; SameSite=Strict{secure}"},
                )
            if u.path == "/api/logout":
                app.auth.revoke_session(self._token())
                return self._json(
                    {"authenticated": False},
                    headers={"Set-Cookie": "healthmon_session=; Max-Age=0; Path=/; HttpOnly; SameSite=Strict"},
                )

            crew_id = self._crew_id()
            if not crew_id:
                return self._json({"error": "Authentication required."}, 401)

            if u.path == "/api/me/checkin":
                if not isinstance(body, dict):
                    return self._json({"error": "A wellbeing check-in object is required."}, 400)
                expected = {
                    "sleep_hours", "exercise_minutes", "exercise_type", "stress_score"
                }
                if set(body) != expected:
                    return self._json({"error": "Provide sleep_hours, exercise_minutes, exercise_type, and stress_score only."}, 400)
                sleep_hours = body["sleep_hours"]
                exercise_minutes = body["exercise_minutes"]
                stress_score = body["stress_score"]
                exercise_type = body["exercise_type"]
                if (
                    isinstance(sleep_hours, bool)
                    or not isinstance(sleep_hours, (int, float))
                    or not 0 <= sleep_hours <= 24
                ):
                    return self._json({"error": "sleep_hours must be between 0 and 24."}, 400)
                if (
                    isinstance(exercise_minutes, bool)
                    or not isinstance(exercise_minutes, int)
                    or not 0 <= exercise_minutes <= 600
                ):
                    return self._json({"error": "exercise_minutes must be a whole number from 0 to 600."}, 400)
                if (
                    not isinstance(exercise_type, str)
                    or exercise_type not in {"aerobic", "strength", "mobility", "rest"}
                ):
                    return self._json({"error": "Choose aerobic, strength, mobility, or rest."}, 400)
                if (
                    isinstance(stress_score, bool)
                    or not isinstance(stress_score, int)
                    or not 1 <= stress_score <= 10
                ):
                    return self._json({"error": "stress_score must be a whole number from 1 to 10."}, 400)
                checkin = app.companion.save_checkin(
                    crew_id,
                    sleep_hours=float(sleep_hours),
                    exercise_minutes=exercise_minutes,
                    exercise_type=exercise_type,
                    stress_score=stress_score,
                )
                return self._json(
                    {
                        "checkin": checkin,
                        "companion": app.companion.state(
                            crew_id,
                            latest_measurement_date=str(
                                app.by_crew()[crew_id][-1]["date_utc"]
                            ),
                        ),
                    },
                    201,
                )

            if u.path == "/api/me/readings":
                if not isinstance(body, dict) or set(body) != set(BASE_FIELDS):
                    return self._json(
                        {
                            "error": (
                                "Provide exactly one numeric value for each of the "
                                "16 configured health indicators."
                            )
                        },
                        400,
                    )
                readings = {}
                for field in BASE_FIELDS:
                    value = body[field]
                    if (
                        isinstance(value, bool)
                        or not isinstance(value, (int, float))
                        or not math.isfinite(float(value))
                    ):
                        return self._json(
                            {"error": f"{field} must be a finite number."},
                            400,
                        )
                    readings[field] = float(value)
                crew_rows = app.by_crew().get(crew_id, [])
                if not crew_rows:
                    return self._json(
                        {"error": "No mission history is available for this account."},
                        404,
                    )
                latest = crew_rows[-1]
                mission_day = int(float(latest.get("mission_day", 0))) + 1
                try:
                    next_date = datetime.strptime(
                        str(latest["date_utc"]), "%Y-%m-%d"
                    ).date() + timedelta(days=1)
                except (KeyError, TypeError, ValueError) as exc:
                    sys.stderr.write(
                        f"cannot append demo reading for {crew_id}: invalid latest mission date\n"
                    )
                    return self._json(
                        {"error": "Latest mission date is invalid; contact the demo operator."},
                        500,
                    )
                reading = app.companion.save_measurement(
                    crew_id,
                    mission_day,
                    next_date.isoformat(),
                    readings,
                )
                app.rows.append(reading)
                return self._json(
                    {
                        "reading": {
                            key: value
                            for key, value in reading.items()
                            if key != "created_at"
                        },
                    },
                    201,
                )

            if u.path == "/api/me/emergency-report":
                try:
                    report = app.report(crew_id)
                except KeyError:
                    return self._json({"error": "No readings are available for this account."}, 404)
                urgent_symptoms = (
                    body.get("urgent_symptoms_confirmed", False)
                    if isinstance(body, dict) else False
                )
                if not isinstance(urgent_symptoms, bool):
                    return self._json({"error": "urgent_symptoms_confirmed must be a boolean."}, 400)
                if (
                    set(body) - {"urgent_symptoms_confirmed"}
                    if isinstance(body, dict) else True
                ):
                    return self._json({"error": "Only urgent_symptoms_confirmed is accepted."}, 400)
                above_safe = report["risk_indicator"]["state"] == "above_safe"
                if not above_safe and not urgent_symptoms:
                    return self._json({"error": "A local emergency handoff is available only for an above-safe demo report."}, 409)
                payload = {
                    "type": "flight_surgeon_review_request",
                    "crew_id": crew_id,
                    "profile": report["profile"],
                    "generated_at": datetime.now(timezone.utc).isoformat(),
                    "risk_indicator": report["risk_indicator"],
                    "current_rule_status": report["status"],
                    "latest_reading": report["latest"],
                    "recent_trend": app.report_history(crew_id)[-7:],
                    "weekly_summary": app.weekly_summary(crew_id),
                    "suggested_follow_up": report["advice"],
                    "trigger": (
                        "above_safe_demo_indicator" if above_safe
                        else "astronaut_self_reported_urgent_symptoms"
                    ),
                    "delivery": {
                        "status": "queued_local",
                        "transmitted": False,
                        "note": "This report remains in the local demo database. No Earth-station connection is configured.",
                    },
                    "disclaimer": "Synthetic-data demonstration only; not clinically validated or diagnostic.",
                }
                handoff = app.companion.queue_handoff(crew_id, payload)
                return self._json(
                    {
                        "handoff": handoff,
                        "delivery": payload["delivery"],
                    },
                    201,
                )

            if u.path == "/api/me/mock-handoff-ack":
                if (
                    not isinstance(body, dict)
                    or set(body) != {"handoff_id"}
                    or isinstance(body["handoff_id"], bool)
                    or not isinstance(body["handoff_id"], int)
                    or body["handoff_id"] < 1
                ):
                    return self._json({"error": "Provide a positive integer handoff_id."}, 400)
                handoff = app.companion.simulate_handoff_acknowledgement(
                    crew_id,
                    body["handoff_id"],
                )
                if handoff is None:
                    return self._json(
                        {"error": "This local report does not exist, belongs to another astronaut, or is no longer awaiting mock acknowledgement."},
                        404,
                    )
                return self._json({
                    "handoff": {
                        "id": handoff["id"],
                        "delivery_status": handoff["delivery_status"],
                        "acknowledged_at": handoff["acknowledged_at"],
                        "transmitted": False,
                    },
                    "note": "Simulated acknowledgement only. No report was sent to any station or person.",
                })

            if isinstance(body, list):
                rows = body
            elif isinstance(body, dict) and "rows" in body:
                rows = body["rows"]
            elif isinstance(body, dict) and "reading" in body:
                rows = [body["reading"]]
            elif isinstance(body, dict):
                rows = [body]
            else:
                return self._json({"error": "expected a JSON object or list"}, 400)

            if not isinstance(rows, list) or not rows or len(rows) > 500:
                return self._json({"error": "provide between 1 and 500 readings"}, 400)
            if any(not isinstance(r, dict) for r in rows):
                return self._json({"error": "each reading must be a JSON object"}, 400)
            rows = [coerce(dict(r)) for r in rows]
            for r in rows:
                r["crew_id"] = crew_id
                r.setdefault("mission_day", 0)
            preds = app.score_rows(rows)
            return self._json({"count": len(preds), "predictions": preds})

    return Handler


def main() -> int:
    ap = argparse.ArgumentParser(description="Crew Health Monitor API")
    ap.add_argument("--host", default=os.environ.get("HOST", "127.0.0.1"))
    ap.add_argument("--port", type=int, default=int(os.environ.get("PORT", "8000")))
    ap.add_argument("--data", default=DEFAULT_DATA)
    ap.add_argument("--model", default=DEFAULT_MODEL)
    ap.add_argument(
        "--auth-db",
        default=os.environ.get("HEALTHMON_AUTH_DB", DEFAULT_AUTH_DB),
    )
    demo_mode = ap.add_mutually_exclusive_group()
    demo_mode.add_argument(
        "--public-demo",
        action="store_true",
        help="allow direct card access to reports for the unchanged synthetic demo dataset only",
    )
    demo_mode.add_argument(
        "--wearable-demo",
        action="store_true",
        help="show four selected wearable-study participants on localhost",
    )
    ap.add_argument(
        "--wearable-dataset",
        default=DEFAULT_WEARABLE_DATASET,
        help="path to the downloaded wearable dataset directory",
    )
    ap.add_argument("--secure-cookies", action="store_true",
                    help="mark session cookies Secure when served through HTTPS")
    args = ap.parse_args()

    for path, hint in ((args.data, "py scripts/generate_synthetic_crew.py"),
                       (args.model, "py scripts/train_model.py")):
        if not os.path.exists(path):
            print(f"missing {path}\nrun: {hint}", file=sys.stderr)
            return 1

    if args.wearable_demo and args.host not in ("127.0.0.1", "localhost", "::1"):
        print("wearable-demo may only bind to localhost.", file=sys.stderr)
        return 1

    try:
        app = App(
            args.data,
            args.model,
            args.auth_db,
            public_demo=args.public_demo,
            wearable_dataset=(
                args.wearable_dataset if args.wearable_demo else None
            ),
        )
    except (OSError, ValueError) as exc:
        print(f"cannot start server: {exc}", file=sys.stderr)
        return 1
    app.secure_cookies = args.secure_cookies
    httpd = ThreadingHTTPServer((args.host, args.port), make_handler(app))
    print(f"Crew Health Monitor API on http://{args.host}:{args.port}")
    print(f"  sign-in   : http://{args.host}:{args.port}/")
    if args.wearable_demo:
        print("  data mode : four selected wearable-study participants (localhost only)")
    elif args.public_demo:
        print("  data mode : unchanged synthetic astronaut demo")
    else:
        print("  data mode : private astronaut records (mission-number authentication)")
    print("  mission numbers: py scripts/manage_badges.py issue-mission-number CREW_ID")
    if args.host not in ("127.0.0.1", "localhost", "::1"):
        print("WARNING: HTTP is not encrypted. Use only behind an HTTPS reverse proxy.")
    print("Ctrl+C to stop.")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\nstopping.")
    finally:
        httpd.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
