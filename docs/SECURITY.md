# Security Invariants and Boundaries

**Version:** Phase B6  
**Last Updated:** 2025-01-XX

This document defines the security guarantees and boundaries enforced by the AIr4 system. All guarantees are enforced at the API layer and memory storage layer.

---

## 1. Session Boundaries

### Guarantees

- **No implicit sessions**: All endpoints that require session context must receive an explicit `session_id` parameter.
- **Session validation**: `session_id` is validated before any operation:
  - Must be a non-empty string
  - Cannot be whitespace-only
  - Must exist in either in-memory `_SESSIONS` or persisted `data/sessions/index.json`
  - Invalid `session_id` returns HTTP 400 (not 404, not silent fail)
- **Session creation**: New sessions are created explicitly via `POST /sessions` or `ensure_session()`. No automatic session creation on first access.

### What is NOT allowed

- Operations without `session_id` where session context is required
- Implicit session creation from request headers or cookies
- Session ID injection via path parameters without validation
- Cross-session access via session_id manipulation (see Memory Isolation)

---

## 2. Memory Isolation by session_id

### Guarantees

- **Session-scoped storage**: All memory operations require `session_id` and store data with `session_id` in metadata.
- **Search isolation**: Memory search operations filter results by `session_id`:
  - `/memory/search` requires `session_id` parameter
  - Results only include items where `meta.session_id` matches the provided `session_id`
  - No cross-session data leakage in search results
- **Delete protection**: Memory deletion verifies ownership:
  - `/memory/delete` checks that the target item's `meta.session_id` matches the request's `session_id`
  - Cross-session deletion attempts return HTTP 403
  - Idempotent: deleting non-existent items returns success (no error)
- **RAG context isolation**: RAG context retrieval (`_retrieve_rag_context`) passes `session_id` to memory search, ensuring context is session-scoped.

### What is NOT allowed

- Reading memory items from a different session
- Deleting memory items from a different session (HTTP 403)
- Search results that include items from other sessions
- RAG context that includes data from other sessions

---

## 3. Write Guards

### Guarantees

- **No empty writes**: All write operations validate input before storage:
  - Text must be non-empty string (not `None`, not empty string)
  - Text must not be whitespace-only after `strip()`
  - Minimum length validation (e.g., `/memory/add` requires at least 5 characters)
  - Invalid input returns HTTP 400 with descriptive error message
- **Duplicate prevention**: Write operations check for duplicates before insertion:
  - `/memory/add` normalizes text (lowercase, strip) and checks against existing documents in the same session
  - Duplicate detection is case-insensitive and whitespace-normalized
  - Duplicates return `{"ok": True, "skipped": True}` (idempotent, no error)
- **Type validation**: All request bodies use Pydantic models:
  - No raw `dict` or `Any` types for request bodies
  - Required fields are explicitly marked with `Field(...)`
  - Type mismatches return HTTP 422 (FastAPI automatic validation)

### What is NOT allowed

- Empty or whitespace-only text writes
- Duplicate writes (detected and skipped, not stored)
- Writes without proper type validation
- Silent failures on invalid input (always returns HTTP 400/422)

---

## 4. MEMORY_MODE Behavior

### Guarantees

- **Strict mode** (`MEMORY_MODE=strict`):
  - ChromaDB initialization failure raises `RuntimeError` and stops server startup
  - No fallback to in-memory adapter
  - Ensures persistent storage is available before accepting requests
- **Fallback mode** (`MEMORY_MODE=fallback`, default):
  - ChromaDB initialization failure logs warning and uses `InMemoryMemoryAdapter`
  - Server continues startup with degraded functionality
  - In-memory adapter is session-scoped but not persistent across restarts
- **Mode validation**: Invalid `MEMORY_MODE` values default to `fallback` with warning log

### What is NOT allowed

- Silent failures in strict mode (must raise and stop startup)
- Fallback mode without explicit logging
- Memory operations when `MEMORY` is `None` (returns HTTP 503)

---

## 5. API Validation Guarantees

### Guarantees

- **Pydantic models for all request bodies**: No manual JSON parsing:
  - `/chat` uses `ChatRequest` model
  - `/chat/stream` uses `ChatStreamRequest` model
  - `/chat/rag` uses `ChatRagRequest` model
  - `/send3` uses `Send3In` model
  - `/memory/add` uses `AddBody` model
  - `/memory/delete` uses `DeleteBody` model
  - `/ingest/url` uses `URLIn` model
