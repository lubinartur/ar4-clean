# AIR4 — Локальный оффлайн-ассистент

## 📌 Описание
AIR4 — это автономный ИИ-ассистент с долговременной памятью, работающий полностью локально на macOS (M-серия).  
На текущем этапе: LLM-ядро (Mistral 7B) через Ollama + FastAPI API.

## 🚀 Запуск (локально)

### 1. Подготовка
# Клонировать репозиторий
git clone <repo_url>
cd air4

# Создать окружение
python3 -m venv .venv
source .venv/bin/activate

# Установить зависимости
pip install -r requirements.txt

# Установить Ollama и скачать модель
brew install ollama
ollama pull mistral

### 2. Конфигурация
cp .env.template .env
nano .env
# Задайте:
# SAFE_WORD — секретное слово для опасных команд.
# PANIC_PHRASE — паник-фраза для мгновенной блокировки.

### 3. Запуск сервера
make dev
# или
uvicorn backend.app.main:app --reload

### 4. Проверка
curl http://127.0.0.1:8000/health
curl -X POST "http://127.0.0.1:8000/chat" \
  -H "Content-Type: application/json" \
  -d '{"message":"Привет"}'

## 📂 Структура проекта
backend/        # Код API и логика
memory/         # Память и эмбеддинги (пусто)
ui/             # Каркас будущего интерфейса
scripts/        # Скрипты автоматизации
docs/           # Документация
.env.template   # Шаблон конфигурации
Makefile        # Запуск и форматирование

## 📅 Этапы разработки
См. roadmap в docs/ROADMAP.md

## Phase-10: RAG smoke

**Цель:** гарантировать стабильное качество извлечения знаний (retrieval) на локальном корпусе `tests/rag_corpus/` под шумом.

**Зелёный критерий:** `avg p@3 ≥ 0.7` на скрипте `scripts/smoke_phase10_rag.sh`.

**Локальный прогон:**
```bash
make serve
make smoke-phase10
make kill-serve
```

**Корпус:**
- Документы: `tests/rag_corpus/docs/` (включая шум в `docs/noise/`)
- Запросы: `tests/rag_corpus/queries.tsv`

**CI:**
- Workflow: `.github/workflows/rag-smoke.yml`
- Джоб падает, если `avg p@3 < 0.7`. Логи смоука сохраняются как artifact.
