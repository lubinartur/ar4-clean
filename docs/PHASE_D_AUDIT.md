# Phase D Audit Report: GoogleUI Sessions, Chat State, History & Settings

**Date:** 2025-01-XX  
**Scope:** Production-hardening of GoogleUI around sessions, chat state, history, and settings  
**Status:** Audit Complete - Ready for Patch Planning

---

## 1. Current Implementation Summary

### 1.1 Session ID Generation/Ownership

**Files:**
- `backend/app/static/googleui/src/services/air4Service.ts` (lines 295-331, 206-208)
- `backend/app/static/googleui/src/App.tsx` (lines 27-70)
- `backend/app/static/googleui/src/pages/Chat.tsx` (lines 59-101)

**What Works:**
- ✅ Backend owns session ID generation via `POST /sessions` (8-char hex from uuid)
- ✅ UI validates session IDs (`isValidBackendSessionId()`) - rejects timestamp-based legacy IDs
- ✅ UI creates sessions via `air4Service.createSession()` → backend POST
- ✅ Session IDs synced to URL (`?session=xxx`) with validation guards
- ✅ `localStorage.getItem('air4:lastSessionId')` stores last active session

**Gaps:**
- ⚠️ No automatic backend sync on app startup (only manual `refreshSessions()`)
- ⚠️ Duplicate session creation possible if user clicks "New Session" rapidly
- ⚠️ No session ownership validation (UI assumes backend session exists)

---

### 1.2 Session Persistence

**Files:**
- `backend/app/static/googleui/src/services/air4Service.ts` (lines 165-177, 378-380)
- `backend/app/static/googleui/src/components/Sidebar.tsx` (lines 46-54)

**What Works:**
- ✅ Sessions stored in `localStorage` as `air4_sessions` (JSON array of `ChatSession[]`)
- ✅ `saveSessions()` persists after create/delete/rename
- ✅ Backend persists messages in ChromaDB via memory manager (separate from UI)
- ✅ Sidebar polls `air4.getSessions()` on mount + manual refresh

**Gaps:**
- ⚠️ **No IndexedDB** - localStorage only (5-10MB limit, synchronous)
- ⚠️ **No backend sync for session list** - only individual session fetch via `getSessionById()`
- ⚠️ Stale localStorage can show deleted sessions until manual refresh
- ⚠️ No migration path if localStorage schema changes

---

### 1.3 Chat Message Persistence Per Session

**Files:**
- `backend/app/static/googleui/src/pages/Chat.tsx` (lines 59-101)
- `backend/app/static/googleui/src/services/air4Service.ts` (lines 210-281, 283-293)

**What Works:**
- ✅ Messages loaded from backend via `GET /sessions/:id` on session change
- ✅ Messages stored in `ChatSession.messages[]` in localStorage
- ✅ `upsertSession()` syncs backend response to localStorage
- ✅ Messages updated in real-time during streaming

**Gaps:**
- ⚠️ **No optimistic updates** - if backend fetch fails, UI shows empty messages
- ⚠️ **No message deduplication** - duplicate messages possible on rapid session switches
- ⚠️ **No pagination** - all messages loaded at once (could be slow for long sessions)
- ⚠️ Messages not persisted to localStorage until backend response (race condition on page close)

---

### 1.4 History/Sessions UI

**Files:**
- `backend/app/static/googleui/src/components/Sidebar.tsx` (lines 129-160, 264-354)
- `backend/app/static/googleui/src/pages/History.tsx` (lines 11-160)

**What Works:**
- ✅ Sidebar shows grouped sessions (Today, Yesterday, Previous 7/30 Days, Older)
- ✅ History page shows full list with search, rename, delete
- ✅ Collapsible groups with open/close state
- ✅ Active session highlighting
- ✅ Delete with confirmation + auto-select next session

