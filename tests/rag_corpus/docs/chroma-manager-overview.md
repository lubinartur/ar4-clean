---
title: Chroma Memory Manager — Overview
phase: 8
topic: memory
created: 2025-08-19
tags: [chroma, memory, backend]
---

`ChromaMemoryManager` инициализируется в `backend/app/main.py` и доступен как `app.state.memory_manager`.
Он отвечает за хранение/поиск эмбеддингов, индексацию и фильтры `where_json`.

Ключевой модуль: `backend/app/memory/manager_chroma.py`.
