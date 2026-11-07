# Palmeiras Diamond Ticket Monitor

Watches official Palmeiras and Avanti ticket sale announcements and sends a Telegram alert when **Avanti Diamante** pre-sale slots appear.

## Sources (official only)

- `palmeiras.com.br` — WordPress REST API (`/wp-json/wp/v2/posts`), searching `ingressos` and `Diamante`
- Ticket stores referenced in the announcements: `ingressospalmeiras.com.br`, `libertadores.eleventickets.com`

No CAPTCHA, Cloudflare, or access restrictions are bypassed; no tickets are purchased.

## Setup

Python 3.15 via [uv](https://docs.astral.sh/uv/). Credentials come from the OpenBot vault at runtime (never written into the repo).

```bash
uv sync
./scripts/run_monitor.sh            # real notifications every 5 min
DRY_RUN=1 RUN_ONCE=1 ./scripts/run_monitor.sh   # one pass, print only
```

## Configuration (environment)

| Variable | Default | Meaning |
|---|---|---|
| `TELEGRAM_BOT_TOKEN` | — | required, `@ShimodaNotificaBot` |
| `TELEGRAM_CHAT_ID` | — | required, 739017043 |
| `CHECK_INTERVAL_SECONDS` | 300 | 5-minute polling |
| `TIMEZONE` | America/Sao_Paulo | local time |
| `DATABASE_PATH` | data/notifications.db | SQLite history |
| `DRY_RUN` | 0 | log instead of send |
| `RUN_ONCE` | 0 | single pass then exit |

## Architecture

- `sources/http_client.py` — httpx with retries/timeouts
- `sources/parsing.py` — Diamante pre-sale schedule, match/date, ticket link extraction
- `sources/palmeiras.py`, `sources/avanti.py` — official REST API collectors
- `collector.py` — dedupe per (match, phase), notification decisions
- `storage.py` — SQLite notification history
- `notifier.py` — Telegram Bot API with retries
- `scheduler.py` — 5-minute polling loop

## Tests

```bash
uv run python -m unittest discover -s tests -v
```
