"""Logging configuration for the ticket monitor."""

from __future__ import annotations

import logging
import sys

LOGGER_NAME = "palmeiras_monitor"


def configure_logging(level_name: str = "INFO") -> logging.Logger:
    """Configure and return the application logger."""
    level = getattr(logging, str(level_name).upper(), logging.INFO)
    logger = logging.getLogger(LOGGER_NAME)
    logger.setLevel(level)
    logger.propagate = False
    if not logger.handlers:
        handler = logging.StreamHandler(sys.stdout)
        handler.setFormatter(
            logging.Formatter("%(asctime)s | %(levelname)s | %(name)s | %(message)s")
        )
        logger.addHandler(handler)
    return logger
