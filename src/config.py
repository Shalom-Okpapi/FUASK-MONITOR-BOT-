"""Configuration loading and validation for the FUASK monitor bot.

Fails fast if required settings are missing or malformed — this catches
misconfiguration in CI logs immediately, before any HTTP requests happen.
"""
import os
from dataclasses import dataclass

from dotenv import load_dotenv

load_dotenv()


class ConfigError(Exception):
    """Raised when required configuration is missing or invalid."""


@dataclass(frozen=True)
class Settings:
    monitor_url: str
    telegram_bot_token: str
    telegram_chat_id: str
    timeout_seconds: float
    latency_threshold_ms: float
    failure_threshold: int
    heartbeat_interval_minutes: float
    check_retries: int
    check_retry_delay_seconds: float
    dry_run: bool


def _require(name: str) -> str:
    value = os.environ.get(name, "").strip()
    if not value:
        raise ConfigError(f"Missing required environment variable: {name}")
    return value


def _bool_env(name: str, default: bool) -> bool:
    raw = os.environ.get(name)
    if raw is None:
        return default
    return raw.strip().lower() in ("1", "true", "yes", "on")


def load_settings() -> Settings:
    monitor_url = _require("MONITOR_URL")
    if not monitor_url.startswith("https://"):
        # HTTPS-only, no exceptions — this is a public-facing monitor, not a
        # local dev tool, so plain HTTP targets are rejected outright.
        raise ConfigError("MONITOR_URL must use HTTPS")

    bot_token = _require("TELEGRAM_BOT_TOKEN")
    chat_id = _require("TELEGRAM_CHAT_ID")

    return Settings(
        monitor_url=monitor_url,
        telegram_bot_token=bot_token,
        telegram_chat_id=chat_id,
        timeout_seconds=float(os.environ.get("TIMEOUT_SECONDS", "10")),
        latency_threshold_ms=float(os.environ.get("LATENCY_THRESHOLD_MS", "3000")),
        # 1 = alert on the very first confirmed failure (the in-check retry
        # in checker.py is what filters out single transient blips, so this
        # can safely be 1 instead of waiting across multiple 5-min cycles).
        failure_threshold=int(os.environ.get("FAILURE_THRESHOLD", "1")),
        # Routine "still healthy" report cadence — every 2 hours by default.
        heartbeat_interval_minutes=float(os.environ.get("HEARTBEAT_INTERVAL_MINUTES", "120")),
        check_retries=int(os.environ.get("CHECK_RETRIES", "1")),
        check_retry_delay_seconds=float(os.environ.get("CHECK_RETRY_DELAY_SECONDS", "3")),
        dry_run=_bool_env("DRY_RUN", False),
  )
