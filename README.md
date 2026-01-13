# AIr4 v1.0 Release Candidate

**Status: v1.0.0-rc1 - API Frozen**

This is the v1.0 release candidate. Core functionality is complete and stabilized. **No new features will be added before v1.0 release.** Only bug fixes and critical stability improvements are permitted.

---

## Quick start
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

# подготовить локальные эмбеддинги (один раз)
python - <<'PY'
from sentence_transformers import SentenceTransformer
m = SentenceTransformer("sentence-transformers/all-MiniLM-L6-v2")
m.save("data/embeddings/all-MiniLM-L6-v2")
print("Saved embeddings.")
PY

# запуск
export $(grep -v '^#' .env.example | xargs)  # или создать свой .env
uvicorn backend.app.main:app --reload --port 8000

## Notes
- LLM: OLLAMA_MODEL_DEFAULT=llama3.1:8b
- Memory: Chroma в ./data/chroma
- Embeddings: ./data/embeddings/all-MiniLM-L6-v2
- UI: /ui/chat
- Health: /health
- Поиск: /memory/search
