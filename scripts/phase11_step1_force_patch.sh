#!/opt/homebrew/bin/bash
set -euo pipefail

MAIN="backend/app/main.py"
ROUTER_IMPORT="from backend.app.routes_profile import router as profile_router"
ROUTER_INCLUDE="app.include_router(profile_router)"

echo "==[A] Снимок include_router до патча =="
grep -n "include_router" "$MAIN" || echo "(нет include_router)"

echo "==[B] Патч main.py (детерминированный) =="
/usr/bin/python3 - "$MAIN" <<'PY'
import sys, re, io
from pathlib import Path
path = Path(sys.argv[1])
t = path.read_text(encoding="utf-8")

imp = "from backend.app.routes_profile import router as profile_router"
inc = "app.include_router(profile_router)"

changed = False

if imp not in t:
    # Вставляем импорт после последнего import/from в верхней части файла
    lines = t.splitlines(True)
    last_import_idx = -1
    for i, L in enumerate(lines[:300]):
        if L.lstrip().startswith(("import ", "from ")):
            last_import_idx = i
    insert_at = last_import_idx + 1 if last_import_idx >= 0 else 0
    lines.insert(insert_at, imp + "\n")
    t = "".join(lines)
    changed = True

if inc not in t:
    # Вставляем include сразу после последнего app.include_router(...) если есть,
    # иначе сразу после объявления app = FastAPI(...)
    m_last_inc = None
    for m in re.finditer(r"app\.include_router\([^)]*\)\s*\n", t):
        m_last_inc = m
    if m_last_inc:
        pos = m_last_inc.end()
        t = t[:pos] + inc + "\n" + t[pos:]
    else:
        m_app = re.search(r"\n\s*app\s*=\s*FastAPI\([^)]*\)\s*\n", t)
        if m_app:
            pos = m_app.end()
            t = t[:pos] + inc + "\n" + t[pos:]
        else:
            # если по какой-то причине не нашли app, просто добавим в конец
            t = t.rstrip() + "\n" + inc + "\n"
    changed = True

path.write_text(t, encoding="utf-8")
print("patched" if changed else "no-change")
PY

echo "==[C] Перезапуск uvicorn =="
if [[ -f .uvicorn.pid ]]; then pkill -P "$(cat .uvicorn.pid)" 2>/dev/null || true; kill "$(cat .uvicorn.pid)" 2>/dev/null || true; rm -f .uvicorn.pid; fi
uvicorn backend.app.main:app --host 127.0.0.1 --port 8000 --reload > .uvicorn.out 2>&1 & echo $! > .uvicorn.pid

echo "==[D] Ожидание /health =="
for i in {1..60}; do
  code=$(curl -s -o /dev/null -w "%{http_code}" http://127.0.0.1:8000/health || true)
  [[ "$code" == "200" ]] && { echo "health: $code"; break; }
  sleep 0.3
done
[[ "${code:-}" == "200" ]]

echo "==[E] Проверка OpenAPI на /memory/profile =="
if curl -s http://127.0.0.1:8000/openapi.json | jq -r '.paths | keys[]' | grep -q '^/memory/profile$'; then
  echo "OK: /memory/profile есть в OpenAPI"
else
  echo "FAIL: /memory/profile нет в OpenAPI — хвост лога:"
  tail -n 80 .uvicorn.out || true
  exit 1
fi

echo "==[F] Быстрый GET/PATCH/GET =="
echo "GET #1"
curl -s http://127.0.0.1:8000/memory/profile | jq '.user_id,.schema_version,.updated_at' || true

echo "PATCH"
curl -s -X PATCH http://127.0.0.1:8000/memory/profile \
  -H 'Content-Type: application/json' \
  -d '{"name":"AR4","preferences":{"tone":"bro","lang":"ru"},"facts":{"country":"EE","bike":"Ducati"},"goals":[{"id":"g1","title":"Moonlight Sonata 1:30","progress":0.3}]}' \
  | jq '.name,.preferences,.facts,.goals[0]' || true

echo "GET #2"
curl -s http://127.0.0.1:8000/memory/profile | jq '.name,.preferences,.facts,.goals[0],.updated_at' || true

echo "DONE"
