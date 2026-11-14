# Data — Health Monitoring Software (NASA Space Apps 2026)

Challenge: **Create Health Monitoring Software for Astronauts on Space Missions**
<https://www.spaceappschallenge.org/2026/challenges/health-monitoring-software/>

> Individual astronaut health records are privacy-protected, so the **crew** dataset is
> **simulated** (`data/synthetic/`), calibrated from the public sources in `data/raw/`.

## Folder layout

```
data/
├── raw/                 # downloaded from public NASA sources (unmodified)
│   ├── osdr/            # NASA Open Science Data Repository (GeneLab + ALSDA)
│   ├── donki/           # NASA space-weather events (solar flares, CMEs, particle events)
│   ├── pds_rad/         # Curiosity RAD surface-radiation file index
│   └── ntrs/            # NASA Technical Reports Server citations
├── synthetic/           # generated crew dataset (no real people)
└── data_dictionary.md   # field-by-field description of the synthetic dataset
```

## Raw data manifest

| File | Source | Records |
|---|---|---|
| `raw/osdr/search_bone_loss.json` | OSDR search API (`osdr.nasa.gov/osdr/data/search?term=bone loss&type=cgene,alsda`) | 54 |
| `raw/osdr/search_muscle_atrophy.json` | OSDR search API | 51 |
| `raw/osdr/search_cardiovascular.json` | OSDR search API | 31 |
| `raw/osdr/search_immune.json` | OSDR search API | 84 |
| `raw/osdr/search_radiation.json` | OSDR search API | 258 |
| `raw/osdr/search_sleep.json` | OSDR search API | 4 |
| `raw/osdr/search_behavior.json` | OSDR search API | 37 |
| `raw/osdr/search_microgravity.json` | OSDR search API | 301 |
| `raw/osdr/biodata_datasets.json` | OSDR Biological Data API v2 (`visualization.osdr.nasa.gov/biodata/api/v2/datasets/`) | listing |
| `raw/donki/SEP_2026-09-01_2026-10-25.json` | NASA CCMC DONKI API (solar energetic particles) | 8 |
| `raw/donki/FLR_2026-09-01_2026-10-25.json` | NASA CCMC DONKI API (solar flares) | 26 |
| `raw/donki/CME_2026-09-01_2026-10-25.json` | NASA CCMC DONKI API (coronal mass ejections) | 190 |
| `raw/pds_rad/INDEX.TAB` | NASA PDS — MSL Curiosity RAD RDR (`pds-ppi.igpp.ucla.edu/data/MSL-M-RAD-3-RDR-V1.0/`) | file index |
| `raw/ntrs/search_astronaut_health_monitoring.json` | NTRS citations API | 25 |
| `raw/ntrs/search_spaceflight_bone_loss.json` | NTRS citations API | 25 |
| `raw/ntrs/search_space_radiation_astronaut_health.json` | NTRS citations API | 25 |

## Synthetic data

| File | Description |
|---|---|
| `synthetic/crew_vitals_simulated.csv` | 4 crew × 180 days = **720 rows**, daily health indicators + rule-based alert level + a hidden `latent_stress_index`. Regenerate with `py scripts/generate_synthetic_crew.py`. |

Indicators are driven by a hidden, autocorrelated **physiological load** that rises
during discrete illness episodes and solar particle events, so elevated states persist
across days (realistic, and what makes next-day risk prediction learnable). The
`latent_stress_index` column is the simulation's ground truth and is **not** used as a
model feature. Details: `data_dictionary.md`.

The synthetic mission (2026-06-01 → 2026-11-27) intentionally overlaps the DONKI
solar-particle-event window (2026-09-05) so radiation-driven health changes appear in the data.

## Access notes

- **OSDR** and **DONKI** need no login. OSDR search returns study *metadata*; use the
  Biological Data API (`/v2/query/data/`) or the OSDR S3 bucket to pull actual assay files.
- **DONKI** date windows must be **≤ 60 days**; querying an exact 60-day span can fail.
- **PDS RAD** `INDEX.TAB` lists every RAD data file; prefix rows with the base URL to download.
- **NTRS** returns citations with links to full-text PDFs.
