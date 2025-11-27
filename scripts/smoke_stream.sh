#!/usr/bin/env bash
set -e
HOST=${1:-http://127.0.0.1:8000}
TXT='Скажи «готово», затем пять точек по одной.'
OUT=$(curl -N -s -X POST "$HOST/chat/stream" \
  -H 'Content-Type: application/json' \
  -d "{\"text\":\"$TXT\"}" | tr -d '\r')
echo "$OUT"
DOTS=$(printf "%s" "$OUT" | tr -cd '.' | wc -c | tr -d ' ')
[[ "$DOTS" == "5" ]] && echo "OK: 5 dots" || { echo "FAIL: $DOTS dots"; exit 1; }
