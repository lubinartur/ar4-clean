#!/usr/bin/env bash
set -e

# 1) Установка зависимостей
if [ -f requirements.txt ]; then
  python -m pip install -r requirements.txt
fi

# 2) Восстановление памяти (если передан архив как 1-й аргумент)
if [ -n "$1" ]; then
  echo "Restoring Chroma from archive: $1"
  rm -rf storage/chroma
  mkdir -p storage
  tar -xzf "$1" -C storage/
fi

# 3) Обязательные переменные для Ollama (подстрой под себя)
export OLLAMA_MODEL=${OLLAMA_MODEL:-mistral:latest}
export OLLAMA_BASE_URL=${OLLAMA_BASE_URL:-http://localhost:11434}

# 4) Запуск API
exec uvicorn backend.app.main:app --host 0.0.0.0 --port 8001

