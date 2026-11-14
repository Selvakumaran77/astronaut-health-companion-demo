"""
healthmon.features
==================

Feature engineering for the crew health-risk model.

The prediction task is **early warning**: using readings up to and including day *t*
(plus short rolling windows), predict whether the crew member will be in an elevated
state (`watch` or `alert`) on day *t+1*.

Only same-day and *past* values are used, so the model never sees the future.
Pure standard library — no numpy/pandas.
"""

from __future__ import annotations

from typing import Any, Iterable

# Raw indicators used directly as features.
BASE_FIELDS = [
    "heart_rate_bpm", "systolic_bp_mmHg", "diastolic_bp_mmHg", "spo2_pct",
    "resp_rate_bpm", "body_temp_c", "sleep_hours", "mood_score_1_10",
    "cognitive_score_0_100", "bone_density_pct_change", "muscle_mass_pct_change",
    "wbc_1e9_per_L", "crp_mg_per_L", "radiation_dose_mSv_day",
    "radiation_dose_cumulative_mSv", "cabin_co2_ppm",
]

# Indicators for which we also add rolling means and a 1-day delta.
TREND_FIELDS = [
    "heart_rate_bpm", "spo2_pct", "body_temp_c", "crp_mg_per_L",
    "sleep_hours", "mood_score_1_10", "radiation_dose_mSv_day", "cabin_co2_ppm",
]

FEATURE_NAMES: list[str] = (
    BASE_FIELDS
    + [f"{f}_mean3" for f in TREND_FIELDS]
    + [f"{f}_mean7" for f in TREND_FIELDS]
    + [f"{f}_delta1" for f in TREND_FIELDS]
)

LEVEL_RANK = {"normal": 0, "watch": 1, "alert": 2}


def _f(v: Any, default: float = 0.0) -> float:
    try:
        return float(v)
    except (TypeError, ValueError):
        return default


def _mean(vals: Iterable[float]) -> float:
    vals = list(vals)
    return sum(vals) / len(vals) if vals else 0.0


def _features_at(seq: list[dict], i: int) -> dict[str, float]:
    row = seq[i]
    f: dict[str, float] = {b: _f(row.get(b)) for b in BASE_FIELDS}
    for t in TREND_FIELDS:
        win3 = seq[max(0, i - 2): i + 1]
        win7 = seq[max(0, i - 6): i + 1]
        f[f"{t}_mean3"] = _mean(_f(r.get(t)) for r in win3)
        f[f"{t}_mean7"] = _mean(_f(r.get(t)) for r in win7)
        prev = _f(seq[i - 1].get(t)) if i > 0 else _f(row.get(t))
        f[f"{t}_delta1"] = _f(row.get(t)) - prev
    return f


def _group_sorted(rows: list[dict]) -> dict[str, list[dict]]:
    groups: dict[str, list[dict]] = {}
    for r in rows:
        groups.setdefault(r.get("crew_id", "?"), []).append(r)
    for crew in groups:
        groups[crew].sort(key=lambda r: _f(r.get("mission_day")))
    return groups


def build_dataset(rows: list[dict], with_target: bool = True) -> dict[str, list]:
    """Return {X, y, meta, feature_names}.

    X: list of feature dicts (one per reading).
    y: list of 0/1 (1 = elevated next day) or None where there is no next day.
    meta: list of {crew_id, mission_day, date_utc, level}.
    """
    X: list[dict] = []
    y: list = []
    meta: list[dict] = []

    for crew, seq in _group_sorted(rows).items():
        for i in range(len(seq)):
            X.append(_features_at(seq, i))
            meta.append({
                "crew_id": crew,
                "mission_day": int(_f(seq[i].get("mission_day"))),
                "date_utc": seq[i].get("date_utc"),
                "level": seq[i].get("alert_level", "normal"),
            })
            if with_target:
                if i + 1 < len(seq):
                    nxt = seq[i + 1].get("alert_level", "normal")
                    y.append(1 if LEVEL_RANK.get(nxt, 0) >= 1 else 0)
                else:
                    y.append(None)
            else:
                y.append(None)

    return {"X": X, "y": y, "meta": meta, "feature_names": list(FEATURE_NAMES)}
