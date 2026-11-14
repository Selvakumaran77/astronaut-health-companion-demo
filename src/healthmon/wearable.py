"""Read a small, privacy-conscious view of the wearable research dataset."""

from __future__ import annotations

import csv
import math
import os
import random
import statistics

PARTICIPANTS = ("f01", "f02", "f03", "f04")
MISSION_NUMBERS = {
    "f01": "MS1001",
    "f02": "MS1002",
    "f03": "MS1003",
    "f04": "MS1004",
}


ACTIVITIES = {
    "stress": ("STRESS", "Induced-stress protocol"),
    "aerobic": ("AEROBIC", "Aerobic exercise"),
    "anaerobic": ("ANAEROBIC", "Anaerobic exercise"),
}
SIGNALS = {
    "HR": ("heart_rate_bpm", "Heart rate", "bpm"),
    "EDA": ("eda_us", "Electrodermal activity", "µS"),
    "TEMP": ("skin_temp_c", "Skin temperature", "°C"),
}
SIMULATED_INDICATORS = {
    "systolic_bp_mmHg": ("Systolic blood pressure", "mmHg", 118.0, 5.0, 85.0, 180.0),
    "diastolic_bp_mmHg": ("Diastolic blood pressure", "mmHg", 76.0, 4.0, 45.0, 120.0),
    "spo2_pct": ("Blood oxygen (SpO₂)", "%", 98.0, 0.45, 90.0, 100.0),
    "resp_rate_bpm": ("Respiratory rate", "/min", 15.5, 1.3, 8.0, 35.0),
    "body_temp_c": ("Body temperature", "°C", 36.8, 0.22, 35.0, 40.0),
    "sleep_hours": ("Sleep", "h", 7.2, 0.7, 0.0, 12.0),
    "mood_score_1_10": ("Mood", "/10", 7.4, 0.9, 1.0, 10.0),
    "cognitive_score_0_100": ("Cognitive score", "/100", 88.0, 3.4, 0.0, 100.0),
    "bone_density_pct_change": ("Bone-density change", "%", -0.015, 0.012, -1.0, 1.0),
    "muscle_mass_pct_change": ("Muscle-mass change", "%", -0.02, 0.025, -1.0, 1.0),
    "wbc_1e9_per_L": ("White blood cells", "10⁹/L", 6.0, 0.45, 2.0, 15.0),
    "crp_mg_per_L": ("CRP (inflammation)", "mg/L", 1.2, 0.22, 0.0, 10.0),
    "radiation_dose_mSv_day": ("Daily radiation dose", "mSv/day", 1.2, 0.12, 0.0, 10.0),
    "radiation_dose_cumulative_mSv": ("Cumulative radiation dose", "mSv", 32.0, 0.0, 0.0, 1000.0),
    "cabin_co2_ppm": ("Cabin CO₂", "ppm", 2500.0, 160.0, 300.0, 10000.0),
}
MEASURED_INDICATORS = {
    "heart_rate_bpm": ("Heart rate", "bpm"),
    "eda_us": ("Electrodermal activity", "µS"),
    "skin_temp_c": ("Skin temperature", "°C"),
}
STRESS_STAGES = (
    "Baseline",
    "TMCT",
    "First Rest",
    "Real Opinion",
    "Opposite Opinion",
    "Second Rest",
    "Subtract",
)
MAX_CHART_POINTS = 240


def _read_signal(path: str, code: str) -> dict:
    with open(path, newline="", encoding="utf-8-sig") as file:
        reader = csv.reader(file)
        start = next(reader, None)
        rate_row = next(reader, None)
        if not start or not rate_row:
            raise ValueError(f"Wearable signal file is incomplete: {path}")
        try:
            sample_rate = float(rate_row[0])
        except (ValueError, IndexError) as exc:
            raise ValueError(f"Wearable sample rate is invalid: {path}") from exc
        if not math.isfinite(sample_rate) or sample_rate <= 0:
            raise ValueError(f"Wearable sample rate must be positive: {path}")

        values = []
        for row in reader:
            if not row or not row[0].strip():
                continue
            try:
                value = float(row[0])
            except ValueError as exc:
                raise ValueError(f"Wearable sample is invalid: {path}") from exc
            if not math.isfinite(value):
                raise ValueError(f"Wearable sample is not finite: {path}")
            values.append(value)

    if not values:
        raise ValueError(f"Wearable signal file has no samples: {path}")

    stride = max(1, math.ceil(len(values) / MAX_CHART_POINTS))
    points = []
    for offset in range(0, len(values), stride):
        bucket = values[offset:offset + stride]
        sample_index = offset + (len(bucket) - 1) / 2
        points.append([
            round(sample_index / sample_rate / 60, 3),
            round(statistics.fmean(bucket), 4),
        ])

    key, label, unit = SIGNALS[code]
    return {
        "key": key,
        "label": label,
        "unit": unit,
        "source": "dataset",
        "start_utc": start[0],
        "sample_rate_hz": sample_rate,
        "sample_count": len(values),
        "duration_seconds": round((len(values) - 1) / sample_rate, 2),
        "average": round(statistics.fmean(values), 4),
        "minimum": round(min(values), 4),
        "maximum": round(max(values), 4),
        "points": points,
    }


