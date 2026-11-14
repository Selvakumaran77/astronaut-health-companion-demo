"""
Generate a SIMULATED astronaut crew health dataset for the NASA Space Apps 2026
challenge "Create Health Monitoring Software for Astronauts on Space Missions".

Why simulated? Individual astronaut health records are privacy-protected, so the
challenge expects synthetic crew data built from published ranges. The value
ranges and radiation-event timing below are calibrated from public sources:

  - NASA HRP (Human Research Program) hazards/risks pages  -> which indicators matter
  - NASA OSDR / ALSDA (bone, muscle, cardiovascular, immune, behavior assays) -> ranges
  - NASA DONKI (solar energetic particle events) -> radiation spike timing
  - NASA PDS Curiosity RAD -> deep-space / surface dose magnitudes

Model
-----
Each crew member carries a hidden, slowly-varying "physiological load" L(t).
It follows a first-order autoregressive (AR(1)) process:

        L(t) = rho * L(t-1) + noise(t)

plus positive impulses from:
  * discrete illness/injury episodes (multi-day, ramp up then resolve), and
  * solar particle events (SPE) during the DONKI window.

Every measured indicator is a per-crew baseline plus a loading on L(t) plus small
observation noise. Because L(t) is autocorrelated, a bad day tends to be followed
by another bad day -- which is both physiologically realistic and what makes
next-day risk prediction possible.

`latent_stress_index` is written to the CSV for transparency/plots only. It is the
simulation's ground truth and is deliberately NOT used as a model feature.

Output: data/synthetic/crew_vitals_simulated.csv
Deterministic (seeded) so results are reproducible.
"""

import csv
import os
import random
from datetime import date, timedelta

random.seed(42)

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT_DIR = os.path.join(ROOT, "data", "synthetic")
os.makedirs(OUT_DIR, exist_ok=True)
OUT_CSV = os.path.join(OUT_DIR, "crew_vitals_simulated.csv")

CREW = ["CDR-1", "MS-1", "MS-2", "PLT-1"]
START = date(2026, 6, 1)
DAYS = 180
# Solar energetic particle event window taken from the DONKI SEP sample (2026-09-05).
SPE_DAYS = {date(2026, 9, 4), date(2026, 9, 5), date(2026, 9, 6)}

# --- latent-state dynamics (mean-reverting / Ornstein-Uhlenbeck) -----------
KAPPA = 0.30        # pull toward the current set-point each day (rho ~ 0.70)
SIGMA = 0.16        # innovation noise per day
EPISODE_START_P = 0.022     # chance per day of starting an illness/injury episode
EPISODE_LEN = (4, 9)        # inclusive duration range (days)
EPISODE_SEVERITY = (0.7, 2.1)
SPE_SETPOINT = 1.9

FIELDS = [
    "crew_id", "date_utc", "mission_day",
    "heart_rate_bpm", "systolic_bp_mmHg", "diastolic_bp_mmHg", "spo2_pct",
    "resp_rate_bpm", "body_temp_c",
    "sleep_hours", "mood_score_1_10", "cognitive_score_0_100",
    "bone_density_pct_change", "muscle_mass_pct_change",
    "wbc_1e9_per_L", "crp_mg_per_L",
    "radiation_dose_mSv_day", "radiation_dose_cumulative_mSv",
    "cabin_co2_ppm", "latent_stress_index", "alert_level",
]

# Rule-based triage thresholds -- mirrored in src/healthmon/alerts.py and the dashboard.
ALERT_RULES = [
    ("spo2_pct", "<", 93.0), ("heart_rate_bpm", ">", 100.0),
    ("body_temp_c", ">", 38.0), ("crp_mg_per_L", ">", 5.0),
    ("wbc_1e9_per_L", "<", 3.0),
]
WATCH_RULES = [
    ("spo2_pct", "<", 95.0), ("heart_rate_bpm", ">", 90.0),
    ("body_temp_c", ">", 37.5), ("crp_mg_per_L", ">", 3.0),
    ("sleep_hours", "<", 5.5), ("mood_score_1_10", "<", 5.0),
    ("cabin_co2_ppm", ">", 5000.0),
]


def clamp(v, lo, hi):
    return max(lo, min(hi, v))


def classify(vals):
    for col, op, val in ALERT_RULES:
        if (vals[col] < val) if op == "<" else (vals[col] > val):
            return "alert"
    for col, op, val in WATCH_RULES:
        if (vals[col] < val) if op == "<" else (vals[col] > val):
            return "watch"
    return "normal"


