"""
Run the health-alert engine over the synthetic crew dataset and print a summary.

    py scripts/check_alerts.py
    py scripts/check_alerts.py path\to\other.csv
"""

from __future__ import annotations

import csv
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "src"))

from healthmon.alerts import summarize  # noqa: E402


def main() -> int:
    default = os.path.join(ROOT, "data", "synthetic", "crew_vitals_simulated.csv")
    path = sys.argv[1] if len(sys.argv) > 1 else default
    with open(path, newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    print(json.dumps(summarize(rows), indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
