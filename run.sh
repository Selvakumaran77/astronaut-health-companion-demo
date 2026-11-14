#!/usr/bin/env sh
set -eu

cd "$(dirname "$0")"

PYTHON="${PYTHON:-python3}"

if [ ! -f "data/synthetic/crew_vitals_simulated.csv" ]; then
  echo "Generating synthetic crew dataset..."
  "$PYTHON" scripts/generate_synthetic_crew.py
fi

if [ ! -f "models/risk_model.json" ]; then
  echo "Training risk model..."
  "$PYTHON" scripts/train_model.py
fi

if [ ! -f "app/dashboard.html" ]; then
  echo "Building dashboard..."
  "$PYTHON" scripts/build_dashboard.py
fi

exec "$PYTHON" scripts/serve_api.py "$@"