def main():
    rows = []
    for ci, crew in enumerate(CREW):
        bone = 0.0
        muscle = 0.0
        cum_dose = 0.0
        load = 0.0
        ep_days_left = 0
        ep_severity = 0.0
        # small, stable per-crew offsets (constitution)
        off = (ci - (len(CREW) - 1) / 2.0)  # ~[-1.5 .. +1.5]

        for d in range(DAYS):
            day = START + timedelta(days=d)
            spe = day in SPE_DAYS

            # ---- latent physiological load: relax toward a time-varying set-point ----
            setpoint = 0.0
            if ep_days_left <= 0 and random.random() < EPISODE_START_P:
                ep_days_left = random.randint(*EPISODE_LEN)
                ep_severity = random.uniform(*EPISODE_SEVERITY)
            if ep_days_left > 0:
                setpoint = ep_severity
                ep_days_left -= 1
            if spe:
                setpoint = max(setpoint, SPE_SETPOINT)
            load += KAPPA * (setpoint - load) + random.gauss(0.0, SIGMA)
            load = max(-1.5, load)

            L = load  # shorthand

            # ---- radiation: deep-space baseline ~1.8 mSv/day; SPE spikes ----
            dose_day = random.gauss(1.8, 0.25)
            if spe:
                dose_day += random.uniform(25.0, 60.0)
            dose_day = max(0.0, dose_day)
            cum_dose += dose_day

            # ---- measurements = baseline + loading * L + observation noise ----
            hr = clamp(60 + 3 * off + 13 * L + random.gauss(0, 4.0), 45, 130)
            sys_bp = clamp(114 + 3 * off + 8 * L + random.gauss(0, 7.0), 85, 155)
            dia_bp = clamp(74 + 2 * off + 5 * L + random.gauss(0, 5.0), 55, 100)
            spo2 = clamp(97.9 - 2.3 * L + random.gauss(0, 0.5), 86, 100)
            rr = clamp(15 + 1.6 * L + random.gauss(0, 1.2), 10, 28)
            temp = clamp(36.6 + 0.5 * L + random.gauss(0, 0.12), 35.6, 39.0)
            sleep = clamp(6.9 - 1.5 * L + random.gauss(0, 0.5), 3.0, 9.5)
            mood = clamp(7.7 - 2.3 * L + random.gauss(0, 0.7), 1, 10)
            cog = clamp(90 - 10 * L + random.gauss(0, 4.0), 0, 100)
            wbc = clamp(6.7 - 1.7 * L + random.gauss(0, 0.7), 1.5, 12.0)
            crp = max(0.1, 0.8 + 1.2 * max(L, 0) + 0.6 * max(L, 0) ** 2 + random.gauss(0, 0.4))
            co2 = clamp(random.gauss(2800, 450), 800, 6000)

            # ---- bone / muscle: gradual spaceflight loss (per-day fraction) ----
            bone -= random.gauss(1.2 / 30.0, 0.02) + (0.01 if L > 1.5 else 0)
            muscle -= random.gauss(1.0 / 30.0, 0.02) + (0.008 if L > 1.5 else 0)

            vals = {
                "heart_rate_bpm": round(hr, 1),
                "systolic_bp_mmHg": round(sys_bp, 1),
                "diastolic_bp_mmHg": round(dia_bp, 1),
                "spo2_pct": round(spo2, 1),
                "resp_rate_bpm": round(rr, 1),
                "body_temp_c": round(temp, 2),
                "sleep_hours": round(sleep, 2),
                "mood_score_1_10": round(mood, 1),
                "cognitive_score_0_100": round(cog, 1),
                "wbc_1e9_per_L": round(wbc, 2),
                "crp_mg_per_L": round(crp, 2),
                "cabin_co2_ppm": int(co2),
            }

            rows.append({
                "crew_id": crew,
                "date_utc": day.isoformat(),
                "mission_day": d + 1,
                "heart_rate_bpm": vals["heart_rate_bpm"],
                "systolic_bp_mmHg": vals["systolic_bp_mmHg"],
                "diastolic_bp_mmHg": vals["diastolic_bp_mmHg"],
                "spo2_pct": vals["spo2_pct"],
                "resp_rate_bpm": vals["resp_rate_bpm"],
                "body_temp_c": vals["body_temp_c"],
                "sleep_hours": vals["sleep_hours"],
                "mood_score_1_10": vals["mood_score_1_10"],
                "cognitive_score_0_100": vals["cognitive_score_0_100"],
                "bone_density_pct_change": round(bone, 3),
                "muscle_mass_pct_change": round(muscle, 3),
                "wbc_1e9_per_L": vals["wbc_1e9_per_L"],
                "crp_mg_per_L": vals["crp_mg_per_L"],
                "radiation_dose_mSv_day": round(dose_day, 3),
                "radiation_dose_cumulative_mSv": round(cum_dose, 3),
                "cabin_co2_ppm": vals["cabin_co2_ppm"],
                "latent_stress_index": round(L, 3),
                "alert_level": classify(vals),
            })

    with open(OUT_CSV, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=FIELDS)
        w.writeheader()
        w.writerows(rows)

    from collections import Counter
    counts = Counter(r["alert_level"] for r in rows)
    n = len(rows)
    print("rows:", n)
    print("crew:", len(CREW), "days:", DAYS)
    print("alert_level counts:", dict(counts),
          "  -> elevated share: {:.1%}".format((counts["watch"] + counts["alert"]) / n))
    # crude persistence check: P(elevated today | elevated yesterday)
    by_crew = {}
    for r in rows:
        by_crew.setdefault(r["crew_id"], []).append(r)
    both = tot = 0
    for seq in by_crew.values():
        for a, b in zip(seq, seq[1:]):
            if a["alert_level"] != "normal":
                tot += 1
                if b["alert_level"] != "normal":
                    both += 1
    print("P(elevated today | elevated yesterday): {:.1%}".format(both / max(1, tot)))
    print("wrote:", OUT_CSV)


if __name__ == "__main__":
    main()
