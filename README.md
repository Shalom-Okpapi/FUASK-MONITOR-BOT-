# FUASK Website Monitor Bot

Checks https://www.fuask.edu.ng/ every 5 minutes and alerts the IT team's
Telegram group when it goes down, comes back up, or responds unusually slowly.

## How it decides to alert

- **Down**: fires on the very first confirmed failure. To avoid a single
  dropped packet looking like a real outage, each check internally retries
  once (`CHECK_RETRIES`, ~3 sec apart) before being counted as a failure —
  so this stays fast (worst case, the next 5-min cron cycle) without being
  trigger-happy on transient blips.
- **Recovered**: the first successful check after a confirmed outage.
- **Slow / possible high traffic**: response time crosses
  `LATENCY_THRESHOLD_MS` (default 3000ms) while the site is otherwise up.
  This is an **estimate based on response time**, not real concurrent-user
  data — without backend/analytics access there's no way to see actual
  traffic. Once IT grants access to hosting metrics, this check can be
  swapped for real numbers.
- **Heartbeat**: a routine "✅ still healthy" message every
  `HEARTBEAT_INTERVAL_MINUTES` (default 120, i.e. every 2 hours) while the
  site is up. This is separate from the alert logic above — its only job
  is to prove the bot itself is still alive and checking, so silence never
  gets confused with "everything's fine." No heartbeat is sent while the
  site is down (the down/recovery alerts already cover that).
- Down/recovered/slow alerts only fire on a **state change**, not on every
  single check — otherwise an ongoing outage would spam the group every 5
  minutes.

## Setup

### 1. Create the Telegram bot
1. Message **@BotFather** on Telegram → `/newbot` → follow the prompts.
2. Save the token it gives you.

### 2. Get the IT group's chat ID
1. Add the bot to the IT team's Telegram group as a normal member (no
   admin rights needed just to send messages).
2. Send any message in that group.
3. Visit `https://api.telegram.org/bot<YOUR_TOKEN>/getUpdates` in a
   browser and find `"chat":{"id": ...}` in the response — group IDs are
   negative numbers (e.g. `-1001234567890`).

   Note: unlike a private-chat bot, the group doesn't need anyone to press
   `/start` — the bot just needs to be a member.

### 3. Test locally
\`\`\`bash
cp .env.example .env
# fill in TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID
pip install -r requirements.txt
python run_monitor.py
\`\`\`
Once you see a sensible `[check]` log line, set `DRY_RUN=false` in `.env`
and run it once more to confirm a real Telegram message arrives.

### 4. Deploy
1. Push this repo to GitHub.
2. Repo **Settings → Secrets and variables → Actions → New repository
   secret**: add `TELEGRAM_BOT_TOKEN` and `TELEGRAM_CHAT_ID`.
3. Go to the **Actions** tab and manually run the workflow once
   (`workflow_dispatch`) to confirm it works in CI before trusting the
   schedule.

## Known limitations (v1)

- **Not true real-time.** GitHub Actions' cron scheduler is best-effort
  and can lag by several minutes, especially at busy times.
- **Traffic is inferred, not measured.** See the "high traffic" note above.
- **Single chat group.** No support yet for separate channels per alert
  type — straightforward to add later if useful.
