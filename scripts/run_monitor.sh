#!/usr/bin/env bash
# Launch the ticket monitor using credentials from the OpenBot vault,
# so no secret is written into this repository.
set -euo pipefail

KEYDIR="${OPENBOT_KEYDIR:-$HOME/Library/Application Support/OpenBot/agent-api-keys/.vault}"

export TELEGRAM_BOT_TOKEN="$(cat "$KEYDIR/TELEGRAM_PALMEIRAS_BOT")"
export TELEGRAM_CHAT_ID="${TELEGRAM_CHAT_ID:-$(cat "$KEYDIR/TELEGRAM_CHAT_ID")}"

cd "$(dirname "$0")/.."
exec uv run palmeiras-monitor "$@"
