"""SentinelAI investigation agent.

Per transaction it gathers evidence with tools, then issues a verdict with a
plain-language explanation. Two engines: Claude tool-calling (when
ANTHROPIC_API_KEY is set) and an offline deterministic planner, so the
pipeline always works.
"""
import json
import os
from . import tools

SYSTEM = ("You are a financial fraud investigator. Investigate the transaction using the tools "
          "(profile, velocity, device links, anomaly score). Be efficient: skip tools that add nothing. "
          "Finish by calling submit_verdict with risk 0-1, a verdict, a short plain-language "
          "explanation, and a list of evidence strings.")


def verdict_for(risk):
    return "fraud" if risk >= 0.75 else "suspicious" if risk >= 0.4 else "legit"


def offline_analyze(db, t):
    ev, risk = [], 0.0
    prof = tools.run("account_profile", {"account_id": t["account_id"], "ts": t["ts"]}, db)
    vel = tools.run("velocity", {"account_id": t["account_id"], "ts": t["ts"]}, db)
    avg = prof["avg_amount"] or t["amount"]

    if prof["txn_count"] >= 5:
        ratio = t["amount"] / avg
        if ratio >= 10:
            risk += 0.45; ev.append(f"Amount is {ratio:.0f}x the account average")
        elif ratio >= 4:
            risk += 0.3; ev.append(f"Amount is {ratio:.1f}x the account average")
        if t["country"] not in prof["usual_countries"]:
            risk += 0.3; ev.append(f"First transaction from country {t['country']}")
    if vel["count"] >= 5:
        risk += 0.3; ev.append(f"{vel['count']} transactions in 10 minutes (total {vel['total']})")

    ml = tools.run("anomaly_score", {"amount": t["amount"], "avg_amount": avg,
                                     "recent_count": vel["count"], "ts": t["ts"]}, db)["ml_score"]
    risk += 0.25 * ml
    if ml > 0.6:
        ev.append(f"Statistical anomaly score {ml}")

    link = tools.run("shared_device", {"device_id": t["device_id"], "account_id": t["account_id"],
                                       "ts": t["ts"]}, db)
    if link["other_accounts"]:
        risk += 0.35
        ev.append(f"Device shared with {len(link['other_accounts'])} other account(s): "
                  f"{', '.join(link['other_accounts'][:3])}")

    risk = round(min(risk, 1.0), 3)
    v = verdict_for(risk)
    expl = "No risk indicators found." if not ev else f"Flagged as {v}: " + "; ".join(ev) + "."
    return {"risk": risk, "verdict": v, "explanation": expl, "evidence": ev, "engine": "offline-planner"}


def llm_analyze(db, t):
    import anthropic
    model = os.getenv("CLAUDE_MODEL", "claude-sonnet-5-5")
    client = anthropic.Anthropic()
    msgs = [{"role": "user", "content": "Investigate this transaction:\n" + json.dumps(t)}]
    for _ in range(7):
        r = client.messages.create(model=model, max_tokens=1000, system=SYSTEM,
                                   tools=tools.TOOL_SPECS, messages=msgs)
        msgs.append({"role": "assistant", "content": r.content})
        calls = [b for b in r.content if b.type == "tool_use"]
        if not calls:
            break
        results = []
        for b in calls:
            if b.name == "submit_verdict":
                out = dict(b.input)
                out["engine"] = "claude-agent"
                out["risk"] = round(float(out["risk"]), 3)
                return out
            results.append({"type": "tool_result", "tool_use_id": b.id,
                            "content": json.dumps(tools.run(b.name, b.input, db))})
        msgs.append({"role": "user", "content": results})
    raise RuntimeError("agent did not submit a verdict")


def analyze(db, t):
    if os.getenv("ANTHROPIC_API_KEY"):
        try:
            return llm_analyze(db, t)
        except Exception as e:  # never stall the pipeline
            print("LLM agent failed, using offline planner:", e)
    return offline_analyze(db, t)
