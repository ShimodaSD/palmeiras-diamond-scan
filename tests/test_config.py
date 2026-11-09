"""Tests for configuration parsing and validation."""

from __future__ import annotations

import os
import unittest
from unittest.mock import patch

from palmeiras_monitor.config import Config, validate_config


class ConfigTests(unittest.TestCase):
    def test_timezone_defaults_to_sao_paulo(self) -> None:
        with patch.dict(os.environ, {}, clear=True):
            config = Config.from_env()
        self.assertEqual(config.timezone, "America/Sao_Paulo")
        self.assertEqual(str(config.tzinfo), "America/Sao_Paulo")

    def test_timezone_from_env_is_used(self) -> None:
        with patch.dict(os.environ, {"TIMEZONE": "America/Manaus"}, clear=True):
            config = Config.from_env()
        self.assertEqual(str(config.tzinfo), "America/Manaus")

    def test_invalid_timezone_fails_validation(self) -> None:
        config = Config(
            telegram_bot_token="token",
            telegram_chat_id="chat",
            timezone="Mars/Olympus",
        )
        with self.assertRaises(ValueError) as ctx:
            validate_config(config)
        self.assertIn("Invalid TIMEZONE", str(ctx.exception))

    def test_valid_config_passes(self) -> None:
        config = Config(
            telegram_bot_token="token",
            telegram_chat_id="chat",
            timezone="America/Sao_Paulo",
        )
        validate_config(config)


if __name__ == "__main__":
    unittest.main()