- **Query parameter validation**: All query parameters have constraints:
  - `session_id`: Required, `min_length=1`
  - `tag`: Optional, `min_length=1, max_length=100`
  - `name`: Required for `/ingest/commit`, `min_length=1, max_length=500`
  - `url`: Required for `/ingest/url`, `min_length=1, max_length=2048`
- **Error responses**: Invalid input always returns HTTP 400 (not 500, not silent fail):
  - Missing required fields: HTTP 400
  - Type mismatches: HTTP 422 (FastAPI automatic)
  - Validation failures: HTTP 400 with descriptive `detail` message
  - No silent failures or default values for invalid input

### What is NOT allowed

- Manual `request.json()` parsing (all endpoints use Pydantic)
- Raw `dict` or `Any` types for request bodies
- Optional fields without explicit justification
- HTTP 500 errors for invalid input (must be 400/422)
- Silent failures or default values for invalid input

---

## 6. Input Sanitization

### Guarantees

- **String normalization**: All string inputs are validated and normalized:
  - `session_id` is stripped of whitespace before validation
  - Text inputs are stripped before duplicate checking
  - Case-insensitive duplicate detection (normalized to lowercase)
- **Length constraints**: All string fields have explicit length limits:
  - Prevents buffer overflow and DoS via oversized inputs
  - Query text: no explicit limit (handled by LLM timeout)
  - URLs: max 2048 characters
  - Tags: max 100 characters
  - File names: max 500 characters

### What is NOT allowed

- Unbounded string inputs without validation
- SQL injection (not applicable: no SQL queries)
- Path traversal (file operations use validated paths only)

---

## 7. Error Handling

### Guarantees

- **Consistent error codes**:
  - Invalid input: HTTP 400
  - Validation errors: HTTP 422
  - Forbidden (cross-session): HTTP 403
  - Not found: HTTP 404
  - Service unavailable (memory disabled): HTTP 503
  - Internal errors: HTTP 500 (only for unexpected exceptions)
- **Error messages**: All errors include descriptive `detail` messages:
  - No generic "error occurred" messages
  - Specific validation failure reasons
  - No stack traces in production responses

### What is NOT allowed

- HTTP 500 for invalid input (must be 400/422)
- Silent failures (all errors return HTTP status codes)
- Stack traces in error responses
- Generic error messages without context

---

## 8. Security Boundaries Summary

### Enforced Boundaries

1. **Session isolation**: No cross-session data access
2. **Input validation**: All inputs validated via Pydantic before processing
3. **Write guards**: No empty/duplicate writes
4. **Type safety**: No raw dict/Any types in request bodies
5. **Error transparency**: Invalid input always returns 400/422

### Explicitly NOT Guaranteed

1. **Authentication/Authorization**: No user authentication or RBAC (single-user system)
2. **Rate limiting**: No rate limiting on API endpoints
3. **Encryption at rest**: Memory data stored in plaintext (ChromaDB, JSON files)
4. **Encryption in transit**: Assumes HTTPS at reverse proxy (not enforced by application)
5. **Audit logging**: No comprehensive audit trail of all operations
6. **Data retention**: No automatic cleanup of old sessions or memory items

---

## 9. Implementation Notes

### Session Validation

```python
def validate_session_id(session_id: Optional[str]) -> str:
    # Raises HTTPException(400) if invalid
    # Checks both in-memory _SESSIONS and persisted index.json
```

### Memory Isolation

```python
# All memory operations include session_id in metadata
meta = {"session_id": session_id, ...}

# Search filters by session_id
results = memory.search(..., session_id=session_id, ...)

# Delete verifies ownership
if record_meta.get("session_id") != session_id:
    raise HTTPException(403, "Cannot delete memory from another session")
```

### Write Guards

```python
# Input validation before write
if not text or not text.strip() or len(text.strip()) < 5:
    raise HTTPException(400, "text must be at least 5 characters")

# Duplicate check
if text_normalized in existing_docs:
    return {"ok": True, "skipped": True}
```

---

## 10. Testing Security Invariants

To verify security guarantees:

1. **Session isolation**: Attempt to read/delete memory from different session_id → should fail
2. **Input validation**: Send invalid input (empty, wrong type) → should return 400/422
3. **Write guards**: Attempt to write empty/duplicate text → should be rejected or skipped
4. **MEMORY_MODE**: Set `MEMORY_MODE=strict` with invalid ChromaDB config → should fail startup
5. **Cross-session deletion**: Attempt to delete memory item from different session → should return 403

---

**End of Document**
