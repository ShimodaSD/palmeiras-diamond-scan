"""SQLite persistence for notification history and sale state."""

from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Any

from .models import TicketSaleEvent

SCHEMA = """
CREATE TABLE IF NOT EXISTS notifications (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    source TEXT NOT NULL,
    match TEXT NOT NULL,
    match_date TEXT NOT NULL,
    sale_phase TEXT NOT NULL,
    sale_start_at TEXT,
    official_url TEXT,
    status TEXT NOT NULL,
    notified_at TEXT NOT NULL,
    UNIQUE (match, sale_phase)
);
"""


class Storage:
    """SQLite wrapper used to persist and dedupe ticket sale notifications."""

    def __init__(self, db_path: str = "data/notifications.db") -> None:
        path = Path(db_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(str(path), timeout=10, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._conn.executescript(SCHEMA)
        self._conn.commit()

    def close(self) -> None:
        """Close the database connection."""
        self._conn.close()

    def is_notified(self, match: str, sale_phase: str) -> bool:
        """Return True when this (match, phase) was already notified."""
        row = self._conn.execute(
            "SELECT 1 FROM notifications WHERE match = ? AND sale_phase = ?",
            (match, sale_phase),
        ).fetchone()
        return row is not None

    def record(self, event: TicketSaleEvent, notified_at: str) -> bool:
        """Insert a notification record; return False when it was a duplicate."""
        cursor = self._conn.execute(
            "INSERT OR IGNORE INTO notifications "
            "(source, match, match_date, sale_phase, sale_start_at, official_url, status, notified_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (
                event.source,
                event.match,
                event.match_date,
                event.sale_phase,
                event.sale_start_at,
                event.official_url,
                event.status,
                notified_at,
            ),
        )
        self._conn.commit()
        return cursor.rowcount > 0

    def get_history(self) -> list[dict[str, Any]]:
        """Return the most recent notification history rows."""
        rows = self._conn.execute(
            "SELECT source, match, match_date, sale_phase, sale_start_at, official_url, status, notified_at "
            "FROM notifications ORDER BY id DESC LIMIT 100"
        ).fetchall()
        return [dict(row) for row in rows]
