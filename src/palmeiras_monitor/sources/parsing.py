"""Parsing helpers for Palmeiras/Avanti ticket sale announcements."""

from __future__ import annotations

import re
from datetime import datetime, timedelta
from typing import Any

from bs4 import BeautifulSoup

from ..models import BRAZIL_TZ, SALE_PHASE_ANNOUNCED, SALE_PHASE_OPEN, TicketSaleEvent

MONTHS = {
    "janeiro": 1,
    "fevereiro": 2,
    "marco": 3,
    "março": 3,
    "abril": 4,
    "maio": 5,
    "junho": 6,
    "julho": 7,
    "agosto": 8,
    "setembro": 9,
    "outubro": 10,
    "novembro": 11,
    "dezembro": 12,
}

PRESALE_RE = re.compile(
    r"(\d)ª\s*Pré-venda\s*\n?\s*Início:\s*(\d{2})/(\d{2})/(\d{4})\s*[–\-]\s*(\d{1,2})h(\d{2})?",
    re.IGNORECASE,
)
DIAMOND_RE = re.compile(r"diamante", re.IGNORECASE)
OPEN_MARKERS = re.compile(
    r"vendas abertas|j[áa] est[ãa]o [àa] venda|j[áa] est[áa] [àa] venda",
    re.IGNORECASE,
)
TICKET_URL_RE = re.compile(
    r"https?://(?:www\.)?(?:ingressospalmeiras\.com\.br|libertadores\.eleventickets\.com)[^\s\"'<>]*",
    re.IGNORECASE,
)
DAY_MONTH_RE = re.compile(r"dia\s+(\d{1,2})\s+de\s+([a-zçãéêô]+)", re.IGNORECASE)

_TEAM = r"[A-ZÀ-Ü][\wÀ-ú.\-']*(?:\s+[A-ZÀ-Ü][\wÀ-ú.\-']*){0,3}"
TEAMS_PAL_FIRST_RE = re.compile(rf"Palmeiras\s*[xX]\s*({_TEAM})")
TEAMS_PAL_LAST_RE = re.compile(rf"({_TEAM})\s*[xX]\s*Palmeiras")
ENFRENTA_RE = re.compile(rf"enfrenta\s+(?:o|a)\s+({_TEAM})")
ENCARA_RE = re.compile(rf"encara\s+(?:o|a)\s+({_TEAM})")
CONTRA_RE = re.compile(rf"contra\s+(?:o|a)\s+({_TEAM})")
DIANTE_RE = re.compile(rf"diante\s+do\s+({_TEAM})")


def clean_text(html: str) -> str:
    """Convert an HTML fragment to plain text."""
    return BeautifulSoup(html or "", "html.parser").get_text("\n", strip=True)


def _presale_blocks(text: str) -> list[tuple[str, datetime]]:
    """Return (block_text, start_datetime) for every pré-venda block."""
    matches = list(PRESALE_RE.finditer(text))
    blocks: list[tuple[str, datetime]] = []
    for index, match in enumerate(matches):
        end = matches[index + 1].start() if index + 1 < len(matches) else len(text)
        block = text[match.start() : end]
        start = datetime(
            year=int(match.group(4)),
            month=int(match.group(3)),
            day=int(match.group(2)),
            hour=int(match.group(5)),
            minute=int(match.group(6) or 0),
        )
        blocks.append((block, start))
    return blocks


def diamond_presale_start(text: str) -> datetime | None:
    """Find the first pre-sale block that includes the Diamante plan."""
    for block, start in _presale_blocks(text):
        if DIAMOND_RE.search(block):
            return start
    return None


def extract_teams(text: str) -> str | None:
    """Best-effort extraction of the match pairing from announcement text."""
    for pattern in (TEAMS_PAL_FIRST_RE, TEAMS_PAL_LAST_RE):
        match = pattern.search(text)
        if match:
            team = match.group(1).strip(" .,-")
            if pattern is TEAMS_PAL_FIRST_RE:
                return f"Palmeiras x {team}"
            return f"{team} x Palmeiras"
    for pattern in (ENFRENTA_RE, ENCARA_RE, CONTRA_RE, DIANTE_RE):
        match = pattern.search(text)
        if match:
            return f"Palmeiras x {match.group(1).strip(' .,-')}"
    return None


def extract_match_date(text: str, reference: datetime) -> str | None:
    """Extract a 'dia DD de mês' date and return it as ISO."""
    match = DAY_MONTH_RE.search(text)
    if not match:
        return None
    month = MONTHS.get(match.group(2).lower().replace("ç", "ç"))
    if month is None:
        return None
    day = int(match.group(1))
    try:
        return datetime(reference.year, month, day).date().isoformat()
    except ValueError:
        return None


def extract_ticket_url(html: str, fallback: str | None) -> str | None:
    """Return the first official ticket link found in the announcement."""
    match = TICKET_URL_RE.search(html or "")
    return match.group(0) if match else fallback


def build_event_from_post(
    post: dict[str, Any],
    source: str,
    lookback_days: int = 30,
) -> TicketSaleEvent | None:
    """Turn a WordPress post into a TicketSaleEvent, or None when irrelevant."""
    title = clean_text((post.get("title") or {}).get("rendered", ""))
    link = post.get("link") or ""
    html = (post.get("content") or {}).get("rendered", "")
    text = clean_text(html)
    combined = f"{title}\n{text}"

    if "ingresso" not in combined.lower():
        return None

    sale_start = diamond_presale_start(text)
    if sale_start is None:
        return None

    now = datetime.now(BRAZIL_TZ).replace(tzinfo=None)
    if sale_start < now - timedelta(days=lookback_days):
        return None

    match = extract_teams(combined) or title or "Palmeiras"
    match_date = extract_match_date(text, sale_start) or "TBD"
    if match_date != "TBD":
        try:
            if datetime.fromisoformat(match_date).date() < now.date():
                return None
        except ValueError:
            pass
    official_url = extract_ticket_url(html, link or None)
    phase = SALE_PHASE_OPEN if OPEN_MARKERS.search(text) else SALE_PHASE_ANNOUNCED

    return TicketSaleEvent(
        source=source,
        match=match,
        match_date=match_date,
        sale_phase=phase,
        sale_start_at=sale_start.isoformat(timespec="minutes"),
        official_url=official_url,
    )
