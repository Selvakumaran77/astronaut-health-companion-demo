# Crew Health Monitor — NASA Space Apps 2026

Software for the NASA Space Apps 2026 challenge
**"Create Health Monitoring Software for Astronauts on Space Missions."** The application
contains separate synthetic astronaut and wearable research-data demonstrations.

Long-duration missions expose crews to radiation, isolation, altered gravity, and a closed
environment, causing immune changes, bone loss, cardiovascular events, and behavioral-health
problems. This project ingests daily health indicators, evaluates them against configurable
thresholds, and **estimates next-day risk** with a trained model — surfaced in an authenticated
personal report and a crew-scoped JSON API.

> **Privacy note:** real astronaut health records are protected, so the crew data here is
> **simulated**, calibrated from published NASA ranges (see `data/`).

## Quick start

```bat
:: from the project root; install the barcode-image generator
py -m pip install -r requirements.txt
:: open the four selected wearable study participants (default dataset folder is beside this project)
py scripts\serve_api.py --wearable-demo
```

### Cross-platform start

The local Python app works on Python 3.10+ and uses the Python standard library at runtime.
On Windows, use `run.bat`; on macOS/Linux, run `sh ./run.sh`. For a consistent cross-platform
environment, use Docker:

```sh
docker build -t astronaut-health-companion .
docker run --rm -p 8000:8000 astronaut-health-companion
```

The container intentionally starts only the integrity-checked synthetic public demo, binds to
the container port supplied by the platform, and marks session cookies Secure. It does not
include wearable research data, badge images, or the local badge database. Its SQLite demo
store is under `/tmp` and is ephemeral; container restarts discard check-ins and queued reports.

### Online synthetic demo deployment (Render)

`render.yaml` and the Dockerfile describe a Render web service for the synthetic public demo.
To publish it, put this project directory in a Git repository, push it to a Git provider, then
create a Render Blueprint deployment from that repository and open the HTTPS URL Render assigns.
The deployment uses no supplied health records: public reports are restricted to the checked-in
synthetic dataset and matching profiles. Free Render services may sleep while idle and have
ephemeral local storage. Do not deploy private records or enable wearable demo on a public host.

This deployment is for demonstration only. It is not a medical service; risk scores and prompts
are illustrative, the synthetic review board is public, and mock report acknowledgement does not
transmit anything. For production, first obtain approved clinical protocols, security/privacy
review, durable encrypted storage, authenticated clinician access, and an approved station API.

Open `http://127.0.0.1:8000/` to view participants `f01`–`f04` from the dataset's second
study cohort. Each report shows their study-stage self-reported stress scores and HR, EDA, and
skin-temperature sessions for induced stress, aerobic exercise, and anaerobic exercise. Time
series are averaged into at most 240 chart bins for display; summary statistics use all valid
source samples. Demographic fields are not exposed. The wearable view is a research-data
demonstration, not an astronaut report, clinical assessment, or trained risk prediction, and
the app restricts this mode to localhost.

The wearable dataset is expected two folders above the project, in
`..\..\wearable-device-dataset-from-induced-stress-and-structured-exercise-sessions-1.0.1`.
To use a different location, pass `--wearable-dataset "C:\path\to\dataset"` along with
`--wearable-demo`. Double-click **`run.bat`** to start the wearable demo when that dataset is
present; otherwise it starts the unchanged synthetic astronaut demo.

The original synthetic astronaut app remains available with `py scripts\serve_api.py --public-demo`.
Public card reports in that mode are restricted to the unchanged, checked-in
synthetic dataset and profiles by SHA-256 signature. For private or modified astronaut health
demo data, start the server without `--public-demo`; mission-number authentication is required.
This authentication is a prototype access control, not a production medical-record security
system. Do not load real astronaut records. The
background video and card image are served from `app/assets/`.

The API uses the Python standard library. The homepage retrieves a public roster containing only astronaut names, roles, and crew IDs.
The wearable demo reads the selected participants' CSV files from the local dataset folder; it
does not upload or copy the raw dataset. The background video and card image are served from
`app/assets/`.

