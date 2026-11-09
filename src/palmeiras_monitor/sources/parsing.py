"""Parsing helpers for Palmeiras/Avanti ticket sale announcements."""

from __future__ import annotations

import re
from datetime import datetime, timedelta
from typing import Any

from bs4 import BeautifulSoup

from ..models import (
    BRAZIL_TZ,
    SALE_PHASE_ANNOUNCED,
    SALE_PHASE_OPEN,
    VENUE_AWAY,
    VENUE_HOME,
    VENUE_NEUTRAL,
    VENUE_UNKNOWN,
    TicketSaleEvent,
)

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

# Venue names are matched after "no/na/em" and classified as home/away/neutral.
VENUE_RE = re.compile(
    r"\b(?:no|na|em)\s+("
    r"(?:Estádio|Arena|Allianz|Nubank|Maracanã|Morumbi|Mineirão|Centenário|Monumental|"
    r"Neo Química|Vila Belmiro|Castelão|Mané Garrincha)"
    r"[^,.;\n]{0,70})",
    re.IGNORECASE,
)
HOME_VENUES = ("nubank parque", "allianz parque", "arena barueri", "arena crefisa", "crefisa barueri")
NEUTRAL_VENUES = ("centenário", "centenario", "montevidéu", "montevideu")

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
    """Extract a 'dia DD de mês' date and return it as ISO.

    The year is rolled forward when the month/day already passed relative to
    the reference (e.g. a January match announced in December).
    """
    match = DAY_MONTH_RE.search(text)
    if not match:
        return None
    month = MONTHS.get(match.group(2).lower().replace("ç", "ç"))
    if month is None:
        return None
    day = int(match.group(1))
    for year in (reference.year, reference.year + 1):
        try:
            candidate = datetime(year, month, day).date()
        except ValueError:
            continue
        if candidate >= reference.date():
            return candidate.isoformat()
    return None


def extract_ticket_url(html: str, fallback: str | None) -> str | None:
    """Return the first official ticket link found in the announcement."""
    match = TICKET_URL_RE.search(html or "")
    return match.group(0) if match else fallback


def post_plain_text(post: dict[str, Any]) -> tuple[str, str, str]:
    """Return (title, html, text) for a WordPress post."""
    title = clean_text((post.get("title") or {}).get("rendered", ""))
    html = (post.get("content") or {}).get("rendered", "")
    return title, html, clean_text(html)


def contains_ingresso(post: dict[str, Any]) -> bool:
    """Return True when the post title or body mentions tickets."""
    title, _, text = post_plain_text(post)
    return "ingresso" in f"{title}\n{text}".lower()


def classify_venue(text: str) -> tuple[str, str | None]:
    """Classify the match as home, away, or neutral from the announcement venue."""
    opening = " ".join((text or "").split())[:700]

    # Use the first venue mentioned: posts may cite Allianz Parque later as a
    # comparison while the actual match is away.
    for match in VENUE_RE.finditer(opening):
        venue = match.group(1).strip(" .,-")
        haystack = venue.lower()
        if any(name in haystack for name in HOME_VENUES):
            return VENUE_HOME, venue
        if any(name in haystack for name in NEUTRAL_VENUES):
            return VENUE_NEUTRAL, venue
        return VENUE_AWAY, venue

    if "fora de casa" in opening.lower() or "como visitante" in opening.lower():
        return VENUE_AWAY, None
    return VENUE_UNKNOWN, None


def build_event_from_post(
    post: dict[str, Any],
    source: str,
    lookback_days: int = 30,
    now: datetime | None = None,
) -> TicketSaleEvent | None:
    """Turn a WordPress post into a TicketSaleEvent, or None when irrelevant."""
    title, html, text = post_plain_text(post)
    link = post.get("link") or ""
    combined = f"{title}\n{text}"

    if "ingresso" not in combined.lower():
        return None

    sale_start = diamond_presale_start(text)
    if sale_start is None:
        return None

    current = now or datetime.now(BRAZIL_TZ)
    current_naive = current.replace(tzinfo=None) if current.tzinfo else current
    if sale_start < current_naive - timedelta(days=lookback_days):
        return None

    match = extract_teams(combined) or title or "Palmeiras"
    match_date = extract_match_date(text, sale_start) or "TBD"
    if match_date != "TBD":
        try:
            if datetime.fromisoformat(match_date).date() < current_naive.date():
                return None
        except ValueError:
            pass
    official_url = extract_ticket_url(html, link or None)
    phase = SALE_PHASE_OPEN if OPEN_MARKERS.search(text) else SALE_PHASE_ANNOUNCED
    venue_type, venue = classify_venue(text)

    return TicketSaleEvent(
        source=source,
        match=match,
        match_date=match_date,
        sale_phase=phase,
        sale_start_at=sale_start.isoformat(timespec="minutes"),
        official_url=official_url,
        venue_type=venue_type,
        venue=venue,
        announcement_url=link or None,
    )
