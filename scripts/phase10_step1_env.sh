#!/opt/homebrew/bin/bash
set -euo pipefail

HOST="${HOST:-127.0.0.1}"
PORT="${PORT:-8000}"

echo "==[1/4] venv + deps =="
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip wheel
pip install -r requirements.txt

echo "==[2/4] uvicorn start =="
# убьём старый, если есть
if [[ -f .uvicorn.pid ]]; then
  pkill -P "$(cat .uvicorn.pid)" || true
  kill "$(cat .uvicorn.pid)" || true
  rm -f .uvicorn.pid
fi
uvicorn backend.app.main:app --host "$HOST" --port "$PORT" --reload > .uvicorn.out 2>&1 & echo $! > .uvicorn.pid
sleep 0.5

echo "==[3/4] wait /health =="
for i in {1..60}; do
  code=$(curl -s -o /dev/null -w "%{http_code}" "http://$HOST:$PORT/health" || true)
  if [[ "$code" == "200" ]]; then
    echo "health: $code"
    break
  fi
  sleep 0.5
done
if [[ "${code:-}" != "200" ]]; then
  echo "FAIL: /health != 200 (got ${code:-nil})"
  exit 1
fi

echo "==[4/4] sanity: __routes must be 404 =="
routes_code=$(curl -s -o /dev/null -w "%{http_code}" "http://$HOST:$PORT/__routes" || true)
echo "__routes: $routes_code"
if [[ "$routes_code" != "404" ]]; then
  echo "FAIL: /__routes expected 404"
  exit 1
fi

echo "OK: server up at http://$HOST:$PORT (health=200, __routes=404)"
