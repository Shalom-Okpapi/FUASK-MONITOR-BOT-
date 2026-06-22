"""Entry point for one multi-page monitoring cycle."""
import sys
from datetime import datetime, timedelta, timezone
from typing import Dict

from src.checker import CheckResult, check_urls
from src.config import ConfigError, load_settings
from src.history import State, load_state, save_state
from src.telegram_notifier import send_message

WAT = timezone(timedelta(hours=1))


def _now_wat() -> str:
    return datetime.now(WAT).strftime("%a %d %b, %I:%M %p WAT")


def _page_label(url: str) -> str:
    path = url.rstrip("/").split("/")[-1]
    if not path or path.startswith("www."):
        return "Homepage"
    return path.replace("-", " ").replace("_", " ").title()


def _error_reason(result: CheckResult) -> str:
    if result.error == "timeout":
        return "took too long to respond (timeout)"
    if result.error:
        return f"connection failed ({result.error})"
    return f"server returned error {result.status_code}"


def evaluate(settings, results: Dict[str, CheckResult], state: State):
    alerts = []
    newly_down = []
    newly_recovered = []
    newly_slow = []

    new_pages_down = list(state.pages_down)
    new_pages_slow_alerted = list(state.pages_slow_alerted)

    for url, result in results.items():
        label = _page_label(url)
        was_down = url in state.pages_down
        was_slow_alerted = url in state.pages_slow_alerted

        if not result.ok:
            if not was_down:
                newly_down.append((label, url, result))
                new_pages_down.append(url)
            if url in new_pages_slow_alerted:
                new_pages_slow_alerted.remove(url)
        else:
            if was_down:
                newly_recovered.append((label, url, result))
                new_pages_down.remove(url)

            is_slow = (
                result.latency_ms is not None
                and result.latency_ms >= settings.latency_threshold_ms
            )
            if is_slow and not was_slow_alerted:
                newly_slow.append((label, url, result))
                new_pages_slow_alerted.append(url)
            elif not is_slow and was_slow_alerted:
                new_pages_slow_alerted.remove(url)

    if newly_down:
        total = len(results)
        down_count = len(new_pages_down)
        up_count = total - down_count

        if down_count == total:
            header = "🚨 *FUASK Website is FULLY DOWN!*\n\nNone of the pages are reachable right now."
        else:
            header = (
                f"🚨 *FUASK Website — {len(newly_down)} Page(s) Just Went Down!*\n\n"
                f"We detected a problem on {len(newly_down)} page(s). "
                f"{up_count} out of {total} pages are still working fine."
            )

        page_lines = "\n".join(
            f"❌ *{label}*\n"
            f"   └ {_error_reason(result)}\n"
            f"   └ {url}"
            for label, url, result in newly_down
        )

        alerts.append(
            f"{header}\n\n"
            f"{page_lines}\n\n"
            f"🕐 *Detected at:* {_now_wat()}\n\n"
            "👉 Please check the server and fix as soon as possible.\n"
            "The bot will notify you here once the affected pages are back online."
        )

    for label, url, result in newly_recovered:
        remaining_down = len(new_pages_down)
        footer = (
            f"\n⚠️ Note: {remaining_down} other page(s) are still down."
            if remaining_down > 0 else
            "\nAll pages are now back online. 🎉"
        )
        alerts.append(
            f"✅ *{label} Page is Back Online!*\n\n"
            f"Good news — this page is now accessible again.\n\n"
            f"🌐 *Page:* {url}\n"
            f"⚡ *Response time:* {result.latency_ms} ms\n"
            f"🕐 *Recovered at:* {_now_wat()}"
            f"{footer}"
        )

    for label, url, result in newly_slow:
        alerts.append(
            f"⚠️ *{label} Page is Running Slowly!*\n\n"
            f"This page is still online, but it is responding much slower than usual. "
            f"This could mean high traffic or a server issue.\n\n"
            f"🌐 *Page:* {url}\n"
            f"🐢 *Response time:* {result.latency_ms} ms "
            f"(normal is under {int(settings.latency_threshold_ms)} ms)\n"
            f"🕐 *Noticed at:* {_now_wat()}\n\n"
            "👉 No immediate action needed, but keep an eye on it."
        )

    new_state = State(
        pages_down=new_pages_down,
        pages_slow_alerted=new_pages_slow_alerted,
        last_heartbeat_at=state.last_heartbeat_at,
    )
    return alerts, new_state


def build_heartbeat(settings, results: Dict[str, CheckResult]) -> str:
    total = len(results)
    up_results = {u: r for u, r in results.items() if r.ok}
    down_results = {u: r for u, r in results.items() if not r.ok}
    up_count = len(up_results)

    latencies = [r.latency_ms for r in up_results.values() if r.latency_ms is not None]
    speed_line = ""
    if latencies:
        speed_line = (
            f"⚡ *Response times:* "
            f"fastest {min(latencies):.0f} ms · slowest {max(latencies):.0f} ms\n"
        )

    if not down_results:
        status_line = f"Great news! Checked {total} pages — all are online and running fine. ✅\n"
        page_summary = "\n".join(
            f"  ✅ {_page_label(url)}" for url in results
        )
    else:
        status_line = (
            f"⚠️ {up_count} out of {total} pages are working. "
            f"{len(down_results)} page(s) are currently down:\n"
        )
        page_summary = "\n".join(
            f"  ✅ {_page_label(url)}" if results[url].ok
            else f"  ❌ {_page_label(url)} — {_error_reason(results[url])}"
            for url in results
        )

    return (
        f"💚 *FUASK Website Health Check*\n\n"
        f"{status_line}\n"
        f"{page_summary}\n\n"
        f"{speed_line}"
        f"🕐 *Checked at:* {_now_wat()}\n\n"
        "No action needed. This is your routine 2-hour check-in from the monitoring bot. 🤖"
    )


def due_for_heartbeat(last_heartbeat_at, now: datetime, interval_minutes: float) -> bool:
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

    print(f"[check] Checking {len(settings.monitor_urls)} URLs...")
    results = check_urls(
        settings.monitor_urls,
        settings.timeout_seconds,
        retries=settings.check_retries,
        retry_delay_seconds=settings.check_retry_delay_seconds,
    )
    for url, r in results.items():
        print(f"  {'✓' if r.ok else '✗'} {url}  status={r.status_code}  latency={r.latency_ms}ms  err={r.error}")

    alerts, new_state = evaluate(settings, results, state)

    heartbeat_text = None
    now = datetime.now(timezone.utc)
    if due_for_heartbeat(state.last_heartbeat_at, now, settings.heartbeat_interval_minutes):
        heartbeat_text = build_heartbeat(settings, results)
        new_state.last_heartbeat_at = now.isoformat()
    else:
        new_state.last_heartbeat_at = state.last_heartbeat_at

    messages = [("alert", t) for t in alerts]
    if heartbeat_text:
        messages.append(("heartbeat", heartbeat_text))

    if not messages:
        print("[notify] Nothing to send this cycle — no state changes and heartbeat not due yet.")
    else:
        for label, text in messages:
            if settings.dry_run:
                print(f"\n[dry-run] Would send ({label}):\n{text}\n{'—'*50}")
            else:
                sent = send_message(settings.telegram_bot_token, settings.telegram_chat_id, text)
                print(f"[{label}] sent={sent}")

    save_state(new_state)
    return 0


if __name__ == "__main__":
    sys.exit(main())
