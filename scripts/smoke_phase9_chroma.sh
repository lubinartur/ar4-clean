#!/usr/bin/env bash
set -euo pipefail

BASE="${1:-http://127.0.0.1:8000}"
USER="${2:-dev}"
SID="smoke-$(date +%s)"

echo "== Health =="
curl -s "$BASE/health" | jq .

echo
echo "== Memory/Add (Chroma) =="
curl -s -X POST "$BASE/memory/add" \
  -H "Content-Type: application/json" -H "X-User: $USER" \
  -d "{\"text\":\"[SMOKE] Phase 9 uses ChromaDB + ST embeddings ($SID)\",\"session_id\":\"$SID\",\"source\":\"smoke\"}" \
  | jq .

echo
echo "== Memory/Search (k=4, q=Chroma) =="
curl -s --get "$BASE/memory/search" \
  -H "X-User: $USER" \
  --data-urlencode "q=Chroma" \
  --data-urlencode "k=4" | jq .

echo
echo "== UI Chat (non-stream) with RAG on =="
curl -s -X POST "$BASE/ui/chat/send" \
  -H "Content-Type: application/json" \
  -d "{\"message\":\"Кратко: что за Phase 9?\",\"session_id\":\"$SID\",\"use_rag\":true,\"k_memory\":4,\"stream\":false}" \
  | jq .
