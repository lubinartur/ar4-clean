#!/usr/bin/env bash
set -euo pipefail

QUEUE="data/ingest/store/queue.json"
STORE="data/ingest/store"
API="http://127.0.0.1:8000"

echo "▶️ Обработка очереди..."

# 1) Прочитаем список файлов из очереди (формат: [ {"file":"name", "ts":...}, ... ])
mapfile -t FILES < <(jq -r '.[]? | .file // empty' "$QUEUE" 2>/dev/null || true)
COUNT=${#FILES[@]}
if (( COUNT == 0 )); then
  echo "ℹ️ Очередь пуста."
  exit 0
fi

for fname in "${FILES[@]}"; do
  echo "  → $fname"
  fpath="$STORE/$fname"
  if [[ ! -f "$fpath" ]]; then
    echo "    ⚠️  Файл не найден в $STORE — пропускаю"
    continue
  fi

  # 2) Извлечём текст (txt/md/log/csv → читать; pdf/docx по lib; остальное — best-effort)
  TEXT="$(
FPATH="$fpath" python - <<'PY'
import sys, json, os
from pathlib import Path

p = Path(os.environ["FPATH"])
name = p.name
ext = ''.join(p.suffixes).lower()

def out(text, note=""):
    obj = {"ok": True, "name": name, "ext": ext, "text": text, "note": note}
    print(json.dumps(obj, ensure_ascii=False))
    sys.exit(0)

try:
    if ext in ('.txt', '.md', '.log', '.csv', ''):
        try:
            t = p.read_text(encoding='utf-8', errors='ignore')
        except Exception:
            t = p.read_text(errors='ignore')
        out(t)
    elif ext == '.pdf':
        try:
            from PyPDF2 import PdfReader
            parts=[]
            with p.open('rb') as fh:
                r=PdfReader(fh)
                pages=list(getattr(r,'pages',[]) or [])
                for pg in pages[:5]:
                    try: parts.append(pg.extract_text() or '')
                    except Exception: parts.append('')
            out('\n'.join(parts).strip())
        except Exception as e:
            out(f"[pdf extract error: {e}]", "error")
    elif ext == '.docx':
        try:
            import docx
            d = docx.Document(str(p))
            t = '\n'.join(par.text for par in d.paragraphs)
            out(t.strip())
        except Exception as e:
            out(f"[docx extract error: {e}]", "error")
    else:
        # fallback: как текст
        try:
            t = p.read_text(encoding='utf-8', errors='ignore')
        except Exception:
            t = ""
        out(t)
except Exception as e:
    print(json.dumps({"ok": False, "err": str(e), "name": name}), ensure_ascii=False)
    sys.exit(0)
PY
  )"
  # извлечём поле text
  BODY_TEXT="$(printf '%s' "$TEXT" | jq -r '.text // ""')"

  if [[ -z "${BODY_TEXT// }" ]]; then
    echo "    ⚠️  Пустой текст — пропускаю"
    continue
  fi

  # 3) Отправим в память
  PAYLOAD="$(jq -cn --arg text "$BODY_TEXT" --arg src "$fname" '{text:$text, meta:{source:$src}}')"
  curl -s -X POST "$API/memory/memory/add" -H "Content-Type: application/json" -d "$PAYLOAD" >/dev/null || true
  echo "    ✅ В память добавлено"
done

# 4) Очистим очередь (успешно обработанные)
echo "[]" > "$QUEUE"
echo "✅ Очередь обработана."

# 5) Быстрая проверка поиска
curl -s "$API/memory/search?q=probe" | jq
