"""Telegram notification sender."""

from __future__ import annotations

import logging
import time
from datetime import datetime

import httpx

from .models import TicketSaleEvent

TELEGRAM_SEND_MESSAGE_URL = "https://api.telegram.org/bot{bot_token}/sendMessage"
TELEGRAM_TITLE = "🎟️ PALMEIRAS — AVANTI DIAMANTE"
TELEGRAM_PARSE_MODE = "Markdown"


def _format_sale_start(value: str | None) -> str:
    if not value:
        return "TBD"
    try:
        return datetime.fromisoformat(value).strftime("%d/%m/%Y %H:%M")
    except ValueError:
        return value


def build_message(event: TicketSaleEvent, checked_at: datetime) -> str:
    """Build the notification text for a ticket sale event."""
    return "\n".join(
        [
            TELEGRAM_TITLE,
            "",
            f"🏟️ Match: {event.match}",
            f"📅 Match date: {event.match_date}",
            f"💎 Diamond ticket sales: {_format_sale_start(event.sale_start_at)}",
            f"🟢 Status: {event.status}",
            f"🔗 Official ticket link: {event.official_url or 'TBD'}",
            f"⏰ Checked at: {checked_at:%Y-%m-%d %H:%M:%S}",
        ]
    )


class TelegramNotifier:
    """Sends ticket sale notifications through the Telegram Bot API."""

    def __init__(self, bot_token: str, chat_id: str, timeout: float = 10.0, attempts: int = 3) -> None:
        self.bot_token = bot_token
        self.chat_id = chat_id
        self.timeout = timeout
        self.attempts = attempts

    def _redact(self, exc: Exception) -> str:
        """Remove the bot token from exception text before logging it."""
        return str(exc).replace(self.bot_token, "<redacted>") if self.bot_token else str(exc)

    def send(self, text: str) -> str | None:
        """Send a message, retrying transient failures."""
        last_error: str | None = None
        for attempt in range(1, self.attempts + 1):
            try:
                response = httpx.post(
                    TELEGRAM_SEND_MESSAGE_URL.format(bot_token=self.bot_token),
                    json={
                        "chat_id": self.chat_id,
                        "text": text,
                        "parse_mode": TELEGRAM_PARSE_MODE,
                    },
                    timeout=self.timeout,
                )
                response.raise_for_status()
                payload = response.json()
                return str(payload.get("message_id", ""))
            except Exception as exc:  # noqa: BLE001 - retry any transient failure
                last_error = self._redact(exc)
                logging.getLogger("palmeiras_monitor").warning(
                    "Telegram send attempt %s/%s failed: %s", attempt, self.attempts, last_error
                )
                if attempt < self.attempts:
                    time.sleep(2 ** attempt)
        raise RuntimeError(f"Telegram notification failed after {self.attempts} attempts: {last_error}")
