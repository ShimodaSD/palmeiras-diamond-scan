"""SQLite persistence for notification history and seen posts."""

from __future__ import annotations

import sqlite3
import threading
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
    venue_type TEXT,
    venue TEXT,
    announcement_url TEXT,
    status TEXT NOT NULL,
    notified_at TEXT NOT NULL,
    UNIQUE (match, sale_phase)
);

CREATE TABLE IF NOT EXISTS seen_posts (
    post_key TEXT PRIMARY KEY,
    source TEXT NOT NULL,
    title TEXT,
    url TEXT,
    published_at TEXT,
    modified_at TEXT,
    parsed INTEGER NOT NULL,
    first_seen_at TEXT NOT NULL
);
"""

NEW_NOTIFICATION_COLUMNS = {
    "venue_type": "TEXT",
    "venue": "TEXT",
    "announcement_url": "TEXT",
}


class Storage:
    """SQLite wrapper used to persist notifications and seen posts."""

    def __init__(self, db_path: str = "data/notifications.db") -> None:
        path = Path(db_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(str(path), timeout=10, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._conn.executescript(SCHEMA)
        self._migrate()
        self._conn.commit()
        self._lock = threading.RLock()

    def _migrate(self) -> None:
        """Add columns introduced after the first schema version."""
        columns = {row[1] for row in self._conn.execute("PRAGMA table_info(notifications)")}
        for name, column_type in NEW_NOTIFICATION_COLUMNS.items():
            if name not in columns:
                self._conn.execute(f"ALTER TABLE notifications ADD COLUMN {name} {column_type}")

    def close(self) -> None:
        """Close the database connection."""
        with self._lock:
            self._conn.close()

    def is_notified(self, match: str, sale_phase: str) -> bool:
        """Return True when this (match, phase) was already notified."""
        with self._lock:
            row = self._conn.execute(
                "SELECT 1 FROM notifications WHERE match = ? AND sale_phase = ?",
                (match, sale_phase),
            ).fetchone()
            return row is not None

    def record(self, event: TicketSaleEvent, notified_at: str) -> bool:
        """Insert a notification record; return False when it was a duplicate."""
        with self._lock:
            cursor = self._conn.execute(
                "INSERT OR IGNORE INTO notifications "
                "(source, match, match_date, sale_phase, sale_start_at, official_url, "
                "venue_type, venue, announcement_url, status, notified_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    event.source,
                    event.match,
                    event.match_date,
                    event.sale_phase,
                    event.sale_start_at,
                    event.official_url,
                    event.venue_type,
                    event.venue,
                    event.announcement_url,
                    event.status,
                    notified_at,
                ),
            )
            self._conn.commit()
            return cursor.rowcount > 0

    def get_history(self) -> list[dict[str, Any]]:
        """Return the most recent notification history rows."""
        with self._lock:
            rows = self._conn.execute(
                "SELECT source, match, match_date, sale_phase, sale_start_at, official_url, "
                "venue_type, venue, announcement_url, status, notified_at "
                "FROM notifications ORDER BY id DESC LIMIT 100"
            ).fetchall()
            return [dict(row) for row in rows]

    def count_posts(self) -> int:
        """Return how many posts have been recorded."""
        with self._lock:
            row = self._conn.execute("SELECT COUNT(*) AS total FROM seen_posts").fetchone()
            return int(row["total"])

    def post_seen(self, post_key: str) -> bool:
        """Return True when this post was already processed in an earlier pass."""
        with self._lock:
            row = self._conn.execute(
                "SELECT 1 FROM seen_posts WHERE post_key = ?", (post_key,)
            ).fetchone()
            return row is not None

    def record_post(
        self,
        post_key: str,
        source: str,
        title: str,
        url: str,
        published_at: str | None,
        modified_at: str | None,
        parsed: bool,
        first_seen_at: str,
    ) -> bool:
        """Record a post as seen; return False when it was already recorded."""
        with self._lock:
            cursor = self._conn.execute(
                "INSERT OR IGNORE INTO seen_posts "
                "(post_key, source, title, url, published_at, modified_at, parsed, first_seen_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    post_key,
                    source,
                    title,
                    url,
                    published_at,
                    modified_at,
                    1 if parsed else 0,
                    first_seen_at,
                ),
            )
            self._conn.commit()
            return cursor.rowcount > 0
