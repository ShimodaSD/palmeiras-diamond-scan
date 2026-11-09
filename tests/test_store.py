"""Ticket store queue detection tests; all HTTP responses are synthetic."""

from __future__ import annotations

import unittest
from unittest.mock import Mock

from palmeiras_monitor.sources.store import TicketStoreSource


class StoreSourceTests(unittest.TestCase):
    def test_queue_redirect_reports_event(self) -> None:
        client = Mock()
        client.probe.return_value = Mock(
            status_code=302,
            headers={
                "location": "https://palmeiras.queue-it.net/?e=202611061000&t=https%3A%2F%2Fpalmeiras.roboticket.com%2Fjogo"
            },
        )
        status = TicketStoreSource(client).check()
        self.assertTrue(status.active)
        self.assertEqual(status.event_key, "202611061000")
        self.assertEqual(status.sale_start_at.isoformat(), "2026-11-06T10:00:00")
        self.assertEqual(status.target_url, "https://palmeiras.roboticket.com/jogo")

    def test_unrelated_redirect_is_not_an_active_sale(self) -> None:
        client = Mock()
        client.probe.return_value = Mock(
            status_code=302, headers={"location": "https://evil.example/"}
        )
        self.assertFalse(TicketStoreSource(client).check().active)

    def test_store_error_raises_for_health_alert(self) -> None:
        client = Mock()
        response = Mock(status_code=503, headers={})
        response.raise_for_status.side_effect = RuntimeError("HTTP 503")
        client.probe.return_value = response
        with self.assertRaises(RuntimeError):
            TicketStoreSource(client).check()


if __name__ == "__main__":
    unittest.main()
