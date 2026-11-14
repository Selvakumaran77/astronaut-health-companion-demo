# Data Dictionary — `synthetic/crew_vitals_simulated.csv`

Simulated daily crew health indicators for the NASA Space Apps 2026 challenge
*"Create Health Monitoring Software for Astronauts on Space Missions."*

**Grain:** one row per crew member per day.
**Coverage:** 4 crew (`CDR-1`, `MS-1`, `MS-2`, `PLT-1`) × 180 days = 720 rows.
**Mission window:** 2026-06-01 → 2026-11-27 (includes the 2026-09-05 solar particle event).
**Deterministic:** generated with `random.seed(42)`.
**Rule-based split:** 608 normal / 104 watch / 8 alert.

## How the values are produced

Each crew member carries a hidden **physiological load** `L(t)` that mean-reverts
toward a set-point (an Ornstein–Uhlenbeck / AR(1) process). The set-point is normally
0 but rises during discrete **illness/injury episodes** and during **solar particle
events**. Every measured indicator is a per-crew baseline + a *loading* on `L(t)` +
small observation noise. Because `L(t)` is autocorrelated, elevated states persist
across days — which is realistic and what makes next-day risk prediction possible.
See `scripts/generate_synthetic_crew.py`.

| Column | Unit | Typical range | Meaning / rationale |
|---|---|---|---|
| `crew_id` | — | `CDR-1`,`MS-1`,`MS-2`,`PLT-1` | Crew member identifier (synthetic). |
| `date_utc` | date | 2026-06-01 … | Calendar day (UTC). |
| `mission_day` | day | 1 … 180 | Elapsed mission day. |
| `heart_rate_bpm` | bpm | 45–130 | Resting heart rate. Rises with load/stress. |
| `systolic_bp_mmHg` | mmHg | 85–155 | Systolic blood pressure (cardiovascular). |
| `diastolic_bp_mmHg` | mmHg | 55–100 | Diastolic blood pressure. |
| `spo2_pct` | % | 86–100 | Blood oxygen saturation (falls with load). |
| `resp_rate_bpm` | breaths/min | 10–28 | Respiratory rate. |
| `body_temp_c` | °C | 35.6–39.0 | Core body temperature. |
| `sleep_hours` | hours | 3.0–9.5 | Sleep duration (falls with load). |
| `mood_score_1_10` | score | 1–10 | Behavioral-health self-report (higher is better). |
| `cognitive_score_0_100` | score | 0–100 | Cognitive performance (higher is better). |
| `bone_density_pct_change` | % change | 0 → ~-7.5 | Cumulative bone loss. Baseline ~1.2 %/month. |
| `muscle_mass_pct_change` | % change | 0 → ~-6.5 | Cumulative muscle loss. Baseline ~1.0 %/month. |
| `wbc_1e9_per_L` | 10⁹/L | 1.5–12.0 | White blood cell count (immune function). |
| `crp_mg_per_L` | mg/L | 0.1–~12 | C-reactive protein (inflammation); rises with load. |
| `radiation_dose_mSv_day` | mSv/day | ~1.5–62 | Daily ionizing-radiation dose. Baseline ~1.8; SPE days spike. |
| `radiation_dose_cumulative_mSv` | mSv | 0 → ~450 | Running mission radiation dose. |
| `cabin_co2_ppm` | ppm | 800–6000 | Cabin CO₂ concentration (closed-environment hazard). |
| `latent_stress_index` | index | ~-1.5 … ~3 | **Simulation ground truth only** — the hidden load `L(t)`. Not a measured indicator and **not** a model feature. |
| `alert_level` | category | `normal`/`watch`/`alert` | Rule-based triage from the thresholds below. |

## Alert thresholds used (illustrative)

- **alert:** SpO₂ < 93 %, or HR > 100, or temp > 38.0 °C, or CRP > 5 mg/L, or WBC < 3.0 ×10⁹/L
- **watch:** SpO₂ < 95 %, or HR > 90, or temp > 37.5 °C, or CRP > 3 mg/L, or sleep < 5.5 h, or mood < 5, or CO₂ > 5000 ppm
- **normal:** none of the above

These thresholds live in `src/healthmon/alerts.py` (`RULES`) and are used by the CLI,
authenticated API and astronaut report.

## Source basis

- Indicator selection: NASA HRP hazards/risks pages (`www.nasa.gov/hrp/`).
- Ranges and assay types: NASA OSDR / ALSDA (`data/raw/osdr/`).
- Radiation event timing: NASA DONKI (`data/raw/donki/`).
- Dose magnitudes: NASA PDS Curiosity RAD (`data/raw/pds_rad/`).
- Literature: NASA NTRS (`data/raw/ntrs/`).

> These are **synthetic** values for software development, not real astronaut measurements.
