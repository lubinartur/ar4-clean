#!/usr/bin/env bash
set -e
HOST=${1:-http://127.0.0.1:8000}
F="ui_btn_test_$(date +%s).txt"
echo "UI BUTTON TEST $(date)" > "$F"
curl -s -F "file=@$F" "$HOST/ingest/file?tag=ui" | jq .
sleep 0.6
curl -s "$HOST/memory/search?q=UI%20BUTTON%20TEST&k=1" | jq .
rm -f "$F"
