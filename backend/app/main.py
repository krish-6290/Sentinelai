import asyncio
import json
import os
import time
from contextlib import asynccontextmanager
from fastapi import Depends, FastAPI, Header, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from . import agent, db as dbm, detector, simulator


def auth(x_api_key: str = Header(default="")):
    if x_api_key != os.getenv("API_KEY", "dev-key"):
        raise HTTPException(401, "invalid API key")


class Txn(BaseModel):
    account_id: str
    amount: float
    merchant: str = ""
    category: str = ""
    country: str = "IN"
    device_id: str = ""
    ts: float | None = None


class Review(BaseModel):
    status: str  # confirmed | dismissed


def ingest(t: dict):
    c = dbm.conn()
    t["ts"] = t.get("ts") or time.time()
    cur = c.execute("INSERT INTO txns(account_id,amount,merchant,category,country,device_id,ts) "
                    "VALUES(?,?,?,?,?,?,?)", (t["account_id"], t["amount"], t.get("merchant"),
                    t.get("category"), t.get("country"), t.get("device_id"), t["ts"]))
    tid = cur.lastrowid
    res = agent.analyze(c, t)
    status = "open" if res["verdict"] != "legit" else "none"
    c.execute("UPDATE txns SET risk=?,verdict=?,explanation=?,evidence=?,engine=?,status=? WHERE id=?",
              (res["risk"], res["verdict"], res["explanation"], json.dumps(res["evidence"]),
               res["engine"], status, tid))
    c.commit()
    c.close()
    return {"id": tid, **res}


def row(r):
    d = dict(r)
    d["evidence"] = json.loads(d["evidence"] or "[]")
    return d


async def stream_loop():
    """Continuous monitoring demo: a new transaction every few seconds."""
    while True:
        await asyncio.sleep(4)
        for t in simulator.batch(1, 0.25):
            await asyncio.to_thread(ingest, t)


@asynccontextmanager
async def lifespan(app):
    dbm.init()
    detector.train()
    task = asyncio.create_task(stream_loop()) if os.getenv("AUTO_STREAM") == "1" else None
    yield
    if task:
        task.cancel()


app = FastAPI(title="SentinelAI Fraud Agent", lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])


@app.get("/health")
def health():
    return {"ok": True}


@app.post("/transactions", dependencies=[Depends(auth)])
def post_txn(t: Txn):
    return ingest(t.model_dump())


@app.post("/simulate", dependencies=[Depends(auth)])
def simulate(n: int = 20):
    out = [ingest(t) for t in simulator.batch(min(n, 100))]
    return {"processed": len(out), "flagged": sum(o["verdict"] != "legit" for o in out)}


@app.get("/alerts", dependencies=[Depends(auth)])
def alerts(status: str = "open", limit: int = 50):
    c = dbm.conn()
    rows = c.execute("SELECT * FROM txns WHERE verdict!='legit' AND status=? "
                     "ORDER BY risk DESC, ts DESC LIMIT ?", (status, limit)).fetchall()
    return [row(r) for r in rows]


@app.get("/alerts/{tid}", dependencies=[Depends(auth)])
def alert(tid: int):
    c = dbm.conn()
    r = c.execute("SELECT * FROM txns WHERE id=?", (tid,)).fetchone()
    if not r:
        raise HTTPException(404, "not found")
    hist = c.execute("SELECT id,amount,country,ts FROM txns WHERE account_id=? "
                     "ORDER BY ts DESC LIMIT 10", (r["account_id"],)).fetchall()
    return {**row(r), "recent_history": [dict(h) for h in hist]}


@app.post("/alerts/{tid}/review", dependencies=[Depends(auth)])
def review(tid: int, rv: Review):
    if rv.status not in ("confirmed", "dismissed"):
        raise HTTPException(400, "status must be confirmed or dismissed")
    c = dbm.conn()
    c.execute("UPDATE txns SET status=? WHERE id=?", (rv.status, tid))
    c.commit()
    return {"id": tid, "status": rv.status}


@app.get("/stats", dependencies=[Depends(auth)])
def stats():
    c = dbm.conn()
    q = lambda s: c.execute(s).fetchone()[0]
    return {"total": q("SELECT COUNT(*) FROM txns"),
            "flagged": q("SELECT COUNT(*) FROM txns WHERE verdict!='legit'"),
            "open": q("SELECT COUNT(*) FROM txns WHERE status='open'"),
            "confirmed": q("SELECT COUNT(*) FROM txns WHERE status='confirmed'"),
            "amount_at_risk": round(q("SELECT COALESCE(SUM(amount),0) FROM txns WHERE status='open'"), 2)}
