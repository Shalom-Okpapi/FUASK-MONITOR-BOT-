"""Sends alerts to the IT team's Telegram chat.

The bot token is never printed or logged. A Telegram-side failure is caught
and reported to stdout but does not crash the run — losing one alert
shouldn't also break state persistence for the next check.
"""
import requests

TELEGRAM_API_BASE = "https://api.telegram.org"


def send_message(bot_token: str, chat_id: str, text: str, timeout_seconds: float = 10) -> bool:
    url = f"{TELEGRAM_API_BASE}/bot{bot_token}/sendMessage"
    try:
        response = requests.post(
            url,
            json={"chat_id": chat_id, "text": text, "parse_mode": "Markdown"},
            timeout=timeout_seconds,
        )
        if response.status_code != 200:
            print(f"[telegram] send failed, status={response.status_code}")
            return False
        return True
    except requests.exceptions.RequestException as exc:
        print(f"[telegram] send failed: {type(exc).__name__}")
        return False
