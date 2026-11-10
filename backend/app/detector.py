"""Statistical anomaly model (IsolationForest) used as one tool by the agent."""
import math
import numpy as np
from sklearn.ensemble import IsolationForest
from . import simulator

_model = None


def features(amount, avg, vel_count, hour):
    ratio = amount / avg if avg else 1.0
    return [math.log1p(amount), min(ratio, 50), vel_count, 1.0 if hour < 6 else 0.0]


def train(n=3000):
    global _model
    rows = []
    for _ in range(n):
        t = simulator.normal()
        avg = simulator.ACCOUNTS[t["account_id"]]["avg"]
        rows.append(features(t["amount"], avg, np.random.poisson(1), np.random.randint(6, 24)))
    _model = IsolationForest(n_estimators=150, contamination=0.02, random_state=7).fit(rows)


def ml_score(amount, avg, vel_count, hour):
    if _model is None:
        train()
    df = _model.decision_function([features(amount, avg or amount, vel_count, hour)])[0]
    return float(1 / (1 + math.exp(12 * df)))  # 0..1, higher = more anomalous
