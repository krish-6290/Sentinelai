import os
import sqlite3


def path():
    return os.getenv("DB_PATH", "sentinel.db")


SCHEMA = """
CREATE TABLE IF NOT EXISTS txns (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  account_id TEXT NOT NULL,
  amount REAL NOT NULL,
  merchant TEXT, category TEXT,
  country TEXT, device_id TEXT,
  ts REAL NOT NULL,
  risk REAL DEFAULT 0,
  verdict TEXT DEFAULT 'pending',
  explanation TEXT DEFAULT '',
  evidence TEXT DEFAULT '[]',
  engine TEXT DEFAULT '',
  status TEXT DEFAULT 'none'
);
CREATE INDEX IF NOT EXISTS idx_acc_ts ON txns(account_id, ts);
CREATE INDEX IF NOT EXISTS idx_dev ON txns(device_id, ts);
"""


def conn():
    c = sqlite3.connect(path(), check_same_thread=False)
    c.row_factory = sqlite3.Row
    return c


def init():
    c = conn()
    c.executescript(SCHEMA)
    c.commit()
    c.close()
