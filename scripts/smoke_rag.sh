#!/usr/bin/env bash
set -euo pipefail
BASE="http://127.0.0.1:8000"

echo "1) Health"; curl -s "$BASE/health" | jq -r '.ok,.model' | xargs echo

echo "2) Create RAG sample"
echo 'AIR4 RAG test: Project codename is AIRCH. The secret color is burnt orange.' > rag_check.md

echo "3) Upload -> commit"
curl -s -F "file=@rag_check.md" "$BASE/ingest/file?tag=smoke" >/dev/null || true
cp rag_check.md data/ingest/inbox/ 2>/dev/null || true
curl -s -X POST "$BASE/ingest/commit?name=rag_check.md" >/dev/null || true

echo "4) Enqueue (force) & process"
DIGEST=$(sha256sum rag_check.md 2>/dev/null | awk '{print $1}')
[ -z "${DIGEST:-}" ] && DIGEST=$(shasum -a 256 rag_check.md | awk '{print $1}')
echo "[{\"file\":\"${DIGEST}.md\"}]" > data/ingest/store/queue.json
curl -s -X POST "$BASE/ingest/process" | jq -r '.processed[]?' | xargs echo "Processed:"

echo "5) Memory search"
curl -s "$BASE/memory/search?q=burnt%20orange&k=1" | jq -r '.results[0].text' | sed -e 's/\n/ /g'

echo "6) chat/rag"
curl -s -X POST "$BASE/chat/rag" -H "Content-Type: application/json" \
  -d '{"q":"What is the secret color and codename?","session_id":"smoke"}' \
  | jq -r '.reply'
