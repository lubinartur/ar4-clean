BASE ?= http://localhost:8000

.PHONY: smoke-rbac smoke-audit

smoke-rbac:
	@echo "== Duress login =="
	@TOKEN_DURESS=$$(curl -s -X POST "$(BASE)/auth/login" \
		-H "Content-Type: application/json" \
		-d "{\"password\":\"$${DURESS:-9111}\"}" | jq -r '.token'); \
	echo "TOKEN_DURESS=$$TOKEN_DURESS"; \
	echo "== Allowed in duress: /chat =="; \
	curl -s -X POST "$(BASE)/chat" \
		-H "Authorization: Bearer $$TOKEN_DURESS" \
		-H "Content-Type: application/json" \
		-d "{\"message\":\"ping\"}" | jq .; \
	echo "== Allowed in duress: /memory/search =="; \
	curl -s "$(BASE)/memory/search?q=ping&k=1" \
		-H "Authorization: Bearer $$TOKEN_DURESS" | jq .; \
	echo "== Blocked in duress: /memory/add =="; \
	curl -s -o /dev/null -w "HTTP %{http_code}\n" -X POST "$(BASE)/memory/add" \
		-H "Authorization: Bearer $$TOKEN_DURESS" \
		-H "Content-Type: application/json" \
		-d "{\"text\":\"secret\"}"; \
	echo "== Blocked in duress: /api/v0/secure/lock =="; \
	curl -s -o /dev/null -w "HTTP %{http_code}\n" -X POST "$(BASE)/api/v0/secure/lock" \
		-H "Authorization: Bearer $$TOKEN_DURESS"; \
	echo "== Logout duress =="; \
	curl -s -X POST "$(BASE)/auth/logout" \
		-H "Authorization: Bearer $$TOKEN_DURESS" | jq .; \
	echo "== Check revoked token =="; \
	curl -s -o /dev/null -w "HTTP %{http_code}\n" "$(BASE)/api/v0/secure/status" \
		-H "Authorization: Bearer $$TOKEN_DURESS"

smoke-audit:
	@echo "== Reset audit log =="; \
	rm -f storage/audit.log; \
	mkdir -p storage; \
	echo "== Normal login =="; \
	TOKEN=$$(curl -s -X POST "$(BASE)/auth/login" \
		-H "Content-Type: application/json" \
		-d "{\"password\":\"$${AUTH:-0000}\"}" | jq -r '.token'); \
	echo "TOKEN=$$TOKEN"; \
	echo "== chat =="; \
	curl -s -X POST "$(BASE)/chat" \
		-H "Authorization: Bearer $$TOKEN" \
		-H "Content-Type: application/json" \
		-d "{\"message\":\"hello\"}" >/dev/null; \
	echo "== memory.add =="; \
	curl -s -X POST "$(BASE)/memory/add" \
		-H "Authorization: Bearer $$TOKEN" \
		-H "Content-Type: application/json" \
		-d "{\"text\":\"note1\"}" >/dev/null; \
	echo "== lock/unlock =="; \
	curl -s -X POST "$(BASE)/api/v0/secure/lock" \
		-H "Authorization: Bearer $$TOKEN" >/dev/null; \
	curl -s -X POST "$(BASE)/api/v0/secure/unlock" \
		-H "Authorization: Bearer $$TOKEN" >/dev/null; \
	echo "== logout =="; \
	curl -s -X POST "$(BASE)/auth/logout" \
		-H "Authorization: Bearer $$TOKEN" >/dev/null; \
	echo "== AUDIT LOG =="; \
	tail -n +1 storage/audit.log | jq -c .
smoke-llm:
	@TOKEN=$$(curl -s -X POST "$(BASE)/auth/login" \
		-H "Content-Type: application/json" \
		-d "{\"password\":\"$${AUTH:-0000}\"}" | jq -r '.token'); \
	echo "TOKEN=$$TOKEN"; \
	curl -s -X POST "$(BASE)/chat" \
		-H "Authorization: Bearer $$TOKEN" \
		-H "Content-Type: application/json" \
		-d "{\"message\":\"shortly explain what RBAC is\"}" | jq .
