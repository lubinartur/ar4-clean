# Deprecated UI: Legacy HTMX/Jinja Interface

## Status: DEPRECATED

**Effective Date:** Phase-12 (v0.12.1)  
**Replacement:** GoogleUI (React) at `/ui/google`

---

## Summary

The legacy HTMX/Jinja-based UI is **deprecated** and **NOT part of v1.0**.

**GoogleUI (React)** is the **only supported UI** going forward.

---

## What is Deprecated

### Legacy UI Routes (Disabled)
- `/ui/chat` — HTMX chat interface
- `/ui/sessions` — HTMX sessions list
- `/ui/ingest` — HTMX file ingestion
- `/ui/ingest/status` — HTMX ingest status
- `/ui/ingest/commit-all` — HTMX ingest commit
- `/ui/ingest/clear` — HTMX ingest clear
- `/ui/ingest/queue` — HTMX ingest queue
- `/ui/chat/stream` — HTMX chat stream
- `/ui/summary` — HTMX summaries
- `/ui/summaries` — HTMX summaries (alternate)
- `/ui/settings` — HTMX settings
- `/ui/test` — HTMX test page
- `/ui/search` — HTMX search
- `/ui/todos` — HTMX todos

### Legacy UI Routers (Disabled)
- `routes_ui_chat_htmx.py` — HTMX chat router
- `routes_ui_search.py` — HTMX search router
- `routes_todos.py` — HTMX todos router
- `routes_summary.py` — HTMX summary router

### Legacy UI Files (Preserved, Not Active)
- All files in `backend/app/templates/` — Jinja templates
- All HTMX-related routes in `backend/app/main.py` — commented out

---

## Current State

### Active UI
- **GoogleUI (React)** — `/ui/google` → `/static/googleui/dist/index.html`
- **Root redirect** — `GET "/"` → redirects to `/ui/google`

### Legacy UI
- **All routes disabled** — commented out in `main.py`
- **All routers disabled** — `include_router()` calls commented out
- **Files preserved** — kept for reference, not deleted

---

## Development Rules

### Phase A–B (Current)
- **DO NOT modify** legacy UI code
- **DO NOT re-enable** legacy UI routes
- **DO NOT add features** to legacy UI
- **DO NOT fix bugs** in legacy UI (unless critical security)

### Allowed Actions
- ✅ Add DEPRECATED comments
- ✅ Document deprecation status
- ✅ Reference legacy code for understanding
- ✅ Remove legacy code in future phases (post-v1.0)

### Forbidden Actions
- ❌ Re-enabling legacy routes
- ❌ Modifying legacy templates
- ❌ Adding new HTMX/Jinja routes
- ❌ Fixing non-critical legacy UI bugs

---

## Migration Path

**For users:** Use GoogleUI at `/ui/google` or root `/`.

**For developers:** All new UI work must target GoogleUI (React).

**For cleanup:** Legacy UI code will be removed in a future phase (post-v1.0).

---

## Technical Details

### Why Deprecated
- GoogleUI provides full feature parity
- React-based architecture is more maintainable
- Legacy HTMX/Jinja UI is no longer actively developed
- Single UI reduces maintenance burden

### Why Not Deleted
- Preserved for reference during transition
- May contain useful patterns/logic
- Will be removed in future cleanup phase
- No risk since routes are disabled

---

**Last Updated:** Phase-12 (v0.12.1)  
**Next Review:** Post-v1.0 cleanup phase
