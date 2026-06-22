"""Configuration loading and validation for the FUASK monitor bot."""
import os
from dataclasses import dataclass

from dotenv import load_dotenv

load_dotenv()


class ConfigError(Exception):
    """Raised when required configuration is missing or invalid."""


@dataclass(frozen=True)
class Settings:
    monitor_urls: list
    telegram_bot_token: str
    telegram_chat_id: str
    timeout_seconds: float
    latency_threshold_ms: float
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
    raw_urls = _require("MONITOR_URLS")
    monitor_urls = [u.strip() for u in raw_urls.split(",") if u.strip()]
    if not monitor_urls:
        raise ConfigError("MONITOR_URLS must contain at least one URL")
    for url in monitor_urls:
        if not url.startswith("https://"):
            raise ConfigError(f"All URLs must use HTTPS. Got: {url}")

    bot_token = _require("TELEGRAM_BOT_TOKEN")
    chat_id = _require("TELEGRAM_CHAT_ID")

    return Settings(
        monitor_urls=monitor_urls,
        telegram_bot_token=bot_token,
        telegram_chat_id=chat_id,
        timeout_seconds=float(os.environ.get("TIMEOUT_SECONDS", "10")),
        latency_threshold_ms=float(os.environ.get("LATENCY_THRESHOLD_MS", "3000")),
        heartbeat_interval_minutes=float(os.environ.get("HEARTBEAT_INTERVAL_MINUTES", "120")),
        check_retries=int(os.environ.get("CHECK_RETRIES", "1")),
        check_retry_delay_seconds=float(os.environ.get("CHECK_RETRY_DELAY_SECONDS", "3")),
        dry_run=_bool_env("DRY_RUN", False),
  )
