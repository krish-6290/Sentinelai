"""Tools the fraud agent can call. Each takes the db and returns JSON-able data."""
import time
from . import detector


def _hour(ts):
    return time.gmtime(ts).tm_hour


def account_profile(db, account_id, before_ts):
    rows = db.execute("SELECT amount,country FROM txns WHERE account_id=? AND ts<?",
                      (account_id, before_ts)).fetchall()
    if not rows:
        return {"txn_count": 0, "avg_amount": 0, "usual_countries": []}
    amts = [r["amount"] for r in rows]
    return {"txn_count": len(rows), "avg_amount": round(sum(amts) / len(amts), 2),
            "usual_countries": sorted({r["country"] for r in rows})}


def velocity(db, account_id, ts, window_sec=600):
    r = db.execute("SELECT COUNT(*) c, COALESCE(SUM(amount),0) s FROM txns "
                   "WHERE account_id=? AND ts BETWEEN ? AND ?",
                   (account_id, ts - window_sec, ts)).fetchone()
    return {"window_sec": window_sec, "count": r["c"], "total": round(r["s"], 2)}


def shared_device(db, device_id, account_id, ts):
    rows = db.execute("SELECT DISTINCT account_id FROM txns WHERE device_id=? AND account_id!=? "
                      "AND ts>?", (device_id, account_id, ts - 86400)).fetchall()
    return {"other_accounts": [r["account_id"] for r in rows]}


def anomaly_score(amount, avg_amount, recent_count, ts):
    return {"ml_score": round(detector.ml_score(amount, avg_amount, recent_count, _hour(ts)), 3)}


def run(name, args, db):
    if name == "account_profile":
        return account_profile(db, args["account_id"], args["ts"])
    if name == "velocity":
        return velocity(db, args["account_id"], args["ts"], args.get("window_sec", 600))
    if name == "shared_device":
        return shared_device(db, args["device_id"], args["account_id"], args["ts"])
    if name == "anomaly_score":
        return anomaly_score(args["amount"], args["avg_amount"], args["recent_count"], args["ts"])
    return {"error": f"unknown tool {name}"}


def _spec(name, desc, props, req):
    return {"name": name, "description": desc,
            "input_schema": {"type": "object", "properties": props, "required": req}}


S, N = {"type": "string"}, {"type": "number"}
TOOL_SPECS = [
    _spec("account_profile", "Historical behaviour of an account before a timestamp.",
          {"account_id": S, "ts": N}, ["account_id", "ts"]),
    _spec("velocity", "Count and total of an account's transactions in a recent window.",
          {"account_id": S, "ts": N, "window_sec": N}, ["account_id", "ts"]),
    _spec("shared_device", "Other accounts using the same device in 24h (fraud ring signal).",
          {"device_id": S, "account_id": S, "ts": N}, ["device_id", "account_id", "ts"]),
    _spec("anomaly_score", "IsolationForest anomaly score 0..1 for the transaction.",
          {"amount": N, "avg_amount": N, "recent_count": N, "ts": N},
          ["amount", "avg_amount", "recent_count", "ts"]),
    _spec("submit_verdict", "Final decision. Call once when the investigation is complete.",
          {"risk": N, "verdict": {"type": "string", "enum": ["legit", "suspicious", "fraud"]},
           "explanation": S, "evidence": {"type": "array", "items": S}},
          ["risk", "verdict", "explanation", "evidence"]),
]
