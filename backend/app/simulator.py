"""Generates realistic transaction streams with injected fraud patterns."""
import random
import time

COUNTRIES = ["IN", "US", "GB", "SG", "AE"]
CATS = ["grocery", "fuel", "dining", "transport", "utilities", "shopping"]
ACCOUNTS = {f"A{i:03d}": {"home": "IN", "avg": random.choice([300, 600, 1200, 2500])}
            for i in range(1, 31)}


def normal(acc=None, ts=None):
    acc = acc or random.choice(list(ACCOUNTS))
    p = ACCOUNTS[acc]
    return dict(account_id=acc, amount=round(max(20, random.gauss(p["avg"], p["avg"] * .3)), 2),
                merchant=f"M{random.randint(1, 80)}", category=random.choice(CATS),
                country=p["home"], device_id=f"D-{acc}", ts=ts or time.time())


def fraud(kind=None):
    kind = kind or random.choice(["spike", "foreign", "burst", "ring"])
    acc = random.choice(list(ACCOUNTS))
    t = normal(acc)
    now = time.time()
    if kind == "spike":
        t["amount"] = ACCOUNTS[acc]["avg"] * random.randint(12, 30)
    elif kind == "foreign":
        t["country"] = random.choice(["NG", "RU", "KP"])
        t["amount"] = round(t["amount"] * 6, 2)
    elif kind == "burst":
        return [dict(t, amount=round(random.uniform(900, 2000), 2), ts=now + i * 0.01) for i in range(7)]
    elif kind == "ring":
        dev = f"D-RING-{random.randint(1, 3)}"
        return [dict(normal(a), device_id=dev, amount=round(random.uniform(3000, 9000), 2))
                for a in random.sample(list(ACCOUNTS), 4)]
    return [t]


def batch(n=20, fraud_rate=0.15):
    out = []
    for _ in range(n):
        out += fraud() if random.random() < fraud_rate else [normal()]
    return out
