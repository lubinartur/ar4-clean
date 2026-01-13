# API Contract: GoogleUI Backend Endpoints

**Version:** Phase-12 (v0.12.1)  
**Purpose:** Define the minimal API surface used by GoogleUI for Phase B security hardening.

---

## Active Endpoints (Used by GoogleUI)

### Health & Status
| Path | Method | Purpose | Used by GoogleUI |
|------|--------|---------|------------------|
| `/health` | GET | System health check and status | ✅ Yes |

### Sessions
| Path | Method | Purpose | Used by GoogleUI |
|------|--------|---------|------------------|
| `/sessions` | GET | List all chat sessions | ✅ Yes |
| `/sessions` | POST | Create new session | ✅ Yes |
| `/sessions/{session_id}` | GET | Get session with messages | ✅ Yes |

### Chat
| Path | Method | Purpose | Used by GoogleUI |
|------|--------|---------|------------------|
| `/chat` | POST | Send message and get response | ✅ Yes |
| `/chat/stream` | POST | Stream chat response (SSE) | ✅ Yes |

### Memory
| Path | Method | Purpose | Used by GoogleUI |
|------|--------|---------|------------------|
| `/memory/search` | GET | Search vector memory | ✅ Yes |
| `/memory/add` | POST | Add manual memory/note | ✅ Yes |
| `/memory/delete` | POST | Delete memory item | ⚠️ Called but NOT implemented |

### Facts (Knowledge Graph)
| Path | Method | Purpose | Used by GoogleUI |
|------|--------|---------|------------------|
| `/facts` | GET | List facts for subject | ✅ Yes |
| `/facts/profile` | GET | Get structured profile from facts | ✅ Yes |

### Ingest
| Path | Method | Purpose | Used by GoogleUI |
|------|--------|---------|------------------|
| `/ingest/file` | POST | Upload and process file | ✅ Yes |
| `/ingest/queue` | GET | Get ingest queue status | ✅ Yes |

### Models
| Path | Method | Purpose | Used by GoogleUI |
|------|--------|---------|------------------|
| `/models/ollama` | GET | List available Ollama models | ✅ Yes |

### UI
| Path | Method | Purpose | Used by GoogleUI |
|------|--------|---------|------------------|
| `/` | GET | Root redirect to GoogleUI | ✅ Yes |
| `/ui/google` | GET | GoogleUI entry point | ✅ Yes |
| `/ui/google` | HEAD | GoogleUI entry point (HEAD) | ✅ Yes |

---

## Deprecated Endpoints (NOT Used by GoogleUI)

These endpoints are **NOT part of the GoogleUI API contract** and should be considered deprecated for Phase B.

### Chat (Alternative)
| Path | Method | Purpose | Used by GoogleUI |
|------|--------|---------|------------------|
| `/send3` | POST | Alternative chat endpoint | ❌ No |

### Memory (Debug/Internal)
| Path | Method | Purpose | Used by GoogleUI |
|------|--------|---------|------------------|
| `/memory/debug` | GET | Memory diagnostics | ❌ No |
| `/memory/debug/query_raw` | GET | Raw ChromaDB query | ❌ No |
| `/memory/facts` | DELETE | Delete facts by criteria | ❌ No |

### Facts (Management)
| Path | Method | Purpose | Used by GoogleUI |
|------|--------|---------|------------------|
| `/facts/reindex` | POST | Reindex facts to memory | ❌ No |
| `/facts/wipe` | DELETE | Wipe all facts for subject | ❌ No |
| `/facts/purge` | DELETE | Purge facts by filters | ❌ No |

### Ingest (Internal)
| Path | Method | Purpose | Used by GoogleUI |
|------|--------|---------|------------------|
| `/ingest` | POST | Legacy ingest endpoint | ❌ No |
| `/ingest/status` | GET | Ingest inbox status | ❌ No |
| `/ingest/commit` | POST | Commit file from inbox | ❌ No |
| `/ingest/commit-all` | POST | Commit all files | ❌ No |
| `/ingest/clear` | DELETE | Clear ingest inbox | ❌ No |
| `/ingest/preview` | GET | Preview file content | ❌ No |
| `/ingest/recent` | GET | Recent ingest files | ❌ No |
| `/ingest/url` | POST | Ingest from URL | ❌ No |
| `/ingest/process` | POST | Process ingest queue | ❌ No |

### Profile (Management)
| Path | Method | Purpose | Used by GoogleUI |
|------|--------|---------|------------------|
| `/memory/profile` | GET | Get user profile | ❌ No |
| `/memory/profile` | PATCH | Update user profile | ❌ No |
| `/memory/profile` | PUT | Replace user profile | ❌ No |

### RAG (Alternative)
| Path | Method | Purpose | Used by GoogleUI |
|------|--------|---------|------------------|
| `/chat/rag` | POST | Alternative RAG endpoint | ❌ No |

### Stream (Test)
| Path | Method | Purpose | Used by GoogleUI |
|------|--------|---------|------------------|
| `/chat/stream-test` | POST | Stream test endpoint | ❌ No |

### Sessions (Management)
| Path | Method | Purpose | Used by GoogleUI |
|------|--------|---------|------------------|
| `/sessions/{session_id}/clear` | POST | Clear session history | ❌ No |

---

## Notes

### Missing Implementation
- `/memory/delete` — Called by GoogleUI but **NOT implemented** in backend. Returns 404.

### Endpoint Count
- **Active (GoogleUI):** 15 endpoints
- **Deprecated (Not used):** 26+ endpoints

### Phase B Security Hardening
For Phase B, focus security hardening on the **15 active endpoints** listed above. Deprecated endpoints can be:
- Left as-is (for internal tools/scripts)
- Protected with stricter access controls
- Removed in future cleanup phase

---

**Last Updated:** Phase-12 (v0.12.1)  
**Next Review:** Phase B (Security Hardening)
