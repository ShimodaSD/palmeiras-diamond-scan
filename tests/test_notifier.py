"""Tests for notification message content (no network)."""

from __future__ import annotations

import unittest
from datetime import datetime

from palmeiras_monitor.models import (
    SALE_PHASE_ANNOUNCED,
    VENUE_AWAY,
    VENUE_HOME,
    TicketSaleEvent,
)
from palmeiras_monitor.notifier import TelegramNotifier, build_message, build_unparsed_message


class NotifierSecurityTests(unittest.TestCase):
    def test_redacts_bot_token_from_exception_text(self) -> None:
        token = "123456:ABCDEF_secret-token"
        notifier = TelegramNotifier(token, "123456789")
        error = RuntimeError(
            f"Client error for url 'https://api.telegram.org/bot{token}/sendMessage'"
        )
        redacted = notifier._redact(error)
        self.assertNotIn(token, redacted)
        self.assertIn("<redacted>", redacted)


class MessageContentTests(unittest.TestCase):
    def _event(self, venue_type: str) -> TicketSaleEvent:
        return TicketSaleEvent(
            source="palmeiras",
            match="Palmeiras x Remo",
            match_date="2026-11-05",
            sale_phase=SALE_PHASE_ANNOUNCED,
            sale_start_at="2026-10-29T12:00",
            official_url="https://ingressospalmeiras.com.br",
            venue_type=venue_type,
            venue="Nubank Parque",
            announcement_url="https://palmeiras.com.br/noticias/remo/",
        )

    def test_home_message_shows_mandante(self) -> None:
        message = build_message(self._event(VENUE_HOME), datetime(2026, 10, 28, 21, 0))
        self.assertIn("Mandante", message)
        self.assertIn("Nubank Parque", message)
        self.assertIn("palmeiras.com.br/noticias/remo", message)

    def test_away_message_shows_visitante(self) -> None:
        message = build_message(self._event(VENUE_AWAY), datetime(2026, 10, 28, 21, 0))
        self.assertIn("Visitante", message)

    def test_unparsed_message_has_warning_and_link(self) -> None:
        message = build_unparsed_message(
            "Ingressos para jogo contra Fluminense",
            "https://palmeiras.com.br/noticias/fluminense/",
            "2026-10-12",
        )
        self.assertIn("não identifiquei a janela Diamante", message)
        self.assertIn("https://palmeiras.com.br/noticias/fluminense/", message)


if __name__ == "__main__":
    unittest.main()
