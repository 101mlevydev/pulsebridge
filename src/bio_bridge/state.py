"""SQLite-backed sync state tracking."""

from __future__ import annotations

import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional


SCHEMA = """
CREATE TABLE IF NOT EXISTS sync_state (
    metric TEXT PRIMARY KEY,
    last_sync_at TEXT NOT NULL,
    updated_at TEXT NOT NULL DEFAULT (CURRENT_TIMESTAMP)
);
CREATE TABLE IF NOT EXISTS backfill_progress (
    metric TEXT NOT NULL,
    window_start TEXT NOT NULL,
    window_end TEXT NOT NULL,
    completed_at TEXT NOT NULL DEFAULT (CURRENT_TIMESTAMP),
    PRIMARY KEY (metric, window_start, window_end)
);
"""


class State:
    def __init__(self, path: Path):
        path.parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(str(path))
        self.conn.executescript(SCHEMA)
        self.conn.commit()

    def get_last_sync(self, metric: str) -> Optional[datetime]:
        cur = self.conn.execute("SELECT last_sync_at FROM sync_state WHERE metric = ?", (metric,))
        row = cur.fetchone()
        if row is None:
            return None
        return datetime.fromisoformat(row[0])

    def set_last_sync(self, metric: str, ts: datetime) -> None:
        self.conn.execute(
            "INSERT OR REPLACE INTO sync_state (metric, last_sync_at, updated_at) VALUES (?, ?, ?)",
            (metric, ts.isoformat(), datetime.now(timezone.utc).isoformat()),
        )
        self.conn.commit()

    def mark_backfill_window(self, metric: str, window_start: str, window_end: str) -> None:
        self.conn.execute(
            "INSERT OR IGNORE INTO backfill_progress (metric, window_start, window_end) VALUES (?, ?, ?)",
            (metric, window_start, window_end),
        )
        self.conn.commit()

    def is_window_done(self, metric: str, window_start: str, window_end: str) -> bool:
        cur = self.conn.execute(
            "SELECT 1 FROM backfill_progress WHERE metric = ? AND window_start = ? AND window_end = ?",
            (metric, window_start, window_end),
        )
        return cur.fetchone() is not None

    def close(self) -> None:
        self.conn.close()
