# v1.0 Release Checklist

**Version:** v1.0.0-rc1 → v1.0.0  
**Status:** Pre-release validation

This checklist must be completed before releasing v1.0. All items must be checked (✅) before proceeding with the release.

---

## Runtime Checks

### Server Startup
- [ ] Server starts without errors on clean environment
- [ ] All required environment variables are documented and validated
- [ ] MEMORY_MODE=strict fails gracefully when ChromaDB is unavailable
- [ ] MEMORY_MODE=fallback works when ChromaDB is unavailable
- [ ] Server logs version correctly on startup: `v1.0.0-rc1` (or `v1.0.0`)

### Health & Status Endpoints
- [ ] `/health` endpoint returns 200 OK
- [ ] `/health` response includes version information
- [ ] `/health` response includes memory status (enabled/disabled)
- [ ] Health check completes in < 1 second

### Core API Endpoints
- [ ] `/sessions` (GET) - Lists all sessions
- [ ] `/sessions` (POST) - Creates new session
- [ ] `/sessions/{session_id}` (GET) - Retrieves session details
- [ ] `/chat` (POST) - Processes chat message and returns response
- [ ] `/chat/stream` (POST) - Streams chat response via SSE
- [ ] `/memory/search` (GET) - Searches vector memory with session isolation
- [ ] `/memory/add` (POST) - Adds manual memory/note
- [ ] `/memory/delete` (POST) - Deletes memory item with ownership check
- [ ] `/facts` (GET) - Lists facts for subject
- [ ] `/facts/profile` (GET) - Retrieves structured profile
- [ ] `/ingest/file` (POST) - Uploads and processes file
- [ ] `/ingest/queue` (GET) - Returns ingest queue status
- [ ] `/models/ollama` (GET) - Lists available Ollama models

### UI Endpoints
- [ ] `/ui/chat` - Chat UI loads correctly
- [ ] `/ui/ingest` - Ingest UI loads correctly
- [ ] Static files served correctly (`/static/*`)
- [ ] Templates render without errors

---

## Security Checks

### Session Boundaries
- [ ] Session validation rejects empty/whitespace-only `session_id`
- [ ] Session validation rejects non-existent `session_id` (returns 400, not 404)
- [ ] No implicit session creation on first access
- [ ] All endpoints requiring `session_id` validate it before processing

### Memory Isolation
- [ ] `/memory/search` only returns results from the provided `session_id`
- [ ] Cross-session memory access is blocked (no data leakage)
- [ ] `/memory/delete` verifies ownership (returns 403 for cross-session deletion)
- [ ] RAG context is session-scoped (no cross-session data in context)

### Write Guards
- [ ] Empty text writes are rejected (returns 400)
- [ ] Whitespace-only text writes are rejected (returns 400)
- [ ] Minimum length validation enforced (e.g., 5 characters for `/memory/add`)
- [ ] Duplicate writes are detected and skipped (returns `{"ok": True, "skipped": True}`)
- [ ] Duplicate detection is case-insensitive and whitespace-normalized

### Input Validation
- [ ] All request bodies use Pydantic models (no raw `dict` or `Any`)
- [ ] Type mismatches return HTTP 422 (FastAPI automatic validation)
- [ ] Invalid input returns HTTP 400 with descriptive error message
- [ ] Query parameters have proper constraints (min_length, max_length)
- [ ] URL length limit enforced (max 2048 characters)
- [ ] Tag length limit enforced (max 100 characters)
- [ ] File name length limit enforced (max 500 characters)

### Error Handling
- [ ] Invalid input returns HTTP 400/422 (not 500)
- [ ] Cross-session deletion returns HTTP 403
- [ ] Service unavailable (memory disabled) returns HTTP 503
- [ ] Error messages are descriptive (no generic "error occurred")
- [ ] No stack traces in production error responses

### Security Boundaries Verification
- [ ] Session isolation test: Attempt to read memory from different `session_id` → fails
- [ ] Session isolation test: Attempt to delete memory from different `session_id` → returns 403
- [ ] Input validation test: Send empty text → returns 400
- [ ] Input validation test: Send wrong type → returns 422
- [ ] Write guard test: Attempt duplicate write → skipped, not stored
- [ ] MEMORY_MODE test: `MEMORY_MODE=strict` with invalid config → fails startup

---

## Smoke Tests

### Phase 12 Smoke Test
- [ ] Run `scripts/smoke_phase12.sh` - All checks pass
  - Health endpoint responds
  - UI/ingest endpoint loads
  - File ingest works
  - Memory search works

