# tests/rag_corpus/evaluate_rag.py
import argparse, json, os
from pathlib import Path
import requests

def doc_basename_from_meta(meta: dict) -> str | None:
    # пробуем разные ключи метаданных
    for key in ("filename","file","path","source_path","source","doc"):
        val = meta.get(key)
        if not val:
            continue
        name = os.path.basename(str(val))
        return name
    return None

def unique_basenames(results):
    seen, out = set(), []
    for r in results:
        # поддерживаем и meta, и metadata
        meta = r.get("metadata") or r.get("meta") or {}
        name = doc_basename_from_meta(meta)
        if not name:
            # fallback: ищем любой строковый путь
            for k,v in r.items():
                if k != "text" and isinstance(v, str) and ("/" in v or "\\" in v):
                    cand = os.path.basename(v)
                    if cand:
                        name = cand
                        break
        if name and name not in seen:
            seen.add(name)
            out.append(name)
    return out

def precision_at_k_norm(preds, expected, k=3):
    preds_k = preds[:k]
    hits = sum(1 for p in preds_k if p in expected)
    denom = max(1, min(k, len(expected)))
    return hits / float(denom)

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", default="http://127.0.0.1:8000", help="API base URL")
    ap.add_argument("--k", type=int, default=3)
    ap.add_argument("--mmr", type=float, default=0.5)
    ap.add_argument("--hyde", type=int, default=1)
    ap.add_argument("--recency_days", type=int, default=365)
    ap.add_argument("--where_json", default=None, help='JSON-строка фильтра, например {"tag":"phase10"}')
    ap.add_argument("--candidate_multiplier", type=int, default=8)
    args = ap.parse_args()

    queries_path = Path("tests/rag_corpus/queries.json")
    queries = json.loads(queries_path.read_text())

    p_at3_list = []
    rows = []

    for q in queries:
        query = q["query"]
        expected_docs = set(q["expected_docs"])

        params = {
            "q": query,
            "k": args.k,
            "mmr": args.mmr,
            "hyde": args.hyde,
            "recency_days": args.recency_days,
            "candidate_multiplier": args.candidate_multiplier,
        }
        if args.where_json:
            params["where_json"] = args.where_json

        resp = requests.get(f"{args.base}/memory/search", params=params, timeout=20)
        resp.raise_for_status()
        data = resp.json()
        results = data.get("results") if isinstance(data, dict) else data or []

        pred_names = unique_basenames(results)
        p3 = precision_at_k_norm(pred_names, expected_docs, k=args.k)
        p_at3_list.append(p3)

        rows.append({
            "id": q["id"],
            "query": query,
            "expected": sorted(list(expected_docs)),
            "predicted@k": pred_names[:args.k],
            "p@3": p3
        })

    macro = sum(p_at3_list)/len(p_at3_list) if p_at3_list else 0.0

    print("=== RAG Evaluation (Phase-10) ===")
    for r in rows:
        print(f"[{r['id']}] p@3={r['p@3']:.3f}")
        print(f"  expected:  {r['expected']}")
        print(f"  predicted: {r['predicted@k']}")
    print(f"\nMacro P@3: {macro:.3f}")

if __name__ == "__main__":
    main()
