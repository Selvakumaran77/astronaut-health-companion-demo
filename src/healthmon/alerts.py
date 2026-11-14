"""
healthmon.alerts
================

Threshold-based health-alert engine for the NASA Space Apps 2026 challenge
"Create Health Monitoring Software for Astronauts on Space Missions".

Design goals:
  * Pure standard library (no third-party deps) so it runs anywhere.
  * Thresholds are data, not code, so a flight surgeon can tune them.
  * Same rule set is mirrored in the dashboard (app/template.html).

Usage:
    py -m healthmon.alerts data/synthetic/crew_vitals_simulated.csv
    (run from the project root, with src/ on PYTHONPATH, or use the helper below)

The module can also be imported:

    from healthmon.alerts import evaluate_row, summarize
"""

from __future__ import annotations

import csv
import json
import os
import sys
from dataclasses import dataclass, field
from typing import Any, Iterable

# ---------------------------------------------------------------------------
# Thresholds.  Each rule: (column, comparison, value, level, message)
# Comparisons: "<" or ">".  Higher severity wins ("alert" > "watch" > "normal").
# ---------------------------------------------------------------------------
RULES: list[dict[str, Any]] = [
    {"col": "spo2_pct", "op": "<", "val": 93, "level": "alert", "msg": "Low blood oxygen (SpO2 < 93%)"},
    {"col": "heart_rate_bpm", "op": ">", "val": 100, "level": "alert", "msg": "High heart rate (> 100 bpm)"},
    {"col": "body_temp_c", "op": ">", "val": 38.0, "level": "alert", "msg": "Elevated body temperature (> 38.0 C)"},
    {"col": "crp_mg_per_L", "op": ">", "val": 5, "level": "alert", "msg": "Elevated CRP (> 5 mg/L)"},
    {"col": "wbc_1e9_per_L", "op": "<", "val": 3.0, "level": "alert", "msg": "Low white blood cell count (< 3.0)"},
    {"col": "spo2_pct", "op": "<", "val": 95, "level": "watch", "msg": "Low blood oxygen (SpO2 < 95%)"},
    {"col": "heart_rate_bpm", "op": ">", "val": 90, "level": "watch", "msg": "Elevated heart rate (> 90 bpm)"},
    {"col": "body_temp_c", "op": ">", "val": 37.5, "level": "watch", "msg": "Elevated body temperature (> 37.5 C)"},
    {"col": "crp_mg_per_L", "op": ">", "val": 3, "level": "watch", "msg": "Elevated CRP (> 3 mg/L)"},
    {"col": "sleep_hours", "op": "<", "val": 5.5, "level": "watch", "msg": "Reduced sleep (< 5.5 h)"},
    {"col": "mood_score_1_10", "op": "<", "val": 5, "level": "watch", "msg": "Low mood self-report (< 5/10)"},
    {"col": "cabin_co2_ppm", "op": ">", "val": 5000, "level": "watch", "msg": "High cabin CO2 (> 5000 ppm)"},
]

LEVEL_RANK = {"normal": 0, "watch": 1, "alert": 2}

# Path to personalized crew profiles
PROFILES_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "data", "crew_profiles.json")

def load_profiles() -> dict[str, Any]:
    """Load personalized crew profiles from JSON."""
    if os.path.exists(PROFILES_PATH):
        try:
            with open(PROFILES_PATH, encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return {}
    return {}

@dataclass
class Finding:
    # ... existing code ...
    level: str
    messages: list[str] = field(default_factory=list)


def evaluate_row(row: dict[str, Any], profiles: dict[str, Any] | None = None) -> Finding:
    """Evaluate a single reading against every rule, including personalized ones."""
    level = "normal"
    messages: list[str] = []
    
    # Get personal overrides for this crew member
    crew_id = row.get("crew_id")
    active_rules = list(RULES)
    if profiles and crew_id in profiles:
        personal_thresholds = profiles[crew_id].get("thresholds", [])
        # If personal thresholds are provided, we could either APPEND or REPLACE.
        # Here we REPLACE rules for the same column to avoid double alerts,
        # otherwise we APPEND.
        override_cols = {r["col"] for r in personal_thresholds}
        active_rules = [r for r in active_rules if r["col"] not in override_cols]
        active_rules.extend(personal_thresholds)

    for rule in active_rules:
        raw = row.get(rule["col"])
        if raw in (None, ""):
            continue
        try:
            v = float(raw)
        except (TypeError, ValueError):
            continue
        hit = v < rule["val"] if rule["op"] == "<" else v > rule["val"]
        if hit:
            messages.append(rule["msg"])
            if LEVEL_RANK[rule["level"]] > LEVEL_RANK[level]:
                level = rule["level"]
    return Finding(level=level, messages=messages)


def summarize(
    rows: Iterable[dict[str, Any]],
    profiles: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Aggregate findings across many readings."""
    if profiles is None:
        profiles = load_profiles()
    counts = {"normal": 0, "watch": 0, "alert": 0}
    per_crew: dict[str, dict[str, int]] = {}
    for row in rows:
        f = evaluate_row(row, profiles)
        counts[f.level] += 1
        crew = row.get("crew_id", "?")
        per_crew.setdefault(crew, {"normal": 0, "watch": 0, "alert": 0})
        per_crew[crew][f.level] += 1
    return {"total": sum(counts.values()), "counts": counts, "per_crew": per_crew}


def _main(argv: list[str]) -> int:
    if len(argv) < 2:
        print("usage: py -m healthmon.alerts <csv-path>")
        return 2
    with open(argv[1], newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    result = summarize(rows)
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(_main(sys.argv))