The site also has a persistent crew-wellbeing widget. After an astronaut report is opened, it
automatically shows that report's predefined guidance and current illustrative risk indicator.
Its guided conversation runs in the browser; it is not a generative AI or a substitute for
medical or behavioral-health care. In either dashboard mode, the agent can fetch sports and
entertainment headlines on demand from BBC RSS feeds. Headlines are filtered to the prior 48
hours; older or undated feed entries are excluded. Search words are matched locally in fetched
headlines. The request to BBC contains no participant data or chat text; internet access is
required and each headline links to its source.

### Health-companion demonstration features

The authenticated synthetic astronaut report also includes:

- A preflight check-up import that records the model's B-score and the 16 raw health-indicator
  values. All 16 indicators are required by `scripts\set_preflight_baseline.py`; the B-score
  is tied to the model version. Current graphs show preflight comparison lines where available
  and phase-specific comparison bands estimated from the first 14 recorded readings in each
  phase. Mission phases and these statistical bands are demonstration references, not
  medically established personal limits.
- A daily in-app reminder, plus an opt-in browser notification at a chosen local time while the
  app tab remains open. Browser permission is required and reminders do not run after the app is
  closed. A sleep/exercise/stress check-in, streak counts, and non-clinical completion badges
  are also included. Check-ins do not change the risk model.
- A daily measurement form for all 16 model indicators. Each submission is stored in the local
  SQLite demo database, assigned the next mission day, and used in the next report and risk
  trend. The form pre-fills the preceding demo values for convenience; replace them with a
  complete measurement set rather than treating copied values as new observations.
- Seven-recorded-day summary, indicator trend charts, a clickable body-system navigation map,
  and spacecraft/ISS/lunar-base display modes. Environment modes are visual only and do not
  connect to vehicle sensors.
- General NASA Human Research Program hazard-awareness prompts and an above-safe review
  checklist. A self-reported urgent-symptom selection can also create a local handoff regardless
  of the demo score; the app tells the astronaut to follow established mission protocol and
  contact onboard medical support. This does not perform emergency triage.
- A flight-surgeon review report and locally queued handoff snapshot. The queue stays on the
  server and is not transmitted to Earth. A mock acknowledgement can be demonstrated, but it
  does not send anything or constitute a station receipt. No receiver, alert delivery, or clinician login is
  configured. A public overview board is available only in the integrity-checked synthetic
  public demo; it is not an authenticated doctor console or suitable for real records. In
  private mode, the review view is restricted to the astronaut's own signed-in record.

These features are prototype demonstrations. The current thresholds are not medically
validated or documented as approved clinical rules; hazard prompts are educational rather than
NASA medical procedures. The SQLite database is **not encrypted at rest**. Use only synthetic
demonstration values until approved medical protocols, secure key management, a clinician
access model, and a tested receiver/API contract are provided. Browser notifications require
permission and the page to remain open; they do not guarantee that a daily check-in occurs.
Urgent symptoms must be handled through mission emergency procedures; the local queue is not
monitored or transmitted.

The default server binds to localhost. Do not expose it directly on a network: HTTP
does not encrypt badge codes or health data. For network access, use an HTTPS reverse
proxy, run with `--secure-cookies`, and follow your organization's identity and
health-data security requirements. This prototype is not a production medical system.

## Layout

