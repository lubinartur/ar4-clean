#!/usr/bin/env bash
set -euo pipefail

BASE="${BASE:-http://127.0.0.1:8000}"
WHERE='{"tag":"phase10"}'
K="${K:-3}"
MMR="${MMR:-0.3}"
HYDE="${HYDE:-1}"
RECENCY="${RECENCY:-365}"
CAND_MULT="${CAND_MULT:-10}"

echo "== Air4 Phase-10 RAG smoke =="
echo "BASE=$BASE  K=$K  MMR=$MMR  HYDE=$HYDE  RECENCY=$RECENCY  CAND_MULT=$CAND_MULT  WHERE=$WHERE"
python3 tests/rag_corpus/evaluate_rag.py \
  --base "$BASE" \
  --where_json "$WHERE" \
  --k "$K" \
  --mmr "$MMR" \
  --hyde "$HYDE" \
  --recency_days "$RECENCY" \
  --candidate_multiplier "$CAND_MULT"
