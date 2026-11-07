"""Tests for notification security helpers (no network)."""

from __future__ import annotations

import unittest

from palmeiras_monitor.notifier import TelegramNotifier


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


if __name__ == "__main__":
    unittest.main()