```
├── app\
│   ├── astronaut.html       # astronaut-card home page and authenticated personal report
│   ├── template.html        # legacy aggregate dashboard design (not served)
│   └── dashboard.html       # generated sign-in page (contains no health records)
├── src\healthmon\
│   ├── auth.py              # hashed, revocable badge codes + preflight measurements
│   ├── companion.py         # local demo check-ins + unsent review queue
│   ├── alerts.py            # threshold engine (RULES + evaluate_row + summarize)
│   ├── notifications.py     # state-change notifications (onset / escalation / back-to-normal)
│   ├── features.py          # feature engineering for the risk model
│   ├── model.py             # logistic regression + metrics + JSON persistence
│   └── wearable.py          # selected wearable-study signal summaries and chart bins
├── scripts\
│   ├── manage_badges.py     # issue/revoke astronaut barcode badges
│   ├── set_preflight_baseline.py # record the Earth-side B-score
│   ├── generate_synthetic_crew.py   # 4 crew × 180 days, seeded
│   ├── train_model.py               # train + evaluate -> models\risk_model.json
│   ├── build_dashboard.py           # copy sign-in page; never embeds health records
│   ├── check_alerts.py              # CLI alert summary
│   └── serve_api.py                 # stdlib authenticated HTTP API + personal report
├── models\
│   └── risk_model.json      # trained weights, normalization, metrics
├── data\
│   ├── raw\                 # downloaded NASA datasets (OSDR, DONKI, PDS, NTRS)
│   ├── synthetic\           # crew_vitals_simulated.csv (720 rows)
│   ├── data_dictionary.md   # field definitions + thresholds
│   └── README.md            # data manifest + access notes
├── tests\
│   ├── test_astronaut_auth.py
│   └── test_wearable.py     # wearable parser and research-mode API tests
└── resources\               # the 5 official challenge resource pages (HTML + PDF)
```

### Wearable research dataset

