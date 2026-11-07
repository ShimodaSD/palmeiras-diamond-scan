"""Domain models for ticket sale monitoring."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from zoneinfo import ZoneInfo

SALE_PHASE_ANNOUNCED = "announced"
SALE_PHASE_OPEN = "open"

STATUS_ANNOUNCED = "Announced"
STATUS_SALES_OPEN = "Sales Open"

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
