"""Domain models for ticket sale monitoring."""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from datetime import datetime
from typing import Any
from urllib.parse import urlsplit, urlunsplit
from zoneinfo import ZoneInfo

SALE_PHASE_ANNOUNCED = "announced"
SALE_PHASE_OPEN = "open"

STATUS_ANNOUNCED = "Announced"
STATUS_SALES_OPEN = "Sales Open"

VENUE_HOME = "home"
VENUE_AWAY = "away"
VENUE_NEUTRAL = "neutral"
VENUE_UNKNOWN = "unknown"

VENUE_LABELS = {
    VENUE_HOME: "Mandante",
    VENUE_AWAY: "Visitante",
    VENUE_NEUTRAL: "Local neutro",
    VENUE_UNKNOWN: "Local não identificado",
}

BRAZIL_TZ = ZoneInfo("America/Sao_Paulo")


def normalize_match(value: str) -> str:
    """Normalize a match label so spelling/accent variants compare equal."""
    text = unicodedata.normalize("NFKD", value or "")
    text = "".join(char for char in text if not unicodedata.combining(char))
    text = re.sub(r"[^a-z0-9x]+", " ", text.lower())
    return " ".join(text.split())


def normalize_url(url: str) -> str:
    """Normalize an official post URL: no query, fragment or trailing slash."""
    raw = (url or "").strip()
    parts = urlsplit(raw)
    if not parts.scheme and not parts.netloc:
        return raw.rstrip("/")
    return urlunsplit((parts.scheme.lower(), parts.netloc.lower(), parts.path.rstrip("/"), "", ""))


def post_identity(url: str | None, post_id: Any = None) -> str:
    """Stable identity for an official post, independent of query strings."""
    normalized = normalize_url(url or "")
    if normalized:
        return f"url:{normalized}"
    return f"id:{post_id}" if post_id is not None else ""


def build_event_key(
    match: str,
    match_date: str,
    sale_start_at: str | None,
    sale_phase: str,
) -> str:
    """Stable identity for a sale window (not just the match name)."""
    window = (sale_start_at or "")[:16]
    return "|".join((normalize_match(match), match_date or "TBD", window, sale_phase))


@dataclass(frozen=True)
class TicketSaleEvent:
    """A single ticket sale announcement/opening for a match."""

    source: str
    match: str
    match_date: str
    sale_phase: str
    sale_start_at: str | None = None
    official_url: str | None = None
    venue_type: str = VENUE_UNKNOWN
    venue: str | None = None
    announcement_url: str | None = None

    @property
    def venue_label(self) -> str:
        """Human-readable home/away/neutral label."""
        return VENUE_LABELS.get(self.venue_type, VENUE_LABELS[VENUE_UNKNOWN])

    @property
    def status(self) -> str:
        """Human-readable status derived from the sale phase."""
        if self.sale_phase == SALE_PHASE_OPEN:
            return STATUS_SALES_OPEN
        return STATUS_ANNOUNCED

    @property
    def dedupe_key(self) -> str:
        """Identity used to avoid duplicate notifications.

        Includes the match date and sale window so the same pairing in a
        different fixture or season is not suppressed.
        """
        return build_event_key(self.match, self.match_date, self.sale_start_at, self.sale_phase)

    @property
    def checked_at_label(self) -> str:
        return datetime.now(BRAZIL_TZ).strftime("%Y-%m-%d %H:%M:%S")
