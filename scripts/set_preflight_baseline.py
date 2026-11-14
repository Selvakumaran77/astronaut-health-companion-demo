"""Record an astronaut's Earth-side baseline risk score before launch."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "src"))

from healthmon.auth import AuthStore  # noqa: E402
from healthmon.features import BASE_FIELDS  # noqa: E402

DEFAULT_DATA = os.path.join(ROOT, "data", "synthetic", "crew_vitals_simulated.csv")
DEFAULT_AUTH_DB = os.path.join(ROOT, "data", "astronaut_badges.sqlite3")
DEFAULT_MODEL = os.path.join(ROOT, "models", "risk_model.json")


def main() -> int:
    parser = argparse.ArgumentParser(description="Record an Earth-side preflight B-score")
    parser.add_argument("crew_id")
    parser.add_argument(
        "--reading-file",
        required=True,
        help="JSON file containing one preflight reading; score it with this project's model",
    )
    parser.add_argument("--model", default=DEFAULT_MODEL)
    parser.add_argument("--auth-db", default=DEFAULT_AUTH_DB)
    parser.add_argument("--data", default=DEFAULT_DATA)
    args = parser.parse_args()

    try:
        with open(args.data, encoding="utf-8", newline="") as file:
            crew_ids = {row["crew_id"] for row in csv.DictReader(file)}
        if args.crew_id not in crew_ids:
            raise ValueError(f"Unknown crew ID: {args.crew_id}")
        with open(args.reading_file, encoding="utf-8") as file:
            reading = json.load(file)
        if not isinstance(reading, dict):
            raise ValueError("Preflight reading file must contain one JSON object.")
        missing = [field for field in BASE_FIELDS if field not in reading]
        if missing:
            raise ValueError(
                "Preflight check-up is missing required measurements: "
                + ", ".join(missing)
            )
        measurements = {}
        for field in BASE_FIELDS:
            try:
                value = float(reading[field])
            except (TypeError, ValueError) as exc:
                raise ValueError(
                    f"Preflight measurement {field} must be numeric."
                ) from exc
            if not math.isfinite(value):
                raise ValueError(f"Preflight measurement {field} must be finite.")
            measurements[field] = value
        if not os.path.exists(args.model):
            raise FileNotFoundError(f"Missing trained model: {args.model}")
        sys.path.insert(0, os.path.join(ROOT, "scripts"))
        from serve_api import App

        app = App(args.data, args.model, args.auth_db)
        reading["crew_id"] = args.crew_id
        reading.setdefault("mission_day", 0)
        prediction = app.score_rows([reading])[0]
        score_percent = prediction["risk_probability"] * 100
        with open(args.model, "rb") as model_file:
            model_signature = hashlib.sha256(model_file.read()).hexdigest()
        AuthStore(args.auth_db).set_preflight_baseline(
            args.crew_id,
            score_percent,
            model_signature,
            measurements,
        )
    except (OSError, ValueError) as exc:
        print(f"Could not record preflight B-score: {exc}", file=sys.stderr)
        return 1

    print(
        f"Recorded {score_percent:.2f}% Earth-side B-score and "
        f"{len(measurements)} health-indicator baselines for {args.crew_id}. "
        "The B-score is tied to this trained model and will be recalculated if the model changes."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
