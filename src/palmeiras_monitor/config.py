"""Application configuration loaded from environment variables."""

from __future__ import annotations

import os
from dataclasses import dataclass
from zoneinfo import ZoneInfo

from dotenv import load_dotenv

load_dotenv()


@dataclass(frozen=True)
class Config:
    """Runtime configuration for the ticket monitor."""

    telegram_bot_token: str
    telegram_chat_id: str
    check_interval_seconds: int = 300
    timezone: str = "America/Sao_Paulo"
    database_path: str = "data/notifications.db"
    log_level: str = "INFO"
    dry_run: bool = False
    run_once: bool = False

    @property
    def tzinfo(self) -> ZoneInfo:
        """Resolve the configured IANA timezone."""
        return ZoneInfo(self.timezone)

    @classmethod
    def from_env(cls) -> "Config":
        """Build a Config instance from environment variables."""
        return cls(
            telegram_bot_token=os.environ.get("TELEGRAM_BOT_TOKEN", ""),
            telegram_chat_id=os.environ.get("TELEGRAM_CHAT_ID", ""),
            check_interval_seconds=int(os.environ.get("CHECK_INTERVAL_SECONDS", "300")),
            timezone=os.environ.get("TIMEZONE", "America/Sao_Paulo"),
            database_path=os.environ.get("DATABASE_PATH", "data/notifications.db"),
            log_level=os.environ.get("LOG_LEVEL", "INFO"),
            dry_run=_as_bool(os.environ.get("DRY_RUN", "0")),
            run_once=_as_bool(os.environ.get("RUN_ONCE", "0")),
        )


def _as_bool(value: str) -> bool:
    return value.strip().lower() in {"1", "true", "yes", "on"}


def validate_config(config: Config) -> None:
    """Fail fast when required secrets are missing or the timezone is invalid."""
    missing = [
        name
        for name, value in (
            ("TELEGRAM_BOT_TOKEN", config.telegram_bot_token),
            ("TELEGRAM_CHAT_ID", config.telegram_chat_id),
        )
        if not value
    ]
    if missing:
        raise ValueError(f"Missing required environment variables: {', '.join(missing)}")
    try:
        config.tzinfo
    except Exception as exc:
        raise ValueError(f"Invalid TIMEZONE {config.timezone!r}: {exc}") from exc
