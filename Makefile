# ===== AIR4 Makefile =====
# Переопределяй переменные при запуске: make run PORT=8010
HOST       ?= 0.0.0.0
PORT       ?= 8000
BASE_URL   ?= http://localhost:$(PORT)
APP        ?= backend.app.main:app
UVICORN    ?= uvicorn

# Duress
DURESS_PIN ?= 0000
SMOKE_TXT  ?= секрет под давлением

.PHONY: help run run-dev stop smoke-duress smoke-sec smoke-phase3 deps

help:
	@echo "Targets:"
	@echo "  make run           - запустить сервер (без авто-релоада)"
	@echo "  make run-dev       - запустить сервер с --reload"
	@echo "  make stop          - убить uvicorn на $(PORT)"
	@echo "  make smoke-sec     - проверка /secure/status"
	@echo "  make smoke-duress  - смоук duress: login -> status -> add -> search"
	@echo "  make smoke-phase3  - (если есть) ваш старый смоук из Фазы 3"
	@echo "  make deps          - проверить наличие curl/jq/python3"

deps:
	@command -v curl >/dev/null || (echo "need curl" && exit 1)
	@command -v jq   >/dev/null || (echo "need jq" && exit 1)
	@command -v python3 >/dev/null || (echo "need python3" && exit 1)
	@echo "ok"

run:
	$(UVICORN) $(APP) --host $(HOST) --port $(PORT)

run-dev:
	$(UVICORN) $(APP) --reload --host $(HOST) --port $(PORT)

stop:
	@pkill -f "$(UVICORN) $(APP).*--port $(PORT)" || true
	@echo "stopped (if was running)"

# --- Security / Duress ---
smoke-sec:
	@curl -s "$(BASE_URL)/secure/status" | jq .

smoke-duress: deps
	@BASE_URL="$(BASE_URL)" DURESS_PIN="$(DURESS_PIN)" ./scripts/smoke_duress.sh "$(SMOKE_TXT)"

# заглушка под ваш старый скрипт (если существует)
smoke-phase3:
	@test -x scripts/smoke_phase3.sh && ./scripts/smoke_phase3.sh || echo "scripts/smoke_phase3.sh not found (skip)"
