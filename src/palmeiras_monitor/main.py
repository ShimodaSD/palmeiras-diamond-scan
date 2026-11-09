"""Entry point for the Palmeiras Diamond ticket monitor."""

from __future__ import annotations

import time

from .collector import Collector
from .config import Config, validate_config
from .logging_setup import configure_logging
from .notifier import TelegramNotifier
from .scheduler import TicketMonitorScheduler
from .sources import DEFAULT_SOURCES
from .storage import Storage


def run() -> int:
    """Run the ticket monitor until stopped."""
    config = Config.from_env()
    validate_config(config)
    logger = configure_logging(config.log_level)

    storage = Storage(config.database_path)
    notifier = TelegramNotifier(config.telegram_bot_token, config.telegram_chat_id)
    collector = Collector(
        sources=DEFAULT_SOURCES,
        storage=storage,
        notifier=notifier,
        logger=logger,
        dry_run=config.dry_run,
        timezone=config.tzinfo,
    )
    if config.run_once:
        sent = collector.run_once()
        logger.info("Single pass finished: %s new event(s)", len(sent))
        storage.close()
        return 0
    scheduler = TicketMonitorScheduler(
        interval_seconds=config.check_interval_seconds,
        handler=collector.run_once,
    )
    scheduler.start()
    logger.info("Ticket monitor started (interval=%ss)", config.check_interval_seconds)
    try:
        while scheduler.is_running():
            time.sleep(1)
    except KeyboardInterrupt:
        logger.info("Shutting down ticket monitor")
    finally:
        scheduler.stop()
        storage.close()
    return 0
