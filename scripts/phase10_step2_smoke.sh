#!/opt/homebrew/bin/bash
set -euo pipefail

LOG=".smoke_phase10_step2.log"
THRESH=0.7

echo "==[1/5] Проверка корпуса и queries =="
test -d tests/rag_corpus/docs || { echo "ERR: нет папки tests/rag_corpus/docs"; exit 1; }
test -f tests/rag_corpus/queries.tsv || { echo "ERR: нет tests/rag_corpus/queries.tsv"; exit 1; }

echo "==[2/5] Добавление шумовых документов (идемпотентно) =="
mkdir -p tests/rag_corpus/docs/noise

add_if_missing () {
  local path="$1"
  local content="$2"
  if [[ ! -f "$path" ]]; then
    printf "%s\n" "$content" > "$path"
    echo "created: $path"
  else
    echo "exists:  $path"
  fi
}

add_if_missing tests/rag_corpus/docs/noise/noise_marketing.txt \
"This is a noise document unrelated to the AIr4 project. It discusses generic marketing strategies, SEO buzzwords, and random KPIs. The intent is to distract RAG retrieval and reduce precision if the retriever is weak."

add_if_missing tests/rag_corpus/docs/noise/noise_lorem.txt \
"Lorem ipsum dolor sit amet, consectetur adipiscing elit. Nulla vitae elit libero, a pharetra augue. Vestibulum id ligula porta felis euismod semper. Aenean lacinia bibendum nulla sed consectetur."

add_if_missing tests/rag_corpus/docs/noise/noise_random_tech.txt \
"Changelog: migrated from MySQL to SQLite then to PostgreSQL. Added websockets, replaced cron with systemd timers. Unrelated tech noise to confuse retrieval."

echo "==[3/5] Uvicorn должен уже работать (/health=200). Проверка =="
code=$(curl -s -o /dev/null -w "%{http_code}" "http://127.0.0.1:8000/health" || true)
if [[ "$code" != "200" ]]; then
  echo "ERR: API не поднят (health=$code). Запусти шаг 1."; exit 1
fi

echo "==[4/5] Запуск smoke (scripts/smoke_phase10_rag.sh) =="
/opt/homebrew/bin/bash scripts/smoke_phase10_rag.sh | tee "$LOG"

echo "==[5/5] Парсинг avg p@3 и проверка порога =="
AVG=$(grep -Eo 'avg p@3[[:space:]]*=[[:space:]]*[0-9.]+' "$LOG" | tail -1 | sed -E 's/.*=[[:space:]]*([0-9.]+)/\1/')
if [[ -z "${AVG:-}" ]]; then
  echo "FAIL: не удалось извлечь avg p@3 из лога $LOG"; exit 1
fi
echo "avg p@3 = ${AVG}"
awk -v a="$AVG" -v t="$THRESH" 'BEGIN{exit (a>=t)?0:1}' \
  && echo "OK: avg p@3 >= ${THRESH} (${AVG})" \
  || { echo "FAIL: avg p@3 < ${THRESH} (${AVG})"; exit 1; }
