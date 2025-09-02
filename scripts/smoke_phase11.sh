#!/bin/bash
set -e
BASE_URL="http://127.0.0.1:8000"
TMP_FILE=$(mktemp /tmp/air4_test_ingest.XXXX.txt)
TARGET_P3=0.7
PASS=0
FAIL=0
function check_endpoint() { local URL=$1; local NAME=$2; if curl -s $URL | jq -e '.ok == true' >/dev/null; then echo "✅ $NAME OK"; PASS=$((PASS+1)); else echo "❌ $NAME FAILED"; FAIL=$((FAIL+1)); fi }
echo -e "\n1️⃣ /health"; check_endpoint "$BASE_URL/health" "/health"
echo -e "\n2️⃣ /chat"; CHAT_RESP=$(curl -s -X POST $BASE_URL/chat -H "Content-Type: application/json" -d '{"message":"Тест Phase-11 RAG + chat","stream":false}'); if echo "$CHAT_RESP" | jq -e '.ok == true' >/dev/null; then echo "✅ /chat OK"; PASS=$((PASS+1)); else echo "❌ /chat FAILED"; FAIL=$((FAIL+1)); fi
echo -e "\n3️⃣ /ingest/file"; echo "Тестовый контент для проверки ingest Phase-11" > $TMP_FILE; INGEST_RESP=$(curl -s -X POST $BASE_URL/ingest/file -H "X-User: dev" -F "file=@$TMP_FILE"); rm $TMP_FILE; if echo "$INGEST_RESP" | jq -e '.ok == true' >/dev/null; then echo "✅ /ingest/file OK"; PASS=$((PASS+1)); else echo "❌ /ingest/file FAILED"; FAIL=$((FAIL+1)); fi
echo -e "\n4️⃣ /memory/search"; check_endpoint "$BASE_URL/memory/search?q=Тестовый&k=3" "/memory/search"
echo -e "\n5️⃣ /profile/memory/profile"; check_endpoint "$BASE_URL/profile/memory/profile" "/profile/memory/profile"
echo -e "\n6️⃣ RAG P@3 Check"; if [[ -f scripts/smoke_phase10_rag.sh ]]; then RAG_SCORE=$(bash scripts/smoke_phase10_rag.sh | grep -Eo 'P@3=[0-9.]+'); P3_VALUE=$(echo "$RAG_SCORE" | grep -Eo '[0-9.]+'); if (( $(echo "$P3_VALUE >= $TARGET_P3" | bc -l) )); then echo "✅ RAG smoke OK, P@3=$P3_VALUE >= $TARGET_P3"; PASS=$((PASS+1)); else echo "❌ RAG smoke FAILED, P@3=$P3_VALUE < $TARGET_P3"; FAIL=$((FAIL+1)); fi; else echo "⚠️ scripts/smoke_phase10_rag.sh не найден, пропуск RAG"; fi
echo -e "\n=============================="; echo "Phase-11 Smoke Test Result"; echo "✅ Passed: $PASS"; echo "❌ Failed: $FAIL"; echo "=============================="; if [ $FAIL -eq 0 ]; then echo "🎉 All checks passed!"; exit 0; else echo "⚠️ Some checks failed."; exit 1; fi
