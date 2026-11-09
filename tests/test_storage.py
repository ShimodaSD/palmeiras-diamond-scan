"""Tests for stable post/event identities and database migration."""

from __future__ import annotations

import sqlite3
import tempfile
import unittest
from pathlib import Path

from palmeiras_monitor.models import (
    SALE_PHASE_ANNOUNCED,
    TicketSaleEvent,
    build_event_key,
    normalize_match,
    post_identity,
)
from palmeiras_monitor.storage import Storage

LEGACY_SCHEMA = """
CREATE TABLE notifications (
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
CREATE TABLE seen_posts (
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


def event(match: str, match_date: str = "2026-11-20", sale: str = "2026-11-10T12:00") -> TicketSaleEvent:
    return TicketSaleEvent(
        source="palmeiras",
        match=match,
        match_date=match_date,
        sale_phase=SALE_PHASE_ANNOUNCED,
        sale_start_at=sale,
    )


class IdentityTests(unittest.TestCase):
    def test_normalize_match_ignores_case_accents_and_punctuation(self) -> None:
        self.assertEqual(
            normalize_match("Palmeiras x São Paulo"),
            normalize_match("palmeiras X sao-paulo"),
        )

    def test_post_identity_normalizes_url(self) -> None:
        self.assertEqual(
            post_identity("https://Palmeiras.com.br/noticias/remo/?utm=1#top"),
            "url:https://palmeiras.com.br/noticias/remo",
        )

    def test_post_identity_falls_back_to_id(self) -> None:
        self.assertEqual(post_identity(None, 1234), "id:1234")
        self.assertEqual(post_identity("", None), "")

    def test_dedupe_key_ignores_source_but_not_fixture(self) -> None:
        a = event("Palmeiras x São Paulo")
        b = TicketSaleEvent(
            source="avanti",
            match="palmeiras X sao paulo",
            match_date=a.match_date,
            sale_phase=a.sale_phase,
            sale_start_at=a.sale_start_at,
        )
        self.assertEqual(a.dedupe_key, b.dedupe_key)
        self.assertNotEqual(a.dedupe_key, event("Palmeiras x São Paulo", "2027-11-20").dedupe_key)
        self.assertNotEqual(
            a.dedupe_key,
            event("Palmeiras x São Paulo", sale="2026-11-11T12:00").dedupe_key,
        )


class DedupeStorageTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.db = str(Path(self.tmp.name) / "test.db")
        self.storage = Storage(self.db)

    def tearDown(self) -> None:
        self.storage.close()
        self.tmp.cleanup()

    def test_record_dedupes_spelling_variants(self) -> None:
        self.assertTrue(self.storage.record(event("Palmeiras x São Paulo"), "2026-11-09 09:00:00"))
        self.assertFalse(
            self.storage.record(event("palmeiras X sao paulo"), "2026-11-09 15:00:00")
        )
        self.assertTrue(self.storage.is_notified(event("Palmeiras x São Paulo").dedupe_key))

    def test_new_fixture_same_teams_is_not_suppressed(self) -> None:
        self.assertTrue(self.storage.record(event("Palmeiras x São Paulo"), "2026-11-09 09:00:00"))
        self.assertTrue(
            self.storage.record(
                event("Palmeiras x São Paulo", "2027-11-20"), "2027-11-09 09:00:00"
            )
        )


class LegacyMigrationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.db = str(Path(self.tmp.name) / "legacy.db")
        conn = sqlite3.connect(self.db)
        conn.executescript(LEGACY_SCHEMA)
        conn.execute(
            "INSERT INTO notifications "
            "(source, match, match_date, sale_phase, sale_start_at, official_url, status, notified_at) "
            "VALUES ('palmeiras', 'Palmeiras x Remo', '2026-11-05', 'announced', "
            "'2026-10-29T12:00', 'https://ingressospalmeiras.com.br', 'Announced', "
            "'2026-10-28 21:00:00')"
        )
        conn.execute(
            "INSERT INTO seen_posts "
            "(post_key, source, title, url, published_at, modified_at, parsed, first_seen_at) "
            "VALUES ('https://palmeiras.com.br/noticias/remo/?utm=1', 'palmeiras', 'Remo', "
            "'https://palmeiras.com.br/noticias/remo/?utm=1', '2026-10-28', '2026-10-28', 1, "
            "'2026-10-28 21:00:00')"
        )
        conn.commit()
        conn.close()

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def test_migration_backfills_keys_and_drops_old_constraint(self) -> None:
        storage = Storage(self.db)
        try:
            key = build_event_key("Palmeiras x Remo", "2026-11-05", "2026-10-29T12:00", "announced")
            self.assertTrue(storage.is_notified(key))

            self.assertTrue(
                storage.post_seen(post_identity("https://palmeiras.com.br/noticias/remo/"))
            )
            self.assertEqual(storage.count_posts(), 1)

            # The legacy UNIQUE(match, sale_phase) must be gone.
            self.assertTrue(
                storage.record(
                    event("Palmeiras x Remo", "2027-11-05", "2027-10-29T12:00"),
                    "2027-10-28 21:00:00",
                )
            )
            self.assertEqual(len(storage.get_history()), 2)
        finally:
            storage.close()


if __name__ == "__main__":
    unittest.main()
