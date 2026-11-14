"""
Train the crew health-risk early-warning model and evaluate it.

    py scripts/train_model.py

Reads   data/synthetic/crew_vitals_simulated.csv
Writes  models/risk_model.json   (weights + metrics, used by the API and dashboard)

The split is chronological (early mission days train, later days test) to respect
the time-series nature of the data.
"""

from __future__ import annotations

import csv
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "src"))

from healthmon.features import build_dataset  # noqa: E402
from healthmon.model import LogisticRegression, evaluate, top_features  # noqa: E402

CSV_PATH = os.path.join(ROOT, "data", "synthetic", "crew_vitals_simulated.csv")
MODEL_PATH = os.path.join(ROOT, "models", "risk_model.json")
SPLIT_DAY = 126  # days <= SPLIT_DAY -> train, later days -> test


def load_rows(path: str) -> list[dict]:
    with open(path, newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def main() -> int:
    if not os.path.exists(CSV_PATH):
        print(f"missing dataset: {CSV_PATH}\nrun: py scripts/generate_synthetic_crew.py", file=sys.stderr)
        return 1

    rows = load_rows(CSV_PATH)
    ds = build_dataset(rows, with_target=True)
    X, y, meta = ds["X"], ds["y"], ds["meta"]

    train_idx = [i for i in range(len(X)) if y[i] is not None and meta[i]["mission_day"] <= SPLIT_DAY]
    test_idx = [i for i in range(len(X)) if y[i] is not None and meta[i]["mission_day"] > SPLIT_DAY]

    Xtr = [X[i] for i in train_idx]
    ytr = [int(y[i]) for i in train_idx]
    Xte = [X[i] for i in test_idx]
    yte = [int(y[i]) for i in test_idx]

    model = LogisticRegression()
    model.fit(Xtr, ytr, ds["feature_names"], l2=1e-2, lr=0.5, epochs=1500)

    train_prob = model.predict_proba(Xtr)
    test_prob = model.predict_proba(Xte)
    model.metrics = {
        "train": evaluate(ytr, train_prob),
        "test": evaluate(yte, test_prob),
        "split_day": SPLIT_DAY,
        "n_features": len(ds["feature_names"]),
    }
    model.save(MODEL_PATH)

    print(f"rows total  : {len(X)}")
    print(f"train / test: {len(Xtr)} / {len(Xte)}   (split at mission day {SPLIT_DAY})")
    print(f"positive rate train/test: {model.metrics['train']['positive_rate']} / {model.metrics['test']['positive_rate']}")
    print()
    print("TRAIN metrics:", json.dumps(model.metrics["train"]))
    print("TEST  metrics:", json.dumps(model.metrics["test"]))
    print()
    print("top features by |weight|:")
    for f in top_features(model, 12):
        print(f"  {f['weight']:+.4f}  {f['feature']}")
    print()
    print(f"wrote: {MODEL_PATH}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
