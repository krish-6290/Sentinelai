import os
import tempfile
import time

os.environ["DB_PATH"] = os.path.join(tempfile.mkdtemp(), "t.db")
os.environ.pop("ANTHROPIC_API_KEY", None)
from fastapi.testclient import TestClient  # noqa: E402
from app.main import app  # noqa: E402

H = {"X-API-Key": "dev-key"}


def txn(**k):
    d = dict(account_id="T1", amount=500, country="IN", device_id="D-T1", ts=time.time())
    d.update(k)
    return d


def test_flow():
    with TestClient(app) as c:
        base = time.time() - 50000
        for i in range(8):
            assert c.post("/transactions", json=txn(ts=base + i * 4000), headers=H).status_code == 200
        ok = c.post("/transactions", json=txn(), headers=H).json()
        assert ok["verdict"] == "legit"
        bad = c.post("/transactions", json=txn(amount=9000, country="NG"), headers=H).json()
        assert bad["verdict"] in ("suspicious", "fraud") and bad["risk"] >= 0.4
        assert any(a["id"] == bad["id"] for a in c.get("/alerts", headers=H).json())
        r = c.post(f"/alerts/{bad['id']}/review", json={"status": "confirmed"}, headers=H)
        assert r.json()["status"] == "confirmed"
        assert c.get("/stats", headers=H).json()["confirmed"] == 1


def test_ring_detection():
    with TestClient(app) as c:
        c.post("/transactions", json=txn(account_id="R1", device_id="D-X"), headers=H)
        out = c.post("/transactions", json=txn(account_id="R2", amount=7000, device_id="D-X"), headers=H).json()
        assert "Device shared" in out["explanation"]


def test_auth():
    with TestClient(app) as c:
        assert c.get("/stats").status_code == 401