**Gaps:**
- ⚠️ **No backend sync** - sidebar/history only read from localStorage
- ⚠️ **No rename persistence to backend** - only localStorage (backend may have different title)
- ⚠️ **No bulk operations** - can't delete/archive multiple sessions
- ⚠️ **No session export/import** - only `exportSession()` exists but not exposed in UI
- ⚠️ **No session search in backend** - only client-side filtering

---

### 1.5 Streaming Support (AbortController/Stop/Retry)

**Files:**
- `backend/app/static/googleui/src/pages/Chat.tsx` (lines 55, 293-295, 319-321, 434, 1018-1030)
- `backend/app/static/googleui/src/services/air4Service.ts` (lines 1009-1114)

**What Works:**
- ✅ `AbortController` used for streaming cancellation
- ✅ Stop button (Square icon) shown when `isThinking && abortControllerRef.current`
- ✅ `chatStream()` accepts `AbortSignal` parameter
- ✅ Race condition protection via `requestIdRef` (increments on each submit)
- ✅ AbortError handled gracefully (no error toast on user cancellation)

**Gaps:**
- ⚠️ **No retry mechanism** - if stream fails, user must manually resubmit
- ⚠️ **No resume** - interrupted streams can't be resumed
- ⚠️ **Smart scroll** exists but may not work well with long messages (scrolls on every token)
- ⚠️ **No streaming state persistence** - if page closes during stream, message lost

---

## 2. Gaps vs Phase D Goals

| Goal | Current State | Gap |
|------|---------------|-----|
| **Sessions consolidation** | Backend creates IDs, UI stores in localStorage | ⚠️ No automatic backend sync on startup |
| **Chat state machine** | Basic stop works, no retry | ❌ Missing: retry, resume, state persistence |
| **Local history sidebar** | Basic list works | ⚠️ Missing: backend sync, bulk ops, export |
| **Settings presets** | Individual settings exist | ❌ Missing: quick presets (short/normal/long + persona) |

---

## 3. Risks

### 3.1 Duplication
- **Risk:** Rapid "New Session" clicks can create duplicate sessions
- **Location:** `Sidebar.tsx:83-92`, `air4Service.ts:295-331`
- **Impact:** Medium - UI shows duplicates, backend may reject

### 3.2 Inconsistent State
- **Risk:** localStorage sessions can be stale (deleted on backend but still in UI)
- **Location:** `Sidebar.tsx:46-54` (no backend sync)
- **Impact:** High - user sees sessions that don't exist

### 3.3 Stale Storage Schema
- **Risk:** `ChatSession` type may change, breaking localStorage parsing
- **Location:** `air4Service.ts:165-177` (no versioning/migration)
- **Impact:** Medium - app may crash on load if schema mismatch

### 3.4 Race Conditions
- **Risk:** Multiple rapid session switches can cause message loading race
- **Location:** `Chat.tsx:59-101` (no request cancellation for session fetch)
- **Impact:** Low - messages may briefly show wrong session

### 3.5 Lost Messages
- **Risk:** Messages not persisted to localStorage until backend response
- **Location:** `Chat.tsx:280-524` (streaming updates state but not localStorage immediately)
- **Impact:** High - page close during stream = lost message

---

## 4. Proposed Phase D Patches

### Patch D1: Sessions Consolidation (if needed)

**Status:** ⚠️ **MAYBE NEEDED** - depends on whether backend sync is required

**Files to Change:**
- `backend/app/static/googleui/src/services/air4Service.ts`
- `backend/app/static/googleui/src/App.tsx`

**What to Add:**
- `refreshSessions()` method that calls `GET /sessions` (if backend supports it)
- Auto-sync on app startup (after initial load)
- Debounce session creation to prevent duplicates

**What to Remove:**
- Nothing (keep localStorage as cache)

**Why:** Ensure UI session list matches backend reality

**Minimal Diff Approach:**
- Add `refreshSessions()` that fetches from backend, merges with localStorage
- Call on app mount (after initial localStorage load)
- Add 500ms debounce to `createSession()`

---

