"""Entry point for one monitoring cycle.

Run on a schedule (see .github/workflows/monitor.yml, every 5 minutes).
Each run:
  1. Checks the monitored URL once (with an in-check retry — see
     src/checker.py — to filter out single transient blips).
  2. Compares the result against the last known state and sends an alert
     on a state TRANSITION — newly down, newly recovered, or a fresh
     latency spike — never on every single check. With FAILURE_THRESHOLD=1,
     a confirmed outage is reported on the very next scheduled check
     (within ~5 minutes), not after multiple cycles.
  3. Independently, sends a routine "✅ still healthy" heartbeat roughly
     every HEARTBEAT_INTERVAL_MINUTES (default 120, i.e. every 2 hours)
     while the site is up, so the team knows the bot itself is alive even
     when there's nothing wrong to report.
  4. Persists the new state atomically.

Exit code is 0 on a completed run (even if the site is down — "down" is a
successful detection, not a script failure) and 1 only on a configuration
error.
"""
import sys
from datetime import datetime, timedelta, timezone

from src.checker import check_url
from src.config import ConfigError, Settings, load_settings
from src.history import State, load_state, save_state
from src.telegram_notifier import send_message


def evaluate(settings: Settings, result, state: State):
    """Decide whether to alert and compute the new state.

    Returns (alert_text_or_None, new_state).
    """
    if not result.ok:
        consecutive = state.consecutive_failures + 1
        crossed_threshold = consecutive >= settings.failure_threshold
        new_status = "down" if crossed_threshold else state.last_status

        alert_text = None
        if crossed_threshold and state.last_status != "down":
            alert_text = (
                "🔴 *FUASK site DOWN*\n"
                f"URL: {settings.monitor_url}\n"
                f"Error: {result.error or result.status_code}\n"
                f"Time: {result.timestamp}\n"
                f"Failed {consecutive} checks in a row."
            )
        return alert_text, State(new_status, consecutive, False)

    # Successful check
    if state.last_status == "down":
        alert_text = (
            "✅ *FUASK site RECOVERED*\n"
            f"URL: {settings.monitor_url}\n"
            f"Latency: {result.latency_ms} ms\n"
            f"Time: {result.timestamp}"
        )
        return alert_text, State("up", 0, False)

    is_slow = (
        result.latency_ms is not None
        and result.latency_ms >= settings.latency_threshold_ms
    )
    alert_text = None
    if is_slow and not state.last_latency_alert_sent:
        alert_text = (
            "🟡 *FUASK site slow (possible high traffic)*\n"
            f"URL: {settings.monitor_url}\n"
            f"Latency: {result.latency_ms} ms (threshold {settings.latency_threshold_ms} ms)\n"
            f"Time: {result.timestamp}\n"
            "Note: this is a response-time estimate, not real traffic data."
        )
    return alert_text, State("up", 0, is_slow)


def due_for_heartbeat(last_heartbeat_at, now: datetime, interval_minutes: float) -> bool:
    """True if it's been at least `interval_minutes` since the last heartbeat
    (or none has ever been sent)."""
    if last_heartbeat_at is None:
        return True
    last = datetime.fromisoformat(last_heartbeat_at)
    return (now - last) >= timedelta(minutes=interval_minutes)


def main() -> int:
    try:
        settings = load_settings()
    except ConfigError as exc:
        print(f"[config] {exc}")
        return 1

    state = load_state()
    result = check_url(
        settings.monitor_url,
        settings.timeout_seconds,
        retries=settings.check_retries,
        retry_delay_seconds=settings.check_retry_delay_seconds,
    )
    print(
        f"[check] ok={result.ok} status={result.status_code} "
        f"latency_ms={result.latency_ms} error={result.error}"
    )

    alert_text, new_state = evaluate(settings, result, state)
    # evaluate() builds a fresh State focused on alert logic — carry the
    # heartbeat timestamp forward separately so it isn't reset every run.
    new_state.last_heartbeat_at = state.last_heartbeat_at

    heartbeat_text = None
    now = datetime.now(timezone.utc)
    if result.ok and due_for_heartbeat(
        state.last_heartbeat_at, now, settings.heartbeat_interval_minutes
    ):
        heartbeat_text = (
            "✅ *FUASK site healthy*\n"
            f"URL: {settings.monitor_url}\n"
            f"Latency: {result.latency_ms} ms\n"
            f"Time: {result.timestamp}\n"
            f"(Routine {int(settings.heartbeat_interval_minutes)}-min check-in)"
        )
        new_state.last_heartbeat_at = now.isoformat()

    for label, text in (("alert", alert_text), ("heartbeat", heartbeat_text)):
        if text is None:
            continue
        if settings.dry_run:
            print(f"[dry-run] would send ({label}):\n{text}")
        else:
            sent = send_message(settings.telegram_bot_token, settings.telegram_chat_id, text)
            print(f"[{label}] sent={sent}")

    if alert_text is None and heartbeat_text is None:
        print("[notify] nothing to send this cycle")

    save_state(new_state)
    return 0


if __name__ == "__main__":
    sys.exit(main())
