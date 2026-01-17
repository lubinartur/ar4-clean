import React, { useEffect, useState, useRef } from "react";

type QBQuestion = {
  id: string;
  signal: string;
  domain: string;
  question: string;
  answers: string[]; // ["yes","no"] or ["low","mid","high"]
};

type QBStateResponse = {
  questions: QBQuestion[];
  snapshot?: any;
  score?: any;
  state?: any;
  constraints?: any;
};

const labelMap: Record<string, string> = { yes: "✓", no: "✕", low: "↓", mid: "•", high: "↑" };

function getSuggestLabels(thinkingMode: ThinkingMode): Record<string, string> {
  const labelsByMode: Record<ThinkingMode, Record<string, string>> = {
    structured: {
      continue: "Продолжить",
      capture: "Зафиксировать",
      go_deeper: "Пойти глубже",
    },
    analytical: {
      continue: "Дальше",
      capture: "Зафиксировать факт",
      go_deeper: "Уточнить",
    },
    wide: {
      continue: "Ок",
      capture: "Сохранить",
      go_deeper: "Расширить",
    },
    hard: {
      continue: "Дальше",
      capture: "Записать",
      go_deeper: "Копать",
    },
    exploratory: {
      continue: "Продолжим",
      capture: "Запомнить",
      go_deeper: "Исследовать",
    },
  };
  return labelsByMode[thinkingMode] || labelsByMode.structured;
}

type DepthMode = "silent" | "normal" | "deep" | "giga";
type ThinkingMode = "analytical" | "structured" | "wide" | "hard" | "exploratory";

