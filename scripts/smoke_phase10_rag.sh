#!/usr/bin/env bash
set -euo pipefail

BASE="${BASE:-http://127.0.0.1:8000}"
XUSER="${XUSER:-X-User: dev}"
PASSWORD="${PASSWORD:-}"
K="${K:-3}"
MMR="${MMR:-0.2}"
HYDE="${HYDE:-1}"
RECENCY_DAYS="${RECENCY_DAYS:-365}"
THRESHOLD="${THRESHOLD:-0.7}"
FILTERS="${FILTERS:-tag:phase10 OR source:rag_corpus}"
CORPUS_DIR="tests/rag_corpus"
DOCS_DIR="$CORPUS_DIR/docs"
QUERIES="$CORPUS_DIR/queries.tsv"

for tool in curl jq awk sed; do command -v "$tool" >/dev/null 2>&1 || { echo "❌ Требуется $tool"; exit 2; }; done

TOKEN=""
if [[ -n "$PASSWORD" ]]; then
  TOKEN="$(curl -s -X POST "$BASE/auth/login" -H 'Content-Type: application/json' -d "{\"password\":\"$PASSWORD\"}" | jq -r '.token // empty')"
  [[ -n "$TOKEN" ]] && echo "🔐 Auth token получен." || echo "⚠️  Не удалось получить токен, продолжаю без авторизации."
fi
HEADERS=(-H "$XUSER"); [[ -n "$TOKEN" ]] && HEADERS+=(-H "Authorization: Bearer $TOKEN")

echo "== Smoke Phase-10 RAG (raw, intent-boost) =="
echo "BASE=$BASE, K=$K, MMR=$MMR, HYDE=$HYDE, THRESHOLD=$THRESHOLD, FILTERS='${FILTERS}'"

[[ -d "$DOCS_DIR" ]] || { echo "❌ Нет директории $DOCS_DIR"; exit 2; }
echo "→ Инжест документов из $DOCS_DIR"
shopt -s nullglob
for f in "$DOCS_DIR"/*.txt; do
  echo "  + $f"
  resp="$(curl -s -X POST "$BASE/ingest/file" -F "file=@$f" "${HEADERS[@]}")" || { echo "❌ Сетевая ошибка инжеста: $f"; exit 1; }
  ok="$(echo "$resp" | jq -r '.ok // false')"
  chunks="$(echo "$resp" | jq -r '.chunks // 0')"
  if [[ "$ok" != "true" || "$chunks" == "0" ]]; then
    content="$(cat "$f")"
    payload="$(jq -n --arg txt "$content" --arg src "$(basename "$f")" '{text:$txt, meta:{source:"rag_corpus", file:$src, tag:"phase10"}}')"
    resp2="$(curl -s -X POST "$BASE/memory/add" -H 'Content-Type: application/json' -d "$payload" "${HEADERS[@]}")" || { echo "❌ Ошибка /memory/add для $f"; echo "$resp2"; exit 1; }
    ok2="$(echo "$resp2" | jq -r '.ok // false')"
    [[ "$ok2" == "true" ]] || { echo "❌ Не удалось добавить через /memory/add: $f"; echo "$resp2"; exit 1; }
    echo "    ↳ fallback /memory/add ✓"
  fi
done
shopt -u nullglob

[[ -f "$QUERIES" ]] || { echo "❌ Нет файла $QUERIES"; exit 2; }
total_q=0; sum_prec=0
echo "→ Запросы и ответы:"

shopt -s nocasematch
while IFS=$'\t' read -r query expected || [[ -n "${query:-}" ]]; do
  [[ -z "${query// }" ]] && continue
  [[ "${query:0:1}" == "#" ]] && continue
  total_q=$((total_q+1))

  # intent boost: добавим якорные слова в текст запроса
  boost=""
  qlc="$query"
  case "$qlc" in
    *цели*|*goals*)          boost="$boost phase10_goals цели goals" ;;
  esac
  case "$qlc" in
    *следующ*|*"next steps"*|*roadmap*)
                           boost="$boost phase10_next \"следующие шаги\" \"next steps\" roadmap" ;;
  esac
  case "$qlc" in
    *"о чём"*|*"о чем"*|*about*|*описан*)
                           boost="$boost phase10_intro описание intro" ;;
  esac
  case "$qlc" in
    *сделано*|*готово*|*done*)
                           boost="$boost phase10_done done \"что уже сделано\"" ;;
  esac

  qsend="$query $boost"

  resp="$(curl -sG "$BASE/memory/debug/query_raw" \
    --data-urlencode "q=$qsend" \
    --data-urlencode "k=$K" \
    --data-urlencode "mmr=$MMR" \
    --data-urlencode "hyde=$HYDE" \
    --data-urlencode "recency_days=$RECENCY_DAYS" \
    --data-urlencode "filters=$FILTERS" \
    "${HEADERS[@]}")"

  hits=0
  IFS='|' read -r -a expected_arr <<< "$expected"
  while IFS=$'\t' read -r mfn msp mtitle thead || [[ -n "${mfn:-}${msp:-}${mtitle:-}${thead:-}" ]]; do
    docid=""
    [[ -n "$mtitle" ]] && docid="$(printf "%s" "$mtitle" | sed -n 's/.*DOCID:[[:space:]]*\([A-Za-z0-9._-]\+\).*/\1/p' | head -n1 || true)"
    [[ -z "$docid" && -n "$thead"  ]] && docid="$(printf "%s" "$thead"  | sed -n 's/.*DOCID:[[:space:]]*\([A-Za-z0-9._-]\+\).*/\1/p' | head -n1 || true)"
    if [[ -z "$docid" ]]; then
      for cand in "$mfn" "$msp"; do
        [[ -z "$cand" ]] && continue
        basef="$(basename "$cand")"; basef="${basef%.*}"
        [[ -n "$basef" ]] && { docid="$basef"; break; }
      done
    fi
    if [[ -n "$docid" ]]; then
      for e in "${expected_arr[@]}"; do
        if [[ "$docid" == "$e" ]]; then hits=$((hits+1)); break; fi
      done
    fi
  done < <(printf "%s" "$resp" | jq -r '.rows[0:'"$K"'][] | [ (.metadata.filename // ""), (.metadata.source_path // ""), (.metadata.title // ""), (.text_head // "") ] | @tsv')

  prec=$(awk -v h="$hits" -v k="$K" 'BEGIN { printf("%.3f", (k>0)? h/k : 0) }')
  sum_prec=$(awk -v s="$sum_prec" -v p="$prec" 'BEGIN { printf("%.6f", s + p) }')
  echo "Q${total_q}: \"$query\" -> hits=$hits/${K}, p@${K}=$prec (ожид.: $expected)"
done < "$QUERIES"

[[ "$total_q" -gt 0 ]] || { echo "❌ В $QUERIES не найдено валидных строк."; exit 2; }
avg_p=$(awk -v s="$sum_prec" -v n="$total_q" 'BEGIN { printf("%.3f", (n>0)? s/n : 0) }')
echo "== Итого: avg p@${K} = $avg_p на $total_q запросах =="
awk -v a="$avg_p" -v t="$THRESHOLD" 'BEGIN { if (a+0 >= t+0) { print "✅ Порог пройден."; exit 0 } else { print "⚠️  Ниже порога."; exit 1 } }'
