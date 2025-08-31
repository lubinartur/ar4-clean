#!/bin/zsh
# phase12_test.sh — авто-тест Phase-12 RAG memory

echo "Создаём тестовые файлы Phase-12 с длинными текстами..."
mkdir -p ./storage/chroma_phase12

# Тестовые заметки
for i in {1..3}; do
  echo "Phase-12 авто-тест: доп. заметка $i — проверяем как RAG работает и объединяет текстовые блоки для поиска" > ./storage/chroma_phase12/note_$i.txt
done

echo "Phase-12 авто-тест: память и RAG проверка — полная проверка Phase-12" > ./storage/chroma_phase12/note_test.txt

echo "Загружаем файлы в Phase-12 memory..."
for f in ./storage/chroma_phase12/*.txt; do
  RESP=$(curl -s -X POST "http://127.0.0.1:8000/ingest/file/phase12" \
    -H "X-User: dev" \
    -F "file=@$f")
  if [[ "$RESP" == *'"ok":true'* ]]; then
    echo "✅ Загружен $f"
  else
    echo "⚠️ Ошибка загрузки $f: $RESP"
  fi
done

NEW_NOTE="Phase-12 авто-тест: память и RAG проверка"
echo "Результат поиска Phase-12:"

RESP=$(curl -s -G "http://127.0.0.1:8000/memory/search/phase12" \
  -H "X-User: dev" \
  --data-urlencode "q=$NEW_NOTE")

echo "$RESP" | jq .

P3=$(echo "$RESP" | jq '[.results[0:3][] | select(.metadata.user_id=="dev")] | length / 3')
echo ""; echo "P@3 ≈ $P3"

if (( $(echo "$P3 >= 0.7" | bc -l) )); then
    echo "✅ Phase-12 RAG OK"
else
    echo "❌ Phase-12 RAG < 0.7"
fi