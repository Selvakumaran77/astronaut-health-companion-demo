@echo off
rem Start the authenticated Crew Health Monitor on http://127.0.0.1:8000
rem Issue individual badges first with: py scripts\manage_badges.py issue-badge CREW_ID
rem Extra args are passed through, e.g.  run_api.bat --port 9000
setlocal
cd /d "%~dp0"

if not exist "data\synthetic\crew_vitals_simulated.csv" (
  echo Generating simulated crew dataset...
  py scripts\generate_synthetic_crew.py
)
if not exist "models\risk_model.json" (
  echo Training risk model...
  py scripts\train_model.py
)
if not exist "app\dashboard.html" (
  echo Building dashboard...
  py scripts\build_dashboard.py
)

echo Starting API... press Ctrl+C to stop.
py scripts\serve_api.py %*
