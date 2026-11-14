"""
healthmon.model
===============

A dependency-free binary classifier used for astronaut health-risk early warning.

Implements L2-regularized logistic regression trained with full-batch gradient
descent, feature standardization, evaluation metrics, and JSON persistence so the
API and dashboard can score new readings without any ML library.

Task: given indicators up to day *t*, predict elevated risk (`watch`/`alert`) on day *t+1*.
"""

from __future__ import annotations

import json
import math
import os
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

MODEL_VERSION = 1


def _sigmoid(z: float) -> float:
    if z >= 0:
        return 1.0 / (1.0 + math.exp(-z))
    ez = math.exp(z)
    return ez / (1.0 + ez)


@dataclass
class LogisticRegression:
    feature_names: list[str] = field(default_factory=list)
    weights: list[float] = field(default_factory=list)
    bias: float = 0.0
    mean: list[float] = field(default_factory=list)
    std: list[float] = field(default_factory=list)
    threshold: float = 0.5
    metrics: dict[str, Any] = field(default_factory=dict)
    created: str = ""

    # -- internals ---------------------------------------------------------
    def _standardize(self, x: list[float]) -> list[float]:
        return [(x[i] - self.mean[i]) / (self.std[i] or 1.0) for i in range(len(x))]

    def _vector(self, features: dict[str, float]) -> list[float]:
        """Raw feature vector. Missing values are imputed with the training mean
        (so they standardize to 0 and add no contribution)."""
        out: list[float] = []
        for i, name in enumerate(self.feature_names):
            v = features.get(name, None)
            if v is None or v == "":
                out.append(self.mean[i] if i < len(self.mean) else 0.0)
                continue
            try:
                out.append(float(v))
            except (TypeError, ValueError):
                out.append(self.mean[i] if i < len(self.mean) else 0.0)
        return out

    # -- training ----------------------------------------------------------
    def fit(
        self,
        X: list[dict[str, float]],
        y: list[int],
        feature_names: list[str],
        *,
        l2: float = 1e-3,
        lr: float = 0.5,
        epochs: int = 800,
    ) -> "LogisticRegression":
        self.feature_names = list(feature_names)
        n = len(X)
        d = len(feature_names)

        # column means / stds
        cols = [[float(x.get(name, 0.0) or 0.0) for x in X] for name in feature_names]
        self.mean = [sum(c) / n for c in cols]
        self.std = []
        for c, m in zip(cols, self.mean):
            var = sum((v - m) ** 2 for v in c) / n
            self.std.append(math.sqrt(var) or 1.0)

        Z = [[(cols[j][i] - self.mean[j]) / self.std[j] for j in range(d)] for i in range(n)]

        self.weights = [0.0] * d
        self.bias = 0.0
        for _ in range(epochs):
            gw = [0.0] * d
            gb = 0.0
            for i in range(n):
                z = self.bias + sum(self.weights[j] * Z[i][j] for j in range(d))
                err = _sigmoid(z) - y[i]
                for j in range(d):
                    gw[j] += err * Z[i][j]
                gb += err
            for j in range(d):
                self.weights[j] -= lr * (gw[j] / n + l2 * self.weights[j])
            self.bias -= lr * (gb / n)
        return self

    # -- inference ---------------------------------------------------------
    def predict_proba(self, X: list[dict[str, float]]) -> list[float]:
        out = []
        for x in X:
            z = self.bias + sum(w * v for w, v in zip(self.weights, self._standardize(self._vector(x))))
            out.append(_sigmoid(z))
        return out

    def predict(self, X: list[dict[str, float]], threshold: float | None = None) -> list[int]:
        t = self.threshold if threshold is None else threshold
        return [1 if p >= t else 0 for p in self.predict_proba(X)]

    def score_one(self, features: dict[str, float]) -> dict[str, Any]:
        p = self.predict_proba([features])[0]
        return {
            "risk_probability": round(p, 4),
            "risk_level": "elevated" if p >= self.threshold else "low",
            "threshold": self.threshold,
        }

    # -- persistence -------------------------------------------------------
    def to_dict(self) -> dict[str, Any]:
        return {
            "model_version": MODEL_VERSION,
            "algorithm": "logistic_regression",
            "task": "predict elevated (watch/alert) health risk on the next mission day",
            "feature_names": self.feature_names,
            "weights": self.weights,
            "bias": self.bias,
            "mean": self.mean,
            "std": self.std,
            "threshold": self.threshold,
            "metrics": self.metrics,
            "created": self.created or datetime.now(timezone.utc).isoformat(),
        }

    def save(self, path: str) -> None:
        os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(self.to_dict(), f, indent=2)

    @classmethod
    def load(cls, path: str) -> "LogisticRegression":
        with open(path, encoding="utf-8") as f:
            d = json.load(f)
        return cls(
            feature_names=d["feature_names"],
            weights=d["weights"],
            bias=d["bias"],
            mean=d["mean"],
            std=d["std"],
            threshold=d.get("threshold", 0.5),
            metrics=d.get("metrics", {}),
            created=d.get("created", ""),
        )


# ---------------------------------------------------------------------------
# Metrics
# ---------------------------------------------------------------------------
def confusion(y_true: list[int], y_pred: list[int]) -> dict[str, int]:
    tp = sum(1 for a, b in zip(y_true, y_pred) if a == 1 and b == 1)
    tn = sum(1 for a, b in zip(y_true, y_pred) if a == 0 and b == 0)
    fp = sum(1 for a, b in zip(y_true, y_pred) if a == 0 and b == 1)
    fn = sum(1 for a, b in zip(y_true, y_pred) if a == 1 and b == 0)
    return {"tp": tp, "tn": tn, "fp": fp, "fn": fn}


def evaluate(y_true: list[int], y_prob: list[float], threshold: float = 0.5) -> dict[str, Any]:
    y_pred = [1 if p >= threshold else 0 for p in y_prob]
    c = confusion(y_true, y_pred)
    tp, tn, fp, fn = c["tp"], c["tn"], c["fp"], c["fn"]
    acc = (tp + tn) / max(1, len(y_true))
    prec = tp / max(1, tp + fp)
    rec = tp / max(1, tp + fn)
    f1 = 2 * prec * rec / max(1e-9, prec + rec)
    return {
        "n": len(y_true),
        "accuracy": round(acc, 4),
        "precision": round(prec, 4),
        "recall": round(rec, 4),
        "f1": round(f1, 4),
        "roc_auc": round(roc_auc(y_true, y_prob), 4),
        "confusion": c,
        "positive_rate": round(sum(y_true) / max(1, len(y_true)), 4),
    }


def roc_auc(y_true: list[int], y_prob: list[float]) -> float:
    pairs = sorted(zip(y_prob, y_true))
    pos = sum(y_true)
    neg = len(y_true) - pos
    if pos == 0 or neg == 0:
        return 0.5
    rank_sum = 0.0
    for i, (_, label) in enumerate(pairs, start=1):
        if label == 1:
            rank_sum += i
    return (rank_sum - pos * (pos + 1) / 2) / (pos * neg)


def top_features(model: LogisticRegression, k: int = 12) -> list[dict[str, Any]]:
    pairs = sorted(zip(model.feature_names, model.weights), key=lambda p: abs(p[1]), reverse=True)
    return [{"feature": n, "weight": round(w, 4)} for n, w in pairs[:k]]