### Patch D2: Chat State Machine (Stop/Retry/Smart Scroll)

**Status:** ✅ **NEEDED**

**Files to Change:**
- `backend/app/static/googleui/src/pages/Chat.tsx`
- `backend/app/static/googleui/src/services/air4Service.ts`

**What to Add:**
- Retry button (appears after stream error)
- Resume mechanism (store partial message in localStorage, resume on retry)
- Smart scroll throttling (only scroll if user near bottom)
- Streaming state persistence (save message to localStorage on each token)

**What to Remove:**
- Nothing

**Why:** Improve UX for interrupted streams and long conversations

**Minimal Diff Approach:**
- Add `retryRequestRef` to store last failed request
- Add retry button in error state (reuse `handleSubmit` with stored input)
- Throttle `scrollToBottom()` to 100ms intervals
- Add `useEffect` to persist messages to localStorage during streaming

---

### Patch D3: Local History Sidebar Improvements

**Status:** ⚠️ **OPTIONAL** - nice-to-have

**Files to Change:**
- `backend/app/static/googleui/src/components/Sidebar.tsx`
- `backend/app/static/googleui/src/pages/History.tsx`
- `backend/app/static/googleui/src/services/air4Service.ts`

**What to Add:**
- Backend sync on sidebar mount (if backend supports `GET /sessions`)
- Bulk delete (multi-select + delete)
- Export/import UI (expose existing `exportSession()`)
- Session search in backend (if backend supports it)

**What to Remove:**
- Nothing

**Why:** Better session management UX

**Minimal Diff Approach:**
- Add `refreshSessions()` call in Sidebar mount (if backend endpoint exists)
- Add checkbox selection state in History page
- Add "Export All" button that calls `exportSession()` for each
- Keep localStorage as primary source, backend as sync target

---

### Patch D4: Settings Presets (Short/Normal/Long + Persona)

**Status:** ✅ **NEEDED**

**Files to Change:**
- `backend/app/static/googleui/src/pages/Settings.tsx`
- `backend/app/static/googleui/src/hooks/useSettings.ts` (if needed)

**What to Add:**
- Preset buttons: "Short & Sharp", "Normal", "Detailed"
- Preset buttons: "Bro", "Strict", "Neutral" (persona)
- Preset applies: `outputDensity`, `responseTone`, `temperature`, `neuralPersonality`
- Visual indicator of active preset

**What to Remove:**
- Nothing

**Why:** Faster settings configuration for common use cases

**Minimal Diff Approach:**
- Add preset definitions (object mapping preset name → settings)
- Add preset buttons in "Session Presets" card
- On click, apply preset to `settings` via `setSettings()`
- Highlight active preset by comparing current settings to preset values

---

## 5. Implementation Order

1. **Patch D4** (Settings Presets) - Lowest risk, immediate UX improvement
2. **Patch D2** (Chat State Machine) - High impact, moderate risk
3. **Patch D1** (Sessions Consolidation) - Only if backend sync is required
4. **Patch D3** (History Improvements) - Optional, can be deferred

---

## 6. Files Involved Summary

**Core Files:**
- `backend/app/static/googleui/src/services/air4Service.ts` - Session management, localStorage
- `backend/app/static/googleui/src/pages/Chat.tsx` - Chat UI, streaming, state
- `backend/app/static/googleui/src/components/Sidebar.tsx` - Session list UI
- `backend/app/static/googleui/src/pages/History.tsx` - History page UI
- `backend/app/static/googleui/src/pages/Settings.tsx` - Settings UI
- `backend/app/static/googleui/src/App.tsx` - App-level session routing
- `backend/app/static/googleui/src/types.ts` - Type definitions

**Storage Keys:**
- `air4_sessions` - Session list (localStorage)
- `air4:lastSessionId` - Last active session (localStorage)
- `air4_config` - Global config (localStorage)
- `air4-core-settings-v1` - Settings (localStorage)

---

**End of Audit Report**
