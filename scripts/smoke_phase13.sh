#!/usr/bin/env bash
set -euo pipefail

base="${1:-http://127.0.0.1:8000}"
echo "🧪 smoke_phase13 — URL: $base"

curl_quiet(){ curl -sf "$@"; }

# 1. Проверка /health
echo "[✓] GET /health"
curl_quiet "$base/health" && echo

# 2. Проверка POST /chat
echo "[✓] POST /chat"
curl_quiet -X POST "$base/chat" \
  -H "Content-Type: application/json" \
  -d '{"q":"ping"}' && echo

# 3. Проверка UI /ui/ingest
echo "[✓] GET /ui/ingest"
curl_quiet "$base/ui/ingest" | head -n 1

# 4. Ингест файла .txt
tmp_txt="$(mktemp)"
echo "AIr4 is my external brain for everything." > "$tmp_txt"
trap 'rm -f "$tmp_txt"' EXIT

echo "[✓] POST /ingest/file"
curl_quiet -F "file=@$tmp_txt" "$base/ingest/file" && echo

# 5. Поиск по памяти
echo "[✓] GET /memory/search?q=external"
curl_quiet "$base/memory/search?q=external" && echo

echo "✅ smoke_phase13 OK"
