#!/usr/bin/env bash
set -euo pipefail

URL="${1:-http://127.0.0.1:8000/chat/stream-test}"

echo ">>> AIR4 stream smoke test: $URL"

OUT="$(
  curl -s -N -X POST "$URL" \
    -H 'Content-Type: application/json' \
    -d '{"text":"STREAM_SMOKE_TEST"}' \
  | grep '^data:' \
  | sed 's/^data: //g' \
  | tr -d '\r'
)"

echo "$OUT"

DOTS="$(printf "%s" "$OUT" | tr -cd '.' | wc -c | tr -d ' ')"

if [ "$DOTS" -ne 3 ]; then
  echo "FAIL: expected 3 dots, got $DOTS"
  exit 1
fi

if ! printf "%s" "$OUT" | grep -q "готово"; then
  echo "FAIL: no 'готово' in stream"
  exit 1
fi

echo "OK: stream smoke passed"
