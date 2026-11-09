"""SQLite persistence for notification history and seen posts."""

from __future__ import annotations

import fcntl
import sqlite3
import threading
from pathlib import Path
from typing import Any

from .models import TicketSaleEvent, build_event_key, post_identity

NOTIFICATIONS_TABLE = """
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
    dedupe_key TEXT NOT NULL,
    UNIQUE (dedupe_key)
);
"""

SEEN_POSTS_TABLE = """
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

SCHEMA = (
    NOTIFICATIONS_TABLE
    + SEEN_POSTS_TABLE
    + """
CREATE TABLE IF NOT EXISTS system_alerts (
    alert_key TEXT PRIMARY KEY,
    sent_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS store_events (
    event_key TEXT PRIMARY KEY,
    first_seen_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS pending_alerts (
    alert_key TEXT PRIMARY KEY,
    message TEXT NOT NULL,
    sent_at TEXT
);
"""
)

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
        self._run_lock_guard = threading.Lock()
        self._run_lock_file = open(f"{path.resolve()}.lock", "a")
        self._run_lock_acquired = False

    def _migrate(self) -> None:
        """Bring older databases to the current schema without losing history."""
        self._migrate_notifications()
        self._migrate_seen_posts()

    def _migrate_notifications(self) -> None:
        """Add new columns and rebuild when the old unique constraint exists."""
        columns = {row[1] for row in self._conn.execute("PRAGMA table_info(notifications)")}
        for name, column_type in NEW_NOTIFICATION_COLUMNS.items():
            if name not in columns:
                self._conn.execute(f"ALTER TABLE notifications ADD COLUMN {name} {column_type}")
        columns = {row[1] for row in self._conn.execute("PRAGMA table_info(notifications)")}
        if "dedupe_key" in columns:
            self._refresh_dedupe_keys()
            return
        self._rebuild_notifications()

    def _refresh_dedupe_keys(self) -> None:
        """Recompute stored keys after the identity rule changes."""
        rows = self._conn.execute("SELECT * FROM notifications").fetchall()
        stale = any(
            build_event_key(
                row["match"],
                row["match_date"],
                row["sale_start_at"],
                row["sale_phase"],
            )
            != row["dedupe_key"]
            for row in rows
        )
        if stale:
            self._rebuild_notifications()

    def _rebuild_notifications(self) -> None:
        """Replace the legacy (match, phase) constraint with a dedupe_key."""
        rows = self._conn.execute("SELECT * FROM notifications").fetchall()
        self._conn.execute("ALTER TABLE notifications RENAME TO notifications_legacy")
        self._conn.execute(NOTIFICATIONS_TABLE)
        for row in rows:
            key = build_event_key(
                row["match"],
                row["match_date"],
                row["sale_start_at"],
                row["sale_phase"],
            )
            self._conn.execute(
                "INSERT OR IGNORE INTO notifications "
                "(source, match, match_date, sale_phase, sale_start_at, official_url, "
                "venue_type, venue, announcement_url, status, notified_at, dedupe_key) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    row["source"],
                    row["match"],
                    row["match_date"],
                    row["sale_phase"],
                    row["sale_start_at"],
                    row["official_url"],
                    row["venue_type"],
                    row["venue"],
                    row["announcement_url"],
                    row["status"],
                    row["notified_at"],
                    key,
                ),
            )
        self._conn.execute("DROP TABLE notifications_legacy")

    def _migrate_seen_posts(self) -> None:
        """Normalize legacy post keys (raw URLs) to the stable identity format."""
        rows = self._conn.execute("SELECT * FROM seen_posts").fetchall()
        if not any(not str(row["post_key"]).startswith(("url:", "id:")) for row in rows):
            return
        self._conn.execute("ALTER TABLE seen_posts RENAME TO seen_posts_legacy")
        self._conn.execute(SEEN_POSTS_TABLE)
        for row in rows:
            key = row["post_key"]
            if not str(key).startswith(("url:", "id:")):
                key = post_identity(row["url"], key)
            self._conn.execute(
                "INSERT OR IGNORE INTO seen_posts "
                "(post_key, source, title, url, published_at, modified_at, parsed, first_seen_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    key,
                    row["source"],
                    row["title"],
                    row["url"],
                    row["published_at"],
                    row["modified_at"],
                    row["parsed"],
                    row["first_seen_at"],
                ),
            )
        self._conn.execute("DROP TABLE seen_posts_legacy")

    def close(self) -> None:
        """Close the database connection."""
        self.release_run_lock()
        self._run_lock_file.close()
        with self._lock:
            self._conn.close()

    def acquire_run_lock(self) -> bool:
        """Acquire a non-blocking lock shared by all monitor processes."""
        if not self._run_lock_guard.acquire(blocking=False):
            return False
        try:
            fcntl.flock(self._run_lock_file.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            self._run_lock_guard.release()
            return False
        self._run_lock_acquired = True
        return True

    def release_run_lock(self) -> None:
        if self._run_lock_acquired:
            fcntl.flock(self._run_lock_file.fileno(), fcntl.LOCK_UN)
            self._run_lock_acquired = False
            self._run_lock_guard.release()

    def is_notified(self, dedupe_key: str) -> bool:
        """Return True when this sale window was already notified."""
        with self._lock:
            row = self._conn.execute(
                "SELECT 1 FROM notifications WHERE dedupe_key = ?",
                (dedupe_key,),
            ).fetchone()
            return row is not None

    def get_notification(self, dedupe_key: str) -> dict[str, Any] | None:
        with self._lock:
            row = self._conn.execute(
                "SELECT * FROM notifications WHERE dedupe_key = ?", (dedupe_key,)
            ).fetchone()
            return dict(row) if row else None

    def update_notification(self, event: TicketSaleEvent, notified_at: str) -> None:
        with self._lock:
            self._conn.execute(
                "UPDATE notifications SET source=?, match=?, match_date=?, sale_phase=?, "
                "sale_start_at=?, official_url=?, venue_type=?, venue=?, announcement_url=?, "
                "status=?, notified_at=? WHERE dedupe_key=?",
                (
                    event.source, event.match, event.match_date, event.sale_phase,
                    event.sale_start_at, event.official_url, event.venue_type, event.venue,
                    event.announcement_url, event.status, notified_at, event.dedupe_key,
                ),
            )
            self._conn.commit()

    def record(self, event: TicketSaleEvent, notified_at: str) -> bool:
        """Insert a notification record; return False when it was a duplicate."""
        with self._lock:
            cursor = self._conn.execute(
                "INSERT OR IGNORE INTO notifications "
                "(source, match, match_date, sale_phase, sale_start_at, official_url, "
                "venue_type, venue, announcement_url, status, notified_at, dedupe_key) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
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
                    event.dedupe_key,
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

    def get_post(self, post_key: str) -> dict[str, Any] | None:
        """Return the last processed revision of a post."""
        with self._lock:
            row = self._conn.execute(
                "SELECT * FROM seen_posts WHERE post_key = ?", (post_key,)
            ).fetchone()
            return dict(row) if row else None

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
                "INSERT INTO seen_posts "
                "(post_key, source, title, url, published_at, modified_at, parsed, first_seen_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?) "
                "ON CONFLICT(post_key) DO UPDATE SET title=excluded.title, url=excluded.url, "
                "published_at=excluded.published_at, modified_at=excluded.modified_at, "
                "parsed=excluded.parsed",
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

    def alert_sent(self, alert_key: str) -> bool:
        """Return True when this health alert was already sent."""
        with self._lock:
            row = self._conn.execute(
                "SELECT 1 FROM system_alerts WHERE alert_key = ?", (alert_key,)
            ).fetchone()
            return row is not None

    def queue_alert(self, alert_key: str, message: str) -> None:
        with self._lock:
            self._conn.execute(
                "INSERT OR IGNORE INTO pending_alerts (alert_key, message) VALUES (?, ?)",
                (alert_key, message),
            )
            self._conn.commit()

    def pending_alerts(self) -> list[dict[str, str]]:
        with self._lock:
            rows = self._conn.execute(
                "SELECT alert_key, message FROM pending_alerts WHERE sent_at IS NULL"
            ).fetchall()
            return [dict(row) for row in rows]

    def alert_delivered(self, alert_key: str) -> bool:
        with self._lock:
            row = self._conn.execute(
                "SELECT 1 FROM pending_alerts WHERE alert_key = ? AND sent_at IS NOT NULL",
                (alert_key,),
            ).fetchone()
            return row is not None

    def mark_alert_delivered(self, alert_key: str, sent_at: str) -> None:
        with self._lock:
            self._conn.execute(
                "UPDATE pending_alerts SET sent_at = ? WHERE alert_key = ?",
                (sent_at, alert_key),
            )
            self._conn.commit()

    def store_event_seen(self, event_key: str) -> bool:
        with self._lock:
            return self._conn.execute(
                "SELECT 1 FROM store_events WHERE event_key = ?", (event_key,)
            ).fetchone() is not None

    def record_store_event(self, event_key: str, first_seen_at: str) -> None:
        with self._lock:
            self._conn.execute(
                "INSERT OR IGNORE INTO store_events (event_key, first_seen_at) VALUES (?, ?)",
                (event_key, first_seen_at),
            )
            self._conn.commit()

    def record_alert(self, alert_key: str, sent_at: str) -> bool:
        """Record a health alert; return False when it was already recorded."""
        with self._lock:
            cursor = self._conn.execute(
                "INSERT OR IGNORE INTO system_alerts (alert_key, sent_at) VALUES (?, ?)",
                (alert_key, sent_at),
            )
            self._conn.commit()
            return cursor.rowcount > 0
