"""Telegram notification sender."""

from __future__ import annotations

import logging
import time
from datetime import datetime

import httpx

from .models import TicketSaleEvent

TELEGRAM_SEND_MESSAGE_URL = "https://api.telegram.org/bot{bot_token}/sendMessage"
TELEGRAM_TITLE = "🎟️ PALMEIRAS — AVANTI DIAMANTE"


def _format_sale_start(value: str | None) -> str:
    if not value:
        return "TBD"
    try:
        return datetime.fromisoformat(value).strftime("%d/%m/%Y %H:%M")
    except ValueError:
        return value


def build_message(event: TicketSaleEvent, checked_at: datetime) -> str:
    """Build the notification text for a ticket sale event."""
    venue = event.venue or "TBD"
    return "\n".join(
        [
            TELEGRAM_TITLE,
            "",
            f"🏟️ Match: {event.match}",
            f"📅 Match date: {event.match_date}",
            f"📍 Venue: {venue} — {event.venue_label}",
            f"💎 Diamond ticket sales: {_format_sale_start(event.sale_start_at)}",
            f"🟢 Status: {event.status}",
            f"🔗 Official ticket link: {event.official_url or 'TBD'}",
            f"📰 Announcement: {event.announcement_url or 'TBD'}",
            f"⏰ Checked at: {checked_at:%Y-%m-%d %H:%M:%S}",
        ]
    )


def build_sale_change_message(
    event: TicketSaleEvent, previous_sale_start: str | None, checked_at: datetime
) -> str:
    """Build a notice for a changed Diamante sale start time."""
    previous = _format_sale_start(previous_sale_start)
    current = _format_sale_start(event.sale_start_at)
    return build_message(event, checked_at).replace(
        TELEGRAM_TITLE,
        f"{TELEGRAM_TITLE}\n\n🔄 Horário da pré-venda Diamante alterado.\n"
        f"Antes: {previous}\nAgora: {current}",
        1,
    )


def build_unparsed_message(title: str, link: str, published_at: str | None = None) -> str:
    """Build a fallback alert for a new ticket post the parser could not read."""
    return "\n".join(
        [
            TELEGRAM_TITLE,
            "",
            "⚠️ Post novo com \"ingresso\", mas não identifiquei a janela Diamante.",
            "",
            f"📰 {title or 'Post sem título'}",
            f"📅 Published: {published_at or 'TBD'}",
            f"🔗 {link or 'TBD'}",
            "",
            "Verifique manualmente — pode ser formato novo, tabela ou imagem.",
        ]
    )


def build_updated_message(event: TicketSaleEvent, checked_at: datetime) -> str:
    """Build a notice when an already-seen ticket announcement was edited."""
    return build_message(event, checked_at).replace(
        TELEGRAM_TITLE, f"{TELEGRAM_TITLE}\n\n✏️ A notícia oficial de ingressos foi atualizada.", 1
    )


def build_source_failure_message(source: str, reason: str, checked_at: datetime) -> str:
    """Build an alert for a source that raised an error during the pass."""
    return "\n".join(
        [
            TELEGRAM_TITLE,
            "",
            f"⚠️ Monitor: a fonte \"{source}\" falhou.",
            f"Motivo: {reason}",
            f"⏰ Checked at: {checked_at:%Y-%m-%d %H:%M:%S}",
            "",
            "A checagem pode estar cega até a próxima execução.",
        ]
    )


def build_empty_feed_message(source: str, checked_at: datetime) -> str:
    """Build an alert for a source that returned no posts at all."""
    return "\n".join(
        [
            TELEGRAM_TITLE,
            "",
            f"⚠️ Monitor: a fonte \"{source}\" não retornou nenhum post.",
            f"⏰ Checked at: {checked_at:%Y-%m-%d %H:%M:%S}",
            "",
            "Pode ser falha da API ou mudança de endpoint. Verifique a fonte oficial.",
        ]
    )


def build_store_open_message(
    sale_start_at: datetime | None,
    target_url: str | None,
    announcement_url: str | None,
    match: str | None,
    checked_at: datetime,
) -> str:
    """Build an alert for a live queue at the official ticket store."""
    start = (
        sale_start_at.strftime("%d/%m/%Y %H:%M") if sale_start_at else "horário não informado"
    )
    return "\n".join(
        [
            TELEGRAM_TITLE,
            "",
            "🟢 Vendas abertas na bilheteria oficial.",
            f"⚽ Jogo: {match or 'não identificado'}",
            f"💎 Início informado pela bilheteria: {start}",
            "🔗 Bilheteria: https://ingressospalmeiras.com.br/",
            f"🎯 Destino oficial: {target_url or 'TBD'}",
            f"📰 Notícia oficial: {announcement_url or 'não localizada'}",
            f"⏰ Checked at: {checked_at:%Y-%m-%d %H:%M:%S}",
            "",
            "Confirme o jogo e o setor no link antes de comprar.",
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
