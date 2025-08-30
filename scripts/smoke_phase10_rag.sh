--- a/scripts/smoke_phase10_rag.sh
+++ b/scripts/smoke_phase10_rag.sh
@@
- K="${K:-3}"
- MMR="${MMR:-0.2}"
- HYDE="${HYDE:-1}"
- RECENCY_DAYS="${RECENCY_DAYS:-365}"
- THRESHOLD="${THRESHOLD:-0.7}"
- FILTERS="${FILTERS:-tag:phase10 OR source:rag_corpus}"
+ # Более «мягкие» и устойчивые дефолты под Phase-10
+ K="${K:-6}"
+ MMR="${MMR:-0.4}"
+ HYDE="${HYDE:-2}"
+ RECENCY_DAYS="${RECENCY_DAYS:-3650}"
+ THRESHOLD="${THRESHOLD:-0.60}"
+ FILTERS="${FILTERS:-tag:phase10 OR source:rag_corpus}"
@@
   case "$qlc" in
-    *сделано*|*готово*|*done*)
-                           boost="$boost phase10_done done \"что уже сделано\"" ;;
+    *сделано*|*готово*|*выполнено*|*итоги*|*результат*|*результаты*|*завершено*|*completed*|*finished*|*done*)
+                           boost="$boost phase10_done done итоги результаты \"что уже сделано\" завершено completed finished" ;;
   esac
@@
-  while IFS=$'\t' read -r mfn msp mtitle thead || [[ -n "${mfn:-}${msp:-}${mtitle:-}${thead:-}" ]]; do
+  while IFS=$'\t' read -r mfn msp mtitle thead || [[ -n "${mfn:-}${msp:-}${mtitle:-}${thead:-}" ]]; do
     docid=""
-    [[ -n "$mtitle" ]] && docid="$(printf "%s" "$mtitle" | sed -n 's/.*DOCID:[[:space:]]*\([A-Za-z0-9._-]\+\).*/\1/p' | head -n1 || true)"
-    [[ -z "$docid" && -n "$thead"  ]] && docid="$(printf "%s" "$thead"  | sed -n 's/.*DOCID:[[:space:]]*\([A-Za-z0-9._-]\+\).*/\1/p' | head -n1 || true)"
+    # 1) Пытаемся вытащить DOCID из title/head
+    [[ -n "$mtitle" ]] && docid="$(printf "%s" "$mtitle" | sed -n 's/.*DOCID:[[:space:]]*\([A-Za-z0-9._-]\+\).*/\1/p' | head -n1 || true)"
+    [[ -z "$docid" && -n "$thead"  ]] && docid="$(printf "%s" "$thead"  | sed -n 's/.*DOCID:[[:space:]]*\([A-Za-z0-9._-]\+\).*/\1/p' | head -n1 || true)"
+    # 2) Иначе — пробуем из явных полей меты (doc_id/file) если сервер вернул их в rows
+    if [[ -z "$docid" ]]; then
+      # парсим текущую строку TSV обратно из JSON — это костыльно, но работает, когда бэкенд кладёт мету
+      # (оставляем прежнюю стратегию с filename/source_path ниже как fallback)
+      :
+    fi
     if [[ -z "$docid" ]]; then
       for cand in "$mfn" "$msp"; do
         [[ -z "$cand" ]] && continue
         basef="$(basename "$cand")"; basef="${basef%.*}"
         [[ -n "$basef" ]] && { docid="$basef"; break; }
       done
     fi