### RAG Smoke Test
- [ ] Run `scripts/smoke_rag.sh` - RAG pipeline works end-to-end
  - File upload succeeds
  - Memory search finds uploaded content
  - Search results are correct

### Stream Smoke Test
- [ ] Run `scripts/smoke_stream.sh` - Streaming endpoint works
  - SSE stream delivers data correctly
  - Stream format is correct
  - Expected content appears in stream

### Additional Smoke Tests
- [ ] Run `scripts/smoke_phaseC.sh` - Core functionality works
- [ ] Run `scripts/smoke_ui_ingest.sh` - UI ingest workflow works
- [ ] Manual test: Full chat conversation with memory persistence
- [ ] Manual test: Facts extraction and profile generation

---

## Release Hygiene

### Version Consistency
- [ ] `VERSION` file contains `v1.0.0` (not `-rc1`)
- [ ] `backend/app/main.py` - `APP_VERSION = "1.0.0"` (not `1.0.0-rc1`)
- [ ] `backend/app/main.py` - Header comment reflects v1.0.0
- [ ] `README.md` header shows `v1.0` (not `v1.0 Release Candidate`)
- [ ] FastAPI app version matches: `FastAPI(version=APP_VERSION)`
- [ ] All version references are consistent across codebase

### Documentation
- [ ] `README.md` is up-to-date with current setup instructions
- [ ] `docs/API_CONTRACT.md` reflects current API surface
- [ ] `docs/SECURITY.md` is accurate and complete
- [ ] `docs/RELEASE_CHECKLIST.md` is complete (this file)
- [ ] All deprecated endpoints are clearly marked
- [ ] All breaking changes since previous version are documented

### Code Quality
- [ ] No `TODO` or `FIXME` comments in critical paths
- [ ] No debug logging in production code
- [ ] All imports are properly organized
- [ ] No unused imports or dead code
- [ ] Code passes linting checks (if configured)

### Git & Tagging
- [ ] All changes are committed to version control
- [ ] Working directory is clean (no uncommitted changes)
- [ ] Create git tag: `git tag v1.0.0 -m "Release v1.0.0"`
- [ ] Tag is annotated with release message
- [ ] Consider creating a release branch if using git-flow

### Build & Dependencies
- [ ] `requirements.txt` is up-to-date and pinned
- [ ] `requirements-memory.txt` is up-to-date (if applicable)
- [ ] All dependencies are production-ready versions
- [ ] No development-only dependencies in production requirements
- [ ] Virtual environment can be recreated from requirements files

### Data & Configuration
- [ ] Default configuration works out-of-the-box
- [ ] `.env.example` includes all required environment variables
- [ ] Data directories can be created automatically if missing
- [ ] No hardcoded paths that break on different systems
- [ ] Backward compatibility: Data from previous versions can be migrated (if applicable)

### Performance
- [ ] Server starts within reasonable time (< 10 seconds)
- [ ] Health check responds quickly (< 1 second)
- [ ] Memory search completes in reasonable time (< 5 seconds for typical queries)
- [ ] Chat endpoint responds within acceptable latency
- [ ] No obvious memory leaks in extended testing

### Testing Coverage
- [ ] Critical paths have been manually tested
- [ ] Edge cases have been tested (empty input, invalid input, etc.)
- [ ] Error cases have been tested (service unavailable, invalid config, etc.)
- [ ] Cross-session isolation has been verified
- [ ] Memory persistence works across server restarts

---

## Final Verification

### Pre-Release Sign-off
- [ ] All runtime checks completed
- [ ] All security checks verified
- [ ] All smoke tests passing
- [ ] All release hygiene items completed
- [ ] Release notes prepared (if maintaining CHANGELOG.md)
- [ ] Version numbers updated and consistent

### Release Decision
- [ ] Team review completed (if applicable)
- [ ] No blocking issues identified
- [ ] Ready for production deployment

---

## Post-Release

After release, verify:
- [ ] Release tag created and pushed
- [ ] Release notes published (if applicable)
- [ ] Deployment successful
- [ ] Post-deployment smoke test passes
- [ ] Monitor logs for errors in first 24 hours

---

## Notes

- **If all items are checked, v1.0 can be released.**
- Items marked with ⚠️ are warnings - investigate but not necessarily blocking
- Items marked with 🔴 are critical - must pass before release
- Keep this checklist updated as the project evolves

---

**Checklist Version:** 1.0  
**Last Updated:** 2025-01-XX  
**Next Review:** Post v1.0 release
