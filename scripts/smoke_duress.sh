#!/usr/bin/env bash
set -euo pipefail

BASE_URL="${BASE_URL:-http://localhost:8000}"
PIN="${DURESS_PIN:-0000}"
TXT="${1:-секрет под давлением}"

echo "[1/4] Duress login…"
TOKEN=$(curl -s -X POST "$BASE_URL/auth/login" \
  -H "Content-Type: application/json" \
  -d "{\"password\":\"$PIN\"}" | python3 -c 'import sys,json;print(json.load(sys.stdin)["token"])')
echo "TOKEN=${TOKEN:0:8}…"

echo "[2/4] Status…"
curl -s "$BASE_URL/secure/status" | jq .

echo "[3/4] Add memory (duress)…"
curl -s -X POST "$BASE_URL/memory/add" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d "{\"user_id\":\"default\",\"text\":\"$TXT\"}" | jq .

echo "[4/4] Search (duress)…"
curl -sG "$BASE_URL/memory/search" \
  -H "Authorization: Bearer $TOKEN" \
  --data-urlencode "q=$TXT" \
  --data-urlencode 'k=5' \
  --data-urlencode 'user_id=default' | jq .
