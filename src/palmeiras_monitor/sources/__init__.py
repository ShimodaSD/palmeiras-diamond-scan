"""Ticket sale source registry."""

from __future__ import annotations

from .avanti import AvantiSource
from .base import SaleSource
from .palmeiras import PalmeirasSource
from .store import TicketStoreSource

DEFAULT_SOURCES: list[SaleSource] = [PalmeirasSource(), AvantiSource()]
