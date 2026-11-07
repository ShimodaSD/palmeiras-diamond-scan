"""Poll Telegram getUpdates and print incoming chat IDs.

Usage:
    TELEGRAM_BOT_TOKEN=... uv run python scripts/get_chat_id.py

Listens until the first message arrives (or LISTEN_SECONDS elapses).
The bot token is read from the TELEGRAM_BOT_TOKEN environment variable.
"""

from __future__ import annotations

import os
import sys
import time

import httpx


def main() -> int:
    token = os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()
    if not token:
        print("TELEGRAM_BOT_TOKEN is not set", file=sys.stderr)
        return 1

    api = f"https://api.telegram.org/bot{token}"
    listen_seconds = int(os.environ.get("LISTEN_SECONDS", "300"))

    try:
        me = httpx.get(f"{api}/getMe", timeout=15)
        me.raise_for_status()
        username = me.json()["result"].get("username", "?")
        print(f"Bot: @{username}", flush=True)
    except Exception as exc:
        print(f"getMe failed: {exc}", file=sys.stderr)
        return 1

    print(f"Listening for {listen_seconds}s. Send a message to the bot now...", flush=True)

    deadline = time.time() + listen_seconds
    offset = 0

    while time.time() < deadline:
        try:
            response = httpx.get(
                f"{api}/getUpdates",
                params={"timeout": 30, "offset": offset},
                timeout=40,
            )
            if response.status_code == 409:
                print(
                    "Telegram error 409: a webhook or another getUpdates consumer "
                    "is active for this bot",
                    file=sys.stderr,
                )
                return 2
            response.raise_for_status()
            updates = response.json().get("result", [])
        except Exception as exc:
            print(f"getUpdates failed: {exc}", file=sys.stderr)
            time.sleep(2)
            continue

        for update in updates:
            offset = max(offset, update.get("update_id", 0) + 1)
            message = update.get("message") or update.get("channel_post") or {}
            chat = message.get("chat") or {}
            if not chat:
                continue
            name = (
                chat.get("title")
                or chat.get("first_name")
                or chat.get("username")
                or "?"
            )
            text = message.get("text", "")
            print(
                f"CHAT_ID={chat.get('id')} type={chat.get('type')} "
                f"name={name} text={text!r}",
                flush=True,
            )
            return 0

    print("No message received before the listen deadline.", file=sys.stderr)
    return 3


if __name__ == "__main__":
    raise SystemExit(main())
