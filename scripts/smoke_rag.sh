#!/usr/bin/env bash
set -euo pipefail

BASE_URL="${1:-http://127.0.0.1:8000}"

MSG="RAG_SMOKE_TEST_$(date +%s)"
FILE="/tmp/rag_smoke_test_$$.txt"

echo ">>> AIR4 RAG smoke test"
echo "Message: $MSG"
echo "$MSG" > "$FILE"

echo ">>> Uploading file via /ingest/file"
curl -s -F "file=@${FILE}" "${BASE_URL}/ingest/file?tag=rag-smoke" | sed 's/^/UPLOAD: /'

echo
echo ">>> Querying /memory/search"
RES="$(
  curl -s "${BASE_URL}/memory/search?q=${MSG}&k=3"
)"

echo "$RES" | sed 's/^/SEARCH: /'

if echo "$RES" | grep -q "$MSG"; then
  echo "OK: RAG smoke passed (phrase found in memory.search)"
  exit 0
else
  echo "FAIL: phrase not found in memory.search response"
  exit 1
fi
