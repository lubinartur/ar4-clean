#!/usr/bin/env bash
set -e

BASE="http://localhost:8001"

echo "=== /health ==="
curl -s "$BASE/health" | jq

echo
echo "=== /tools:docs_search ==="
curl -s -X POST "$BASE/tools" -H 'Content-Type: application/json' \
  -d '{"name":"docs_search","params":{"query":"asyncio run","max_results":3}}' | jq

echo
echo "=== /tools:web_search (site:docs.python.org) ==="
curl -s -X POST "$BASE/tools" -H 'Content-Type: application/json' \
  -d '{"name":"web_search","params":{"query":"site:docs.python.org asyncio run","max_results":3}}' | jq

echo
echo "=== /tools:web_fetch (title + 300 символов) ==="
curl -s -X POST "$BASE/tools" -H 'Content-Type: application/json' \
  -d '{"name":"web_fetch","params":{"url":"https://docs.python.org/3.13/library/asyncio-runner.html"}}' \
  | jq -r '.result.title, (.result.text[:300])'

echo
echo "=== /chat с web_query ==="
curl -s -X POST "$BASE/chat" -H 'Content-Type: application/json' \
  -d '{"message":"Кратко объясни asyncio.run с примером.","session_id":"smoke-001","user_id":"ar4","web_query":"site:docs.python.org asyncio run","end_session":false}' \
  | jq '.reply'
