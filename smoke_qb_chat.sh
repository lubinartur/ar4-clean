#!/usr/bin/env bash
set -euo pipefail

BASE="${BASE:-http://localhost:8000}"

echo "== create qb session"
SID=$(curl -s -X POST "$BASE/qb/sessions" | python -c "import sys,json; print(json.load(sys.stdin)['session_id'])")
echo "SID=$SID"

echo "== answer overload_risk=yes (force stabilize)"
curl -s -X POST "$BASE/qb/answer" \
  -H "Content-Type: application/json" \
  -d "{\"session_id\":\"$SID\",\"signal\":\"overload_risk\",\"answer\":\"yes\"}" \
  | python -m json.tool | head -n 80

echo "== call /chat with qb_session_id (should inject QB preamble)"
echo "NOTE: adjust payload fields if your /chat request schema differs."
curl -s -X POST "$BASE/chat" \
  -H "Content-Type: application/json" \
  -d "{\"message\":\"дай следующий шаг\",\"qb_session_id\":\"$SID\",\"qb_enabled\":true}" \
  | python -m json.tool | head -n 120

echo "OK"
