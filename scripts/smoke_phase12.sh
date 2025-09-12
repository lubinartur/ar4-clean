#!/usr/bin/env bash
set -euo pipefail

base="${1:-http://127.0.0.1:8000}"

curl_quiet(){ curl -sf "$@"; }

echo "[health]";        curl_quiet "$base/health" && echo
echo "[ui/ingest]";     curl_quiet "$base/ui/ingest" | head -n1

tmp="$(mktemp)"; echo "hello air4" > "$tmp"
trap 'rm -f "$tmp"' EXIT

echo "[ingest/file]";   curl_quiet -F "file=@$tmp" "$base/ingest/file" && echo
echo "[memory/search]"; curl_quiet "$base/memory/search?q=hello" && echo
