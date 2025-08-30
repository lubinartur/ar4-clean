---
title: Retriever Tuning (MMR / HyDE / Recency)
phase: 10
topic: retrieval
created: 2025-08-23
tags: [retrieval, mmr, hyde, recency, filters]
---

Ретривер реализован в `backend/app/retrieval.py`.

Параметры:
- `mmr` — Maximal Marginal Relevance (0..1), повышает диверсификацию.
- `hyde` — включает HyDE (генерация гипотетического ответа → эмбеддинг).
- `recency_days` — фильтрует документы старше порога.
- `candidate_multiplier` — увеличивает пул кандидатов перед top‑k.
- Фильтры: `where_json` по метаданным (например, `{"phase": 10}`).

Стартовые значения:
- `mmr=0.5`, `hyde=1`, `recency_days=365`, `candidate_multiplier=3`.