def _simulated_signal(
    participant_id: str,
    activity_key: str,
    indicator_key: str,
    duration_seconds: float,
) -> dict:
    """Create explicitly synthetic chart values for indicators absent from the study."""
    label, unit, center, amplitude, minimum, maximum = SIMULATED_INDICATORS[
        indicator_key
    ]
    seed = sum(
        (index + 1) * ord(char)
        for index, char in enumerate(
            f"{participant_id}:{activity_key}:{indicator_key}"
        )
    )
    rng = random.Random(seed)
    points = []
    sample_count = 120
    activity_shift = {"stress": 0.0, "aerobic": 0.2, "anaerobic": 0.35}[activity_key]
    for index in range(sample_count):
        phase = index / max(1, sample_count - 1)
        if indicator_key == "radiation_dose_cumulative_mSv":
            value = center + phase * (1.8 + activity_shift)
        else:
            value = (
                center
                + amplitude * activity_shift
                + amplitude * (
                    0.55 * math.sin(phase * math.tau * 2)
                    + 0.25 * math.sin(phase * math.tau * 5 + 0.7)
                )
                + rng.gauss(0, amplitude * 0.12)
            )
        value = min(maximum, max(minimum, value))
        points.append([
            round(duration_seconds * phase / 60, 3),
            round(value, 4),
        ])

    values = [point[1] for point in points]
    return {
        "key": indicator_key,
        "label": label,
        "unit": unit,
        "source": "simulated",
        "sample_count": sample_count,
        "duration_seconds": round(duration_seconds, 2),
        "average": round(statistics.fmean(values), 4),
        "minimum": round(min(values), 4),
        "maximum": round(max(values), 4),
        "points": points,
    }


def load_wearable_dataset(dataset_path: str) -> dict[str, dict]:
    """Load selected second-stage participants without demographic fields."""
    labels_path = os.path.join(dataset_path, "Stress_Level_v2.csv")
    labels = {}
    with open(labels_path, newline="", encoding="utf-8-sig") as file:
        for row in csv.DictReader(file):
            participant_id = next(iter(row.values()), "").strip()
            if participant_id in PARTICIPANTS:
                labels[participant_id] = [
                    {
                        "stage": stage,
                        "score": float(row[stage]),
                    }
                    for stage in STRESS_STAGES
                ]

    participants = {}
    for participant_id in PARTICIPANTS:
        if participant_id not in labels:
            raise ValueError(
                f"Self-reported stress scores are missing for {participant_id}."
            )
        activities = {}
        for activity, (directory, label) in ACTIVITIES.items():
            folder = os.path.join(
                dataset_path, "Wearable_Dataset", directory, participant_id
            )
            signals = {}
            for code in SIGNALS:
                signal = _read_signal(
                    os.path.join(folder, f"{code}.csv"), code
                )
                signals[signal["key"]] = signal
            duration_seconds = max(
                signal["duration_seconds"] for signal in signals.values()
            )
            for indicator_key in SIMULATED_INDICATORS:
                signals[indicator_key] = _simulated_signal(
                    participant_id,
                    activity,
                    indicator_key,
                    duration_seconds,
                )
            activities[activity] = {
                "label": label,
                "start_utc": signals["heart_rate_bpm"]["start_utc"],
                "duration_seconds": duration_seconds,
                "signals": signals,
            }
        participants[participant_id] = {
            "participant_id": participant_id,
            "profile": {
                "mission_number": MISSION_NUMBERS[participant_id],
                "role": "Wearable research participant",
            },
            "stress_ratings": labels[participant_id],
            "activities": activities,
        }

    return participants


def participant_roster(participants: dict[str, dict]) -> list[dict]:
    """Return card-safe summaries for the selected four research participants."""
    roster = []
    for participant_id, participant in participants.items():
        stress = participant["activities"]["stress"]["signals"]
        roster.append({
            "participant_id": participant_id,
            "mission_number": participant["profile"]["mission_number"],
            "role": participant["profile"]["role"],
            "stress_rating_baseline": next(
                item["score"]
                for item in participant["stress_ratings"]
                if item["stage"] == "Baseline"
            ),
            "stress_rating_tmct": next(
                item["score"]
                for item in participant["stress_ratings"]
                if item["stage"] == "TMCT"
            ),
            "heart_rate_bpm": stress["heart_rate_bpm"]["average"],
            "eda_us": stress["eda_us"]["average"],
            "skin_temp_c": stress["skin_temp_c"]["average"],
        })
    return roster


def health_indicator_catalog() -> list[dict]:
    """List reference-dashboard indicators and the additional research signals."""
    catalog = [
        {
            "key": "heart_rate_bpm",
            "label": "Heart rate",
            "unit": "bpm",
            "source": "dataset",
        },
        {
            "key": "eda_us",
            "label": "Electrodermal activity",
            "unit": "µS",
            "source": "dataset",
        },
        {
            "key": "skin_temp_c",
            "label": "Skin temperature",
            "unit": "°C",
            "source": "dataset",
        },
    ]
    for key, (label, unit, *_rest) in SIMULATED_INDICATORS.items():
        catalog.append({
            "key": key,
            "label": label,
            "unit": unit,
            "source": "simulated",
        })
    return catalog
