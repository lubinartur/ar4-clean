---
title: Ingest Pipeline
phase: 10
topic: ingest
created: 2025-08-23
tags: [ingest, readers, pdf, docx, md, txt]
---

Поддерживаемые источники: **.pdf / .docx / .md / .txt**.

Эндпоинты:
- POST /ingest/file — загрузка файла
- POST /ingest/url  — скачивание и разбор по URL

Читалки и чанкинг: backend/app/ingest/readers.py