export function QBPanel(props: {
  enabled: boolean;
  maxQuestions?: number;
  onAnswered?: (payload: any) => void;
  onSendMessage?: (message: string) => void;
  refreshTrigger?: number; // Trigger refresh when this value changes
  userTurnsCount?: number; // Number of user messages in session
}) {
  const { enabled, maxQuestions = 1, onAnswered, refreshTrigger, userTurnsCount = 0 } = props;

  const QB_KEY = "air4.qb_session_id";
  
  // PHASE L2.2: Manage qbSessionId from ONE source (localStorage)
  const [qbSessionId, setQbSessionId] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [data, setData] = useState<QBStateResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [queue, setQueue] = useState<QBQuestion[]>([]);
  const [insightText, setInsightText] = useState<string | null>(null);
  const [suggest, setSuggest] = useState<string[]>([]);
  const [mode, setMode] = useState<"idle" | "question" | "insight">("idle");
  const [depthMode, setDepthMode] = useState<DepthMode>("normal");
  const [thinkingMode, setThinkingMode] = useState<ThinkingMode>("structured");
  
  // Preserve last valid QB state during AIR4 generation using useRef (stable across re-renders)
  const lastValidQBRef = useRef<{
    queue: QBQuestion[];
    mode: "idle" | "question" | "insight";
  }>({ queue: [], mode: "idle" });
  
  // Track consumed questions (answered questions that should be hidden)
  const [consumedId, setConsumedId] = useState<string | null>(null);
  
  // Anti-repeat filter: track seen and answered question IDs
  const [seenIds, setSeenIds] = useState<Set<string>>(new Set());
  const [answeredIds, setAnsweredIds] = useState<Set<string>>(new Set());
  
  // Cooldown after answering to prevent immediate next question
  const [qbCooldownUntil, setQbCooldownUntil] = useState<number>(0);
  
  // Rate limiting: track user messages since last QB question
  const N = 3; // Show QB question every N user messages
  const [userSinceQB, setUserSinceQB] = useState<number>(0);
  // Track if any question has been shown in this session (to allow first question immediately)
  const [qbHasShownAny, setQbHasShownAny] = useState<boolean>(false);
  // Track last shown question ID to keep it visible (sticky) even if gate blocks new questions
  const lastShownQuestionIdRef = useRef<string | null>(null);

  // PHASE L2.2: Helper to apply insight from response
  function applyInsight(resp: any): boolean {
    if (resp?.insight) {
      setInsightText(resp.insight);
      setSuggest(Array.isArray(resp.suggest) ? resp.suggest : ["continue", "capture", "go_deeper"]);
      setMode("insight");
      return true;
    }
    setInsightText(null);
    setSuggest([]);
    return false;
  }

  // Get base URL - try to use window.location.origin or fallback
  const getBaseUrl = (): string => {
    if (typeof window !== "undefined") {
      return window.location.origin;
    }
    return "";
  };

  // Use last valid queue from ref (stable across re-renders) - always prefer ref if it has questions
  // This ensures QB question stays visible during AIR4 generation (re-renders)
  const effectiveQueue = (lastValidQBRef.current.queue.length > 0) 
    ? lastValidQBRef.current.queue 
    : queue;
  const effectiveMode = (lastValidQBRef.current.queue.length > 0 && lastValidQBRef.current.mode !== "idle")
    ? lastValidQBRef.current.mode
    : mode;
  
  // Filter queue to exclude answered questions only
  const filteredQueue = effectiveQueue.filter(q => 
    !answeredIds.has(q.id)
  );
  
  // Select first question from filtered queue
  const visible = filteredQueue.slice(0, 1); // PHASE L2.2: Show only one question at a time
  
  // Determine if there's a displayed question (for mutually exclusive rendering)
  const displayedQuestion = visible.length > 0 ? visible[0] : null;
  // Exclude consumed questions and respect cooldown
  const isCooldownActive = Date.now() < qbCooldownUntil;
  // Rate limiting: only apply gate if at least one question was already shown
  // First question should appear immediately, subsequent questions follow N=3 rule
  // But keep already shown question visible (sticky) even if gate would block new question
  const isStickyQuestion = displayedQuestion?.id === lastShownQuestionIdRef.current;
  const canShowQuestion = !qbHasShownAny || userSinceQB >= N || isStickyQuestion;
  const hasQuestion = Boolean(
    !isCooldownActive &&
    canShowQuestion &&
    displayedQuestion && 
    displayedQuestion.question?.trim().length &&
    displayedQuestion.id !== consumedId
  );
  
  // NOTE: seenIds removed - only answeredIds filter is used to prevent repeats
  
  // Mark that question was shown and reset counter when new question is displayed
  useEffect(() => {
    if (hasQuestion && displayedQuestion?.id) {
      // Track if this is a new question (different from last shown)
      const isNewQuestion = displayedQuestion.id !== lastShownQuestionIdRef.current;
      if (isNewQuestion) {
        setQbHasShownAny(true);
        setUserSinceQB(0);
        lastShownQuestionIdRef.current = displayedQuestion.id;
      }
    }
  }, [hasQuestion, displayedQuestion?.id]);

  function qbUrl(path: string): string {
    const sid = qbSessionId || "";
    const mode = localStorage.getItem("air4.depth_mode") || "normal";
    const tmode = localStorage.getItem("air4.thinking_mode") || "structured";
    const qs = new URLSearchParams();
    if (sid) qs.set("session_id", sid);
    qs.set("depth_mode", mode);
    qs.set("thinking_mode", tmode);
    return `${path}?${qs.toString()}`;
  }

  // PHASE L2.2: Ensure qbSessionId is initialized from localStorage or create new
  async function ensureQbSession(): Promise<string> {
    // If already set in state, use it
    if (qbSessionId) return qbSessionId;
    
    // Try to read from localStorage
    const existing = localStorage.getItem(QB_KEY);
    if (existing) {
      setQbSessionId(existing);
      return existing;
    }
    
    // Create new session
    const res = await fetch("/qb/sessions", { method: "POST" });
    const json = await res.json();
    const sid = json?.session_id;
    if (!sid) throw new Error("QB session create failed");
    localStorage.setItem(QB_KEY, sid);
    setQbSessionId(sid);
    return sid;
  }

  // PHASE L2.2: Refresh QB state (used after actions)
  async function refreshQBState() {
    if (!qbSessionId || !enabled) return;
    await loadState();
  }

  async function testInsight() {
    if (!qbSessionId) {
      console.warn("[QBPanel] No qbSessionId, test insight skipped");
      return;
    }

    try {
      const depthMode = localStorage.getItem("air4.depth_mode") || "normal";
      const thinkingMode = localStorage.getItem("air4.thinking_mode") || "structured";
      const url = `/qb/state?session_id=${encodeURIComponent(qbSessionId)}&depth_mode=${encodeURIComponent(depthMode)}&thinking_mode=${encodeURIComponent(thinkingMode)}&force_insight=1`;
      
      const res = await fetch(url);

      if (!res.ok) {
        const t = await res.text().catch(() => "");
        console.warn("[QB] test insight failed", res.status, t);
        return;
      }

      const json = await res.json();
      
      // Apply insight and update state
      if (!applyInsight(json)) {
        // If no insight, update mode based on questions
        if (json?.questions?.length) {
          setMode("question");
          setQueue(json.questions ?? []);
        } else {
          setMode("idle");
        }
      } else {
        setQueue(json.questions ?? []);
      }
      
      setData(json);
      
      console.debug("[QBPanel] Test insight completed", { insight: json?.insight, suggest: json?.suggest });
    } catch (e: any) {
      console.error("[QBPanel] Test insight failed", e);
    }
  }

  // PHASE L2.2: Send action to /qb/action endpoint
  type QBAction = "continue" | "capture" | "go_deeper";

  async function sendAction(action: QBAction) {
    if (!qbSessionId) return;

    try {
      const baseUrl = getBaseUrl();
      const res = await fetch(`${baseUrl}/qb/action`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          session_id: qbSessionId,
          action: action,
        }),
      });

      if (!res.ok) {
        const t = await res.text().catch(() => "");
        console.warn("[QB] action failed", res.status, t);
        return;
      }

      const json = await res.json();
      
      // PHASE L2.4: Update state immediately with response
      setData(json);
      
      // PHASE L2.4: Handle questions immediately
      const actionQuestions = Array.isArray(json?.questions) ? json.questions : [];
      setQueue(actionQuestions);
      
      // PHASE L2.4: Handle mode based on action response
      // For go_deeper: close insight, show question immediately (if present)
      // For continue: close insight, go idle
      // For capture: close insight, go idle
      let actionMode: "idle" | "question" | "insight" = "idle";
      if (action === "go_deeper" && actionQuestions.length > 0) {
        // go_deeper: close insight, show question immediately
        setInsightText(null);
        setSuggest([]);
        actionMode = "question";
      } else {
        // continue, capture, or no questions: close insight, go idle
        setInsightText(null);
        setSuggest([]);
        if (actionQuestions.length > 0) {
          actionMode = "question";
        } else {
          actionMode = "idle";
        }
      }
      setMode(actionMode);
      
      // Preserve last valid state in ref (only if we have questions)
      if (actionQuestions.length > 0 && actionMode === "question") {
        lastValidQBRef.current = { queue: actionQuestions, mode: "question" };
        // Reset consumedId when new question arrives (different ID)
        const actionQuestionId = actionQuestions[0]?.id;
        if (actionQuestionId && actionQuestionId !== consumedId) {
          setConsumedId(null);
        }
      }
      
      console.debug("[QBPanel] Action completed", { action, calibration: json?.calibration, questions: json?.questions?.length });
    } catch (e: any) {
      console.error("[QBPanel] Action failed", e);
    }
  }

  async function handleSuggestClick(action: string) {
    if (!insightText) return;

    // PHASE L2.2: All actions go to /qb/action
    if (action === "continue" || action === "capture" || action === "go_deeper") {
      await sendAction(action as QBAction);
    }
  }

  async function loadState() {
    if (!enabled) return;
    
    // PHASE L2.2: Ensure session exists before loading
    const sid = await ensureQbSession();
    if (!sid) return;
    
    setLoading(true);
    setError(null);
    try {
      const res = await fetch(qbUrl("/qb/state"));
      const text = await res.text();
      let json: any = null;
      try {
        json = JSON.parse(text);
      } catch {
        json = null;
      }
      
      // Auto-recover from session_not_found
      if (json?.error === "session_not_found") {
        localStorage.removeItem(QB_KEY);
        setQbSessionId(null);
        // Reset seen/answered IDs for new session
        setSeenIds(new Set());
        setAnsweredIds(new Set());
        // Reset rate limiting counter and flag for new session
        setUserSinceQB(0);
        setQbHasShownAny(false);
        lastShownQuestionIdRef.current = null;
        // создать новую сессию
        const newSid = await ensureQbSession();
        if (newSid) {
          // обновить UI: setData(null) и затем повторно дернуть state с newSid и depth_mode
          setData(null);
          const retryRes = await fetch(qbUrl("/qb/state"));
          const retryText = await retryRes.text();
          let retryJson: any = null;
          try {
            retryJson = JSON.parse(retryText);
          } catch {
            retryJson = null;
          }
          if (!retryRes.ok) throw new Error(`QB state ${retryRes.status}: ${retryText}`);
          setData(retryJson);
          const retryQuestions = retryJson.questions ?? [];
          setQueue(retryQuestions);
          
          // PHASE L2.2: Apply insight if present
          let retryMode: "idle" | "question" | "insight" = "idle";
          if (!applyInsight(retryJson)) {
            if (retryQuestions.length) {
              retryMode = "question";
            } else {
              retryMode = "idle";
            }
          } else {
            retryMode = "insight";
          }
          setMode(retryMode);
          
          // Preserve last valid state in ref (only if we have questions)
          if (retryQuestions.length > 0 && retryMode === "question") {
            lastValidQBRef.current = { queue: retryQuestions, mode: "question" };
            // Reset consumedId when new question arrives
            const retryQuestionId = retryQuestions[0]?.id;
            if (retryQuestionId && retryQuestionId !== consumedId) {
              setConsumedId(null);
            }
          }
        }
        return;
      }
      
      if (!res.ok) throw new Error(`QB state ${res.status}: ${text}`);
      console.debug("[QBPanel] state ok", json);
      setData(json);
      const newQuestions = json.questions ?? [];
      setQueue(newQuestions);
      
      // PHASE L2.2: Apply insight if present, otherwise set mode based on questions
      let newMode: "idle" | "question" | "insight" = "idle";
      if (!applyInsight(json)) {
        if (newQuestions.length) {
          newMode = "question";
        } else {
          newMode = "idle";
        }
      } else {
        newMode = "insight";
      }
      setMode(newMode);
      
      // Preserve last valid state in ref (only if we have questions) - stable across re-renders
      if (newQuestions.length > 0 && newMode === "question") {
        lastValidQBRef.current = { queue: newQuestions, mode: "question" };
        // Reset consumedId when new question arrives (different ID)
        const newQuestionId = newQuestions[0]?.id;
        if (newQuestionId && newQuestionId !== consumedId) {
          setConsumedId(null);
        }
      } else if (newQuestions.length === 0) {
        // No questions - reset consumedId
        setConsumedId(null);
      }
    } catch (e: any) {
      setError(String(e?.message || e));
    } finally {
      setLoading(false);
    }
  }

  async function answer(signal: string, answer: string) {
    if (!enabled || !qbSessionId || loading) return;
    
    // Get current question ID before optimistic update
    const currentQuestion = visible.length > 0 ? visible[0] : null;
    const questionId = currentQuestion?.id;
    
    // Mark question as answered and consumed immediately (optimistic UI)
    if (questionId) {
      setAnsweredIds(prev => {
        const next = new Set(prev);
        next.add(questionId);
        return next;
      });
      setConsumedId(questionId);
    }
    
    // Start cooldown to prevent immediate next question
    setQbCooldownUntil(Date.now() + 2000);
    
    setLoading(true);
    setError(null);
    
    // Optimistic update: remove first question from queue immediately
    // But DON'T update ref - keep last valid question visible during loading
    setQueue(prev => prev.length > 0 ? prev.slice(1) : []);
    
    try {
      const depthMode = localStorage.getItem("air4.depth_mode") || "normal";
      const thinkingMode = localStorage.getItem("air4.thinking_mode") || "structured";
      const res = await fetch(qbUrl("/qb/answer"), {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ 
          session_id: qbSessionId, 
          signal, 
          answer,
          depth_mode: depthMode,
          thinking_mode: thinkingMode,
        }),
      });
      const json = await res.json();
      if (!res.ok) throw new Error(json?.detail || "QB answer error");
      
      // Update data for score/state, and replace queue with new questions
      setData(json);
      const newQuestions = json.questions ?? [];
      setQueue(newQuestions);
      
      // PHASE L2.2: Apply insight if present, otherwise set mode based on questions
      let newMode: "idle" | "question" | "insight" = "idle";
      if (!applyInsight(json)) {
        if (newQuestions.length) {
          newMode = "question";
        } else {
          newMode = "idle";
        }
      } else {
        newMode = "insight";
      }
      setMode(newMode);
      
      // Preserve last valid state in ref (only if we have questions) - stable across re-renders
      if (newQuestions.length > 0 && newMode === "question") {
        lastValidQBRef.current = { queue: newQuestions, mode: "question" };
        // Reset consumedId when new question arrives (different ID)
        const newQuestionId = newQuestions[0]?.id;
        if (newQuestionId && newQuestionId !== consumedId) {
          setConsumedId(null);
        }
      } else {
        // No new questions - keep consumedId to hide current question
        setConsumedId(null); // Reset when no questions
      }
      
      onAnswered?.(json);
    } catch (e: any) {
      setError(String(e?.message || e));
      // On error, reload state to restore queue
      loadState();
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    // PHASE L2.2: Initialize qbSessionId from localStorage on mount
    const existing = localStorage.getItem(QB_KEY);
    if (existing) {
      setQbSessionId(existing);
    } else {
      // Create new session on mount if missing
      ensureQbSession().catch((e) => {
        console.error("[QBPanel] Failed to ensure QB session", e);
      });
    }
    
    // Load depth mode from localStorage on mount
    const saved = localStorage.getItem("air4.depth_mode") || "normal";
    if (["silent", "normal", "deep", "giga"].includes(saved)) {
      setDepthMode(saved as DepthMode);
    }
    
    // Load thinking mode from localStorage on mount
    const savedThinking = localStorage.getItem("air4.thinking_mode") || "structured";
    if (["analytical", "structured", "wide", "hard", "exploratory"].includes(savedThinking)) {
      setThinkingMode(savedThinking as ThinkingMode);
    } else {
      // If invalid or missing, set default and save
      setThinkingMode("structured");
      localStorage.setItem("air4.thinking_mode", "structured");
    }
  }, []);

  useEffect(() => {
    // PHASE L2.2: Load state when qbSessionId is available
    // Only load if user has sent at least one message (userTurnsCount >= 1)
    if (qbSessionId && enabled && userTurnsCount >= 1) {
      loadState();
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [qbSessionId, enabled, userTurnsCount]);

  // Track user messages for rate limiting
  useEffect(() => {
    if (refreshTrigger !== undefined && refreshTrigger > 0 && userTurnsCount >= 1) {
      // Increment counter when user sends a message
      setUserSinceQB(prev => prev + 1);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [refreshTrigger]);

  // Auto-refresh QB after user message (triggered by refreshTrigger prop)
  // Only refresh if user has sent at least one message (userTurnsCount >= 1)
  useEffect(() => {
    if (refreshTrigger !== undefined && refreshTrigger > 0 && qbSessionId && enabled && userTurnsCount >= 1) {
      // Reset cooldown when user sends a message
      setQbCooldownUntil(0);
      // Small delay to ensure backend has processed the message
      const timer = setTimeout(() => {
        loadState();
      }, 500);
      return () => clearTimeout(timer);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [refreshTrigger, userTurnsCount]);

  function handleDepthModeChange(mode: DepthMode) {
    localStorage.setItem("air4.depth_mode", mode);
    setDepthMode(mode);
    // Reset cooldown when Depth changes
    setQbCooldownUntil(0);
    // Override rate limiting: allow immediate question update for manual Depth change
    setUserSinceQB(0);
    // Optionally reload state
    if (qbSessionId && enabled) {
      loadState();
    }
  }

  function handleThinkingModeChange(mode: ThinkingMode) {
    localStorage.setItem("air4.thinking_mode", mode);
    setThinkingMode(mode);
    // Reset cooldown when Think changes
    setQbCooldownUntil(0);
    // Override rate limiting: allow immediate question update for manual Think change
    setUserSinceQB(0);
    // Optionally reload state
    if (qbSessionId && enabled) {
      loadState();
    }
  }

  if (!enabled) return null;
  if (!qbSessionId) return null;

  // Optional: hide panel in execution mode if present
  const qbMode = data?.state?.mode;
  if (qbMode === "execution") return null;

  return (
    <div style={{ padding: "8px 12px", borderBottom: "1px solid rgba(255,255,255,0.08)" }}>
      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", gap: 8 }}>
        <div style={{ display: "flex", alignItems: "center", gap: 8, flex: 1, minWidth: 0 }}>
          <div style={{ fontSize: 11, opacity: 0.6, whiteSpace: "nowrap" }}>QB</div>
          <div style={{ display: "flex", gap: 3, alignItems: "center", flexWrap: "wrap" }}>
            <span style={{ fontSize: 9, opacity: 0.5 }}>Depth:</span>
            {(["silent", "normal", "deep", "giga"] as DepthMode[]).map((mode) => (
              <button
                key={mode}
                onClick={() => handleDepthModeChange(mode)}
                style={{
                  padding: "1px 4px",
                  fontSize: 9,
                  borderRadius: 3,
                  border: "1px solid rgba(255,255,255,0.12)",
                  background: depthMode === mode ? "rgba(255,255,255,0.15)" : "rgba(255,255,255,0.04)",
                  cursor: "pointer",
                  opacity: depthMode === mode ? 1 : 0.5,
                  textTransform: "capitalize",
                }}
              >
                {mode}
              </button>
            ))}
            <span style={{ fontSize: 9, opacity: 0.5, marginLeft: 4 }}>Think:</span>
            {(["analytical", "structured", "wide", "hard", "exploratory"] as ThinkingMode[]).map((mode) => (
              <button
                key={mode}
                onClick={() => handleThinkingModeChange(mode)}
                style={{
                  padding: "1px 4px",
                  fontSize: 9,
                  borderRadius: 3,
                  border: "1px solid rgba(255,255,255,0.12)",
                  background: thinkingMode === mode ? "rgba(255,255,255,0.15)" : "rgba(255,255,255,0.04)",
                  cursor: "pointer",
                  opacity: thinkingMode === mode ? 1 : 0.5,
                  textTransform: "capitalize",
                }}
              >
                {mode}
              </button>
            ))}
          </div>
        </div>
        <div style={{ display: "flex", alignItems: "center", gap: 6, flexShrink: 0 }}>
          {data?.score?.total != null && (
            <div style={{ fontSize: 10, opacity: 0.5 }}>
              {data.score.total}
            </div>
          )}
          {/* Debug buttons - only when debug=1 in URL */}
          {(() => {
            const debugUI = new URLSearchParams(window.location.search).get("debug") === "1";
            return debugUI && (
              <>
                <button
                  onClick={testInsight}
                  style={{
                    padding: "2px 6px",
                    fontSize: 9,
                    borderRadius: 3,
                    border: "1px solid rgba(255,255,255,0.2)",
                    background: "rgba(255,255,255,0.1)",
                    cursor: "pointer",
                    opacity: 0.5,
                  }}
                >
                  Test
                </button>
                <button
                  onClick={testInsight}
                  style={{
                    padding: "2px 6px",
                    fontSize: 9,
                    borderRadius: 3,
                    border: "1px solid rgba(255,255,255,0.2)",
                    background: "rgba(255,255,255,0.1)",
                    cursor: "pointer",
                    opacity: 0.5,
                  }}
                >
                  Force
                </button>
              </>
            );
          })()}
        </div>
      </div>

      {error && (
        <div style={{ marginTop: 4, fontSize: 10, color: "tomato" }}>
          {error}
        </div>
      )}

      {/* Mutually exclusive rendering: question OR loading OR empty-state */}
      {hasQuestion && effectiveMode === "question" && userTurnsCount >= 1 ? (
        // Render question UI only
        <div style={{ marginTop: 4 }}>
          {visible.map((q) => (
            <div key={`q:${q.id}`} style={{ display: "flex", alignItems: "flex-start", gap: 8 }}>
              <div style={{ flex: 1, minWidth: 0 }}>
                <div style={{ 
                  fontSize: 12, 
                  lineHeight: 1.4,
                  display: "-webkit-box",
                  WebkitLineClamp: 2,
                  WebkitBoxOrient: "vertical",
                  overflow: "hidden",
                  textOverflow: "ellipsis"
                }}>
                  {q.question}
                </div>
                <div style={{ fontSize: 9, opacity: 0.4, marginTop: 2 }}>
                  {q.domain} • {q.signal}
                </div>
              </div>
              <div style={{ display: "flex", gap: 4, flexShrink: 0, alignItems: "center" }}>
                {(q.answers || []).map((a) => {
                  // PHASE L2.2: Show ✅/❌ for yes/no instead of text
                  const displayLabel = a === "yes" ? "✅" : a === "no" ? "❌" : (labelMap[a] ?? a);
                  return (
                    <button
                      key={`q:${q.id}:a:${a}`}
                      onClick={() => answer(q.signal, a)}
                      disabled={loading}
                      style={{
                        padding: "4px 8px",
                        fontSize: 14,
                        borderRadius: 6,
                        border: "1px solid rgba(255,255,255,0.12)",
                        background: "rgba(255,255,255,0.06)",
                        cursor: "pointer",
                        minWidth: 32,
                        display: "flex",
                        alignItems: "center",
                        justifyContent: "center",
                      }}
                    >
                      {displayLabel}
                    </button>
                  );
                })}
              </div>
            </div>
          ))}
        </div>
      ) : loading && !data ? (
        // Render loading state only
        <div style={{ marginTop: 4, fontSize: 10, opacity: 0.5 }}>Loading…</div>
      ) : userTurnsCount === 0 ? (
        // Render placeholder for new session
        <div style={{ marginTop: 4, fontSize: 11, opacity: 0.5, fontStyle: "italic" }}>
          QB ждёт первого сообщения…
        </div>
      ) : mode === "insight" && userTurnsCount >= 1 ? (
        // Render insight UI
        <>
          {insightText && (
            <div style={{ marginTop: 4, fontSize: 11, opacity: 0.7, fontStyle: "italic", lineHeight: 1.4 }}>
              {insightText}
            </div>
          )}
          {suggest.length > 0 && (
            <div style={{ marginTop: 6, display: "flex", gap: 6, flexWrap: "wrap" }}>
              {suggest.map((action) => {
                // Map action to RU labels
                const actionLabels: Record<string, string> = {
                  continue: "Дальше",
                  capture: "Записать",
                  go_deeper: "Копать",
                };
                return (
                  <button
                    key={`action:${action}`}
                    onClick={() => handleSuggestClick(action)}
                    style={{
                      padding: "4px 8px",
                      fontSize: 10,
                      borderRadius: 6,
                      border: "1px solid rgba(255,255,255,0.12)",
                      background: "rgba(255,255,255,0.06)",
                      cursor: "pointer",
                      opacity: 0.8,
                    }}
                  >
                    {actionLabels[action] || action}
                  </button>
                );
              })}
            </div>
          )}
        </>
      ) : (
        // Render empty-state (no questions and not loading)
        <div style={{ marginTop: 4, fontSize: 10, opacity: 0.5 }}>Пока без вопросов</div>
      )}

    </div>
  );
}