The wearable dashboard reads only `f01`–`f04` from the V2 protocol in the
[Wearable Device Dataset from Induced Stress and Structured Exercise Sessions](https://physionet.org/content/wearable-device-dataset-from-induced-stress-and-structured-exercise-sessions/1.0.1/).
It displays HR, EDA, and skin temperature from each participant's stress, aerobic, and
anaerobic sessions alongside the study's V2 self-reported stress-stage scores. Participant
IDs are de-identified study labels; the interface uses mission numbers MS1001–MS1004 instead of
names. Reports show selectable, downsampled
within-session sensor trends and study-stage stress scores. The chart selector
also include all 16 health indicators from `dashboard[1].html`, along with EDA and skin temperature.
Heart rate, EDA, and skin temperature are measured study signals; other indicators are generated
examples because they are not in this dataset. The interface keeps provenance details out of the
individual cards and chart selector, while disclosing that the dashboard combines historical
measurements with generated examples. Each graph can show actual values or deviation around its
displayed-session/participant mean, using a centered zero line. The
dashboard structure and chart styling follow the reference dashboard, but reference synthetic
readings and risk predictions are not copied. Generated values are not clinical assessments.
The raw recordings date from 2013 and must not be presented
as live astronaut telemetry. This dashboard does not infer a stress diagnosis, define safe
thresholds, or run the astronaut risk model on this dataset.

Contains information from the *Wearable Device Dataset from Induced Stress and Structured
Exercise Sessions*, made available under the [ODC Attribution License 1.0](https://opendatacommons.org/licenses/by/1-0/).
The original `LICENSE.txt` and dataset documentation remain with the downloaded dataset.

## How it works

```
synthetic data ──▶ rule engine (alerts.py)  ──▶ normal / watch / alert  ──▶ personal report + API
      │
      └──────────▶ feature engineering (features.py) ──▶ risk model (model.py) ──▶ P(elevated tomorrow)
```

1. **Ingest** — daily per-crew indicators (`data/synthetic/crew_vitals_simulated.csv`):
   HR, BP, SpO2, temperature, sleep, mood, cognition, bone/muscle change, WBC, CRP,
   radiation dose, cabin CO2.
2. **Evaluate** — `src/healthmon/alerts.py` applies data-driven `RULES` and returns a level of
   `normal` / `watch` / `alert` plus human-readable reasons. The UI displays the API's result so
   the CLI, API and signed-in report use the same thresholds.
3. **Predict** — `src/healthmon/features.py` + `model.py` estimate the probability that the crew
   member is in an elevated state (`watch`/`alert`) on the **next** mission day, using only
   current and past data.
4. **Notify** — `src/healthmon/notifications.py` turns the level changes into warnings
   (problem started / got worse) and **"back to normal"** confirmations.
5. **Surface** — a badge scan opens the astronaut's personal report; authorization scopes
   each health-data API response to the badge's crew ID.

### Astronaut badges and report

An operator issues a Code 128 badge with `scripts\manage_badges.py issue-badge CREW_ID`.
Only a SHA-256 digest of the random badge credential is stored in SQLite; scans are
rate-limited, and browser sessions use HttpOnly, SameSite cookies and expire after 12
hours or when the server restarts. There is no public badge registration. Each credential
is associated with one crew ID, and requests for another crew ID are rejected. Treat the
badge like a medical-record key: anyone with a copy can scan it. Revoke lost badges promptly.

Before launch, record the astronaut's Earth-side B-score using a JSON file of preflight
measurements, scored with the same model:
`py scripts\set_preflight_baseline.py CREW_ID --reading-file ground_checkup.json`.
The resulting score, timestamp, and model-file signature are stored in
`data/astronaut_badges.sqlite3`; if the model changes, the old baseline is marked stale
and must be recomputed from the preflight reading.

The astronaut demo report compares the current in-space model score with this preflight B-score and the
trained model threshold. **Safe** is below 75% of the safe line, **rising** is nearing that
line or has a watch alert, and **above safe** is at/above the safe line or has an alert. The
safe line is the lower of the recorded B-score and model threshold. If no Earth-side baseline
is recorded, the indicator explicitly uses the model threshold and notes the missing B-score.
These are illustrative model-risk references—not clinical thresholds.

For rising or above-safe results, the report can export a flight-surgeon handoff JSON. This
prototype shows an above-safe consultation notice and the report, recommending prompt review
with an Earth-based doctor or flight surgeon under mission protocols. The handoff export is
local only: this prototype has no mission-control/ground communication integration and does
**not** transmit health data to Earth. Operators must use an approved medical channel.
Advice is predefined decision support, not diagnosis or treatment. Source values are synthetic
and the risk model is not clinically validated.

### Astronaut report charts

Each astronaut report includes a selectable health-indicator trend and a predicted next-day
risk trend, both calculated from that astronaut's own synthetic mission history. The indicator
chart has a **View** switch (the diverging view is the default):

- **Rise/drop from baseline (0 centred)** — a **centered-zero diverging line chart**: each reading
  minus that crew's own mission mean. The Y range is **symmetric** (e.g. `-M … +M`), so **0 sits
  exactly at the vertical centre**; positive values extend **upward** and negative values **downward**
  from a solid horizontal **zero reference line**. The area is shaded to zero and the axis labels are
  signed (`+`/`-`). Only horizontal guides are drawn (no vertical Y-axis spine).
- **Actual values** — the raw reading over mission days.

The predicted-risk trend preserves the centered-zero design: it shows percentage-point
deviation from that astronaut's own mean predicted risk, not the absolute probability. Card
vitals and chart histories are exposed only when `--public-demo` verifies the unchanged
checked-in synthetic dataset and profiles.

## The risk model

- **Task:** predict elevated (`watch`/`alert`) health state on day *t+1* from features up to day *t*.
- **Algorithm:** L2-regularized logistic regression (pure Python, gradient descent) with feature
  standardization; 40 features = 16 raw indicators + 3-/7-day rolling means + 1-day deltas.
- **Split:** chronological — mission days ≤ 126 train (504 rows), days > 126 test (212 rows).
- **Test performance:** AUC **0.926**, precision **0.90**, recall **0.62**, F1 **0.735**.
- **Top drivers:** SpO₂, mood (3-day mean), cognitive score, WBC, body-temperature trend, heart rate,
  radiation dose, sleep.
- Weights, normalization and metrics are stored in `models/risk_model.json`; retrain any time with
  `py scripts\train_model.py`.

### Risk chart — centered zero baseline

The **predicted next-day risk** chart is a **centered-zero diverging** chart, not a 0–100% probability
axis. Each day's raw model probability (`risk_prob`, still preserved on every row and listed in the
risk table) is transformed into a **deviation from that crew's own baseline risk**:

```
centeredValue = (risk_prob - crewBaselineRisk) * 100     # percentage points
```

The Y range is symmetric (`-M … +M`), so **0 sits exactly at the vertical centre**; values above 0
mean "riskier than this crew's usual level", values below 0 mean "calmer". The chart is labelled as a
**deviation, not a probability** — the negative values are *not* negative probabilities. The old
0–100% axis, the 50% threshold line and the percentage shaded band are removed; crew colours, names,
solar-particle markers and the legend are preserved.

## API

`py scripts\serve_api.py` (default `http://127.0.0.1:8000`) serves the scanner page and JSON.
Except for liveness and mission-number sign-in, API endpoints require the session cookie and
are scoped to the signed-in astronaut:

| Method | Endpoint | Description |
|---|---|---|
| GET | `/` | astronaut-card home page and personal report UI |
| GET | `/health` | public liveness only |
| GET | `/api/astronauts` | public astronaut card labels only (crew ID, name, role) |
| POST | `/api/mission-number` | exchange a private 20-digit mission number for a scoped session |
| GET | `/api/demo/report/CREW_ID` | public report only when `--public-demo` validates the unchanged synthetic files |
| POST | `/api/scan` | legacy badge-code sign-in endpoint |
| POST | `/api/logout` | revoke the current browser session |
| GET | `/api/me/report` | latest personal condition signals, risk estimate, and follow-up guidance |
| POST | `/api/me/checkin` | save this astronaut's daily sleep/exercise/stress demo check-in |
| POST | `/api/me/readings` | save all 16 next-day demo health measurements and update the astronaut's trend |
| POST | `/api/me/emergency-report` | queue an above-safe or self-reported-urgent local review report; never transmits |
| POST | `/api/me/mock-handoff-ack` | mark a local queue item as mock-acknowledged for demonstration; never transmits |
| GET | `/model`, `/crew`, `/readings`, `/alerts`, `/summary`, `/notifications`, `/predict` | authenticated existing API, restricted to the signed-in crew ID |
| GET | `/api/demo/doctor-dashboard` | synthetic all-crew weekly overview, only in integrity-checked `--public-demo` mode |
| POST | `/predict` | score submitted readings; crew ID is set from the authenticated session |

## Notifications (warn while bad, confirm when normal)

`src/healthmon/notifications.py` watches alert-level changes and raises a notification
on every change of state. The authenticated `/notifications` API only returns the signed-in
astronaut's events:

| Change | Notification |
|---|---|
| `normal → watch/alert` | ⚠️ **warning** — a problem started |
| `watch → alert` | 🚨 **warning** — it got worse (escalated) |
| `alert → watch` | (improving, but still not normal — the warning stands) |
| `watch/alert → normal` | ✅ **recovered** — "back to normal", with the peak level and how many days it lasted |

When a reading returns to normal, a "back to normal" notification is raised.

## Indicators monitored

| Domain | Indicators |
|---|---|
| Cardiovascular | heart rate, systolic/diastolic BP, SpO2, respiratory rate |
| Bone & muscle | bone-density % change, muscle-mass % change |
| Immune / inflammation | white blood cells, CRP |
| Behavioral health | sleep hours, mood score, cognitive score |
| Radiation | daily dose, cumulative dose (SPE events flagged) |
| Environment | cabin CO2 |

## Data sources

- **NASA OSDR** (GeneLab + ALSDA) — spaceflight biology studies (`data/raw/osdr/`)
- **NASA DONKI** — solar flares, CMEs, solar energetic particles (`data/raw/donki/`)
- **NASA PDS** — Curiosity RAD surface radiation (`data/raw/pds_rad/`)
- **NASA NTRS** — technical-report citations (`data/raw/ntrs/`)
- **NASA HRP** — hazard/risk background (`resources/`)

Details and endpoints: see `data/README.md`. Field definitions: `data/data_dictionary.md`.

## Disclaimer

Educational/hackathon project. Not affiliated with or endorsed by NASA. Simulated values only.
