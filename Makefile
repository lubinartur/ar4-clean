BASE ?= http://localhost:8000
.PHONY: smoke-rbac smoke-audit
smoke-rbac:
	@TOKEN_DURESS=$$(curl -s -X POST "$(BASE)/auth/login" -H "Content-Type: application/json" -d '{"password":"$${DURESS:-9111}"}' | jq -r '.token'); \
	curl -s -X POST "$(BASE)/chat" -H "Authorization: Bearer $$TOKEN_DURESS" -H "Content-Type: application/json" -d '{"message":"ping"}' | jq .; \
	curl -s "$(BASE)/memory/search?q=ping&k=1" -H "Authorization: Bearer $$TOKEN_DURESS" | jq .; \
	curl -s -o /dev/null -w "HTTP %{http_code}\n" -X POST "$(BASE)/memory/add" -H "Authorization: Bearer $$TOKEN_DURESS" -H "Content-Type: application/json" -d '{"text":"secret"}'; \
	curl -s -o /dev/null -w "HTTP %{http_code}\n" -X POST "$(BASE)/api/v0/secure/lock" -H "Authorization: Bearer $$TOKEN_DURESS"; \
	curl -s -X POST "$(BASE)/auth/logout" -H "Authorization: Bearer $$TOKEN_DURESS" | jq .; \
	curl -s -o /dev/null -w "HTTP %{http_code}\n" "$(BASE)/api/v0/secure/status" -H "Authorization: Bearer $$TOKEN_DURESS"
smoke-audit:
	@rm -f storage/audit.log; mkdir -p storage; \
	TOKEN=$$(curl -s -X POST "$(BASE)/auth/login" -H "Content-Type: application/json" -d '{"password":"$${AUTH:-0000}"}' | jq -r '.token'); \
	curl -s -X POST "$(BASE)/chat" -H "Authorization: Bearer $$TOKEN" -H "Content-Type: application/json" -d '{"message":"hello"}' >/dev/null; \
	curl -s -X POST "$(BASE)/memory/add" -H "Authorization: Bearer $$TOKEN" -H "Content-Type: application/json" -d '{"text":"note1"}' >/dev/null; \
	curl -s -X POST "$(BASE)/api/v0/secure/lock" -H "Authorization: Bearer $$TOKEN" >/dev/null; \
	curl -s -X POST "$(BASE)/api/v0/secure/unlock" -H "Authorization: Bearer $$TOKEN" >/dev/null; \
	curl -s -X POST "$(BASE)/auth/logout" -H "Authorization: Bearer $$TOKEN" >/dev/null; \
	tail -n +1 storage/audit.log | jq -c .
