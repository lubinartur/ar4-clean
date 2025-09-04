#!/bin/bash
# Добавляет файл в очередь индексации (store/queue.json)
# Использование: ./scripts/add_to_queue.sh filename.ext

set -euo pipefail
NAME="${1:-}"
if [[ -z "$NAME" ]]; then
  echo "❌ Укажи имя файла: ./scripts/add_to_queue.sh filename.ext" >&2
  exit 1
fi

INBOX="data/ingest/inbox"
STORE="data/ingest/store"
QUEUE="$STORE/queue.json"

mkdir -p "$STORE"
[[ -f "$QUEUE" ]] || echo "[]" > "$QUEUE"

# Проверяем существование в inbox или store
if [[ -f "$INBOX/$NAME" ]]; then
  REAL="$NAME"
elif [[ -f "$STORE/$NAME" ]]; then
  REAL="$NAME"
else
  echo "❌ Файл не найден ни в $INBOX, ни в $STORE: $NAME" >&2
  exit 1
fi

TS=$(date +%s)
TMP=$(mktemp)
jq ". += [{\"file\":\"$REAL\",\"ts\":$TS}]" "$QUEUE" > "$TMP" && mv "$TMP" "$QUEUE"

echo "✅ В очередь добавлено: $REAL (ts=$TS)"
echo "→ Очередь: $QUEUE"
