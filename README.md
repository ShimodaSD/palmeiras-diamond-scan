# Palmeiras Diamond Ticket Monitor

Watches official Palmeiras and Avanti ticket sale announcements and sends a Telegram alert when **Avanti Diamante** pre-sale slots appear.

## Sources (official only)

- `palmeiras.com.br` — WordPress REST API (`/wp-json/wp/v2/posts`), searching `ingressos` and `Diamante`
- Ticket stores referenced in the announcements: `ingressospalmeiras.com.br`, `libertadores.eleventickets.com`

No CAPTCHA, Cloudflare, or access restrictions are bypassed; no tickets are purchased.

## What it alerts on

- **Diamond sale window found** — match, venue (Mandante / Visitante / Local neutro), sale start, status, ticket link and announcement link.
- **New ticket post the parser could not read** — fallback alert with the post title and link, so a new layout, table or image is never silent.
- **Source failure or empty feed** — if an official source raises an error or returns zero posts, the monitor alerts once per day per source, so a broken endpoint never turns into silent blindness.
- **First run after deploy** records existing posts without sending fallback alerts, to avoid spamming the history.

Duplicates are suppressed by a stable fixture key: match date + canonical teams + phase. Accent, case, punctuation and country suffixes (`Estudiantes-ARG` vs `Estudiantes`) do not create a new alert, and neither does a repost of the same fixture with a shifted sale window. The same opponent in another season or another phase alerts again; when the match date is still TBD, the sale day is used as the anchor.

## Setup

Python 3.15 via [uv](https://docs.astral.sh/uv/). Credentials come from the OpenBot vault at runtime (never written into the repo).

```bash
uv sync
./scripts/run_monitor.sh            # real notifications every 5 min
DRY_RUN=1 RUN_ONCE=1 ./scripts/run_monitor.sh   # one pass, print only
```

Production uses OpenBot routines with `RUN_ONCE=1` three times a day (09:00, 15:00 and 21:00, America/Sao_Paulo). `CHECK_INTERVAL_SECONDS` only applies to the continuous mode above.

## Configuration (environment)

| Variable | Default | Meaning |
|---|---|---|
| `TELEGRAM_BOT_TOKEN` | — | required, `@ShimodaNotificaBot` |
| `TELEGRAM_CHAT_ID` | — | required, your private chat ID |
| `CHECK_INTERVAL_SECONDS` | 300 | 5-minute polling |
| `TIMEZONE` | America/Sao_Paulo | IANA timezone used for timestamps, lookback and match-date year rollover |
| `DATABASE_PATH` | data/notifications.db | SQLite history |
| `DRY_RUN` | 0 | log instead of send |
| `RUN_ONCE` | 0 | single pass then exit |

## Architecture

- `sources/http_client.py` — httpx with retries/timeouts
- `sources/parsing.py` — Diamante pre-sale schedule, match/date, ticket link and venue (home/away/neutral) extraction
- `sources/palmeiras.py`, `sources/avanti.py` — official REST API collectors
- `collector.py` — stable dedupe per sale window, fallback alerts for unparsed posts, notification decisions
- `storage.py` — SQLite notification history and normalized seen-post tracking
- `notifier.py` — Telegram Bot API with retries
- `scheduler.py` — 5-minute polling loop (continuous mode only)

## Tests

```bash
uv run python -m unittest discover -s tests -v
```
