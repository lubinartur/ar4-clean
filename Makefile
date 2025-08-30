SHELL := /opt/homebrew/bin/bash
HOST ?= 127.0.0.1
PORT ?= 8000
UVICORN := uvicorn
APP := backend.app.main:app
PY := python

.PHONY: serve kill-serve wait health smoke-phase10 smoke-ci

serve:
	@echo ">> Launching API on $(HOST):$(PORT)"
	@$(UVICORN) $(APP) --host $(HOST) --port $(PORT) --reload > .uvicorn.out 2>&1 & echo $$! > .uvicorn.pid
	@$(MAKE) wait

kill-serve:
	@if [ -f .uvicorn.pid ]; then \
		pkill -P `cat .uvicorn.pid` || true; \
		kill `cat .uvicorn.pid` || true; \
		rm -f .uvicorn.pid; \
	fi

wait:
	@echo ">> Waiting for /health..."
	@for i in {1..60}; do \
		code=$$(curl -s -o /dev/null -w "%{http_code}" "http://$(HOST):$(PORT)/health" || true); \
		if [ "$$code" = "200" ]; then echo "health: $$code"; exit 0; fi; \
		sleep 0.5; \
	done; \
	echo "FAIL: /health not 200"; exit 1

health:
	@curl -s -o /dev/null -w "%{http_code}\n" "http://$(HOST):$(PORT)/health"
	@curl -s -o /dev/null -w "%{http_code}\n" "http://$(HOST):$(PORT)/__routes" || true

smoke-phase10:
	@echo ">> Running Phase-10 smoke"
	@/opt/homebrew/bin/bash scripts/smoke_phase10_rag.sh | tee .smoke.log
	@AVG=$$(grep -Eo 'avg p@3[[:space:]]*=[[:space:]]*[0-9.]+' .smoke.log | tail -1 | sed -E 's/.*=[[:space:]]*([0-9.]+)/\1/'); \
	echo "Detected avg p@3 = $$AVG"; \
	awk -v a="$$AVG" 'BEGIN{exit (a>=0.7)?0:1}' && echo "OK: >= 0.7" || (echo "FAIL: < 0.7"; exit 1)

smoke-ci:
	@$(MAKE) serve
	@$(MAKE) smoke-phase10
	@$(MAKE) kill-serve
