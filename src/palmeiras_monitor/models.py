"""Domain models for ticket sale monitoring."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
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
    def dedupe_key(self) -> tuple[str, str, str]:
        """Identity used to avoid duplicate notifications."""
        return (self.source, self.match, self.sale_phase)

    @property
    def checked_at_label(self) -> str:
        return datetime.now(BRAZIL_TZ).strftime("%Y-%m-%d %H:%M:%S")
