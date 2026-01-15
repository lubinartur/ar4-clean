#!/usr/bin/env bash
set -euo pipefail

BASE="${BASE:-http://localhost:8000}"
TODAY="${TODAY:-2026-01-14}"

echo "== QB smoke: create session"
SID=$(curl -s -X POST "$BASE/qb/sessions" | python -c "import sys,json; print(json.load(sys.stdin)['session_id'])")
echo "SID=$SID"

echo "== QB smoke: onboarding packs"
curl -s "$BASE/qb/onboarding" | python -m json.tool | head -n 120

echo "== QB smoke: onboarding/start OB-1-core_state"
curl -s -X POST "$BASE/qb/onboarding/start" \
  -H "Content-Type: application/json" \
  -d "{\"session_id\":\"$SID\",\"pack_id\":\"OB-1-core_state\"}" \
  | python -m json.tool | head -n 120

echo "== QB smoke: state (empty)"
curl -s "$BASE/qb/state?session_id=$SID" | python -m json.tool | head -n 80

echo "== QB smoke: checkin status (expect done=false)"
curl -s "$BASE/qb/checkin/status?session_id=$SID&today=$TODAY" | python -m json.tool

echo "== QB smoke: checkin set"
curl -s -X POST "$BASE/qb/checkin" -H "Content-Type: application/json" \
  -d "{\"session_id\":\"$SID\",\"date\":\"$TODAY\"}" | python -m json.tool

echo "== QB smoke: checkin status (expect done=true)"
curl -s "$BASE/qb/checkin/status?session_id=$SID&today=$TODAY" | python -m json.tool

echo "== QB smoke: answer overload_risk=yes (expect OVERLOADED)"
curl -s -X POST "$BASE/qb/answer" \
  -H "Content-Type: application/json" \
  -d "{\"session_id\":\"$SID\",\"signal\":\"overload_risk\",\"answer\":\"yes\"}" \
  | python -m json.tool | head -n 160

echo "== QB smoke: invalid answer (expect 400)"
set +e
HTTP_CODE=$(curl -s -o /tmp/qb_err.json -w "%{http_code}" -X POST "$BASE/qb/answer" \
  -H "Content-Type: application/json" \
  -d "{\"session_id\":\"$SID\",\"signal\":\"baseline_energy\",\"answer\":\"maybe\"}")
echo "HTTP_CODE=$HTTP_CODE"
cat /tmp/qb_err.json | python -m json.tool || true
set -e

echo "== QB smoke: reset"
curl -s -X POST "$BASE/qb/reset?session_id=$SID" | python -m json.tool | head -n 140

echo "== QB smoke: feed execution (expect mode=execution, questions=[])"
curl -s -X POST "$BASE/qb/answer" -H "Content-Type: application/json" \
  -d "{\"session_id\":\"$SID\",\"signal\":\"baseline_energy\",\"answer\":\"yes\"}" | python -m json.tool | head -n 60
curl -s -X POST "$BASE/qb/answer" -H "Content-Type: application/json" \
  -d "{\"session_id\":\"$SID\",\"signal\":\"attention_available\",\"answer\":\"yes\"}" | python -m json.tool | head -n 60
curl -s -X POST "$BASE/qb/answer" -H "Content-Type: application/json" \
  -d "{\"session_id\":\"$SID\",\"signal\":\"execution_ready\",\"answer\":\"yes\"}" | python -m json.tool | head -n 60
curl -s -X POST "$BASE/qb/answer" -H "Content-Type: application/json" \
  -d "{\"session_id\":\"$SID\",\"signal\":\"task_clarity\",\"answer\":\"yes\"}" | python -m json.tool | head -n 120

echo "== QB smoke: snapshot"
curl -s "$BASE/qb/snapshot?session_id=$SID" | python -m json.tool | head -n 120

echo "OK"
