import React, { useEffect, useState } from "react";

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
}) {
  const { enabled, maxQuestions = 1, onAnswered } = props;

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

  const visible = queue.slice(0, 1); // PHASE L2.2: Show only one question at a time

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
      if (Array.isArray(json?.questions)) {
        setQueue(json.questions);
      } else {
        setQueue([]);
      }
      
      // PHASE L2.4: Handle mode based on action response
      // For go_deeper: close insight, show question immediately (if present)
      // For continue: close insight, go idle
      // For capture: close insight, go idle
      if (action === "go_deeper" && json?.questions?.length > 0) {
        // go_deeper: close insight, show question immediately
        setInsightText(null);
        setSuggest([]);
        setMode("question");
      } else {
        // continue, capture, or no questions: close insight, go idle
        setInsightText(null);
        setSuggest([]);
        if (json?.questions?.length > 0) {
          setMode("question");
        } else {
          setMode("idle");
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
          setQueue(retryJson.questions ?? []);
          
          // PHASE L2.2: Apply insight if present
          if (!applyInsight(retryJson)) {
            if (retryJson?.questions?.length) {
              setMode("question");
            } else {
              setMode("idle");
            }
          }
        }
        return;
      }
      
      if (!res.ok) throw new Error(`QB state ${res.status}: ${text}`);
      console.debug("[QBPanel] state ok", json);
      setData(json);
      setQueue(json.questions ?? []);
      
      // PHASE L2.2: Apply insight if present, otherwise set mode based on questions
      if (!applyInsight(json)) {
        if (json?.questions?.length) {
          setMode("question");
        } else {
          setMode("idle");
        }
      }
    } catch (e: any) {
      setError(String(e?.message || e));
    } finally {
      setLoading(false);
    }
  }

  async function answer(signal: string, answer: string) {
    if (!enabled || !qbSessionId || loading) return;
    setLoading(true);
    setError(null);
    
    // Optimistic update: remove first question from queue immediately
    setQueue(prev => prev.slice(1));
    
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
      
      // PHASE L2.2: Apply insight if present, otherwise set mode based on questions
      if (!applyInsight(json)) {
        if (json?.questions?.length) {
          setMode("question");
        } else {
          setMode("idle");
        }
      }
      
      // Update data for score/state, and replace queue with new questions
      setData(json);
      setQueue(json.questions ?? []);
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
    if (qbSessionId && enabled) {
      loadState();
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [qbSessionId, enabled]);

  function handleDepthModeChange(mode: DepthMode) {
    localStorage.setItem("air4.depth_mode", mode);
    setDepthMode(mode);
    // Optionally reload state
    if (qbSessionId && enabled) {
      loadState();
    }
  }

  function handleThinkingModeChange(mode: ThinkingMode) {
    localStorage.setItem("air4.thinking_mode", mode);
    setThinkingMode(mode);
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
    <div style={{ padding: 12, borderBottom: "1px solid rgba(255,255,255,0.08)" }}>
      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", gap: 12 }}>
        <div style={{ display: "flex", flexDirection: "column", gap: 2 }}>
          <div style={{ fontSize: 12, opacity: 0.7 }}>QB</div>
          {/* PHASE L2.2: Display qbSessionId for debugging */}
          {qbSessionId && (
            <div style={{ fontSize: 10, opacity: 0.5, fontFamily: "monospace" }}>
              session: {qbSessionId}
            </div>
          )}
        </div>
        <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
          <div style={{ fontSize: 12, opacity: 0.7 }}>
            {data?.score?.total != null ? `Score: ${data.score.total}` : ""}
          </div>
          {import.meta.env.DEV && (
            <>
              <button
                onClick={testInsight}
                style={{
                  padding: "4px 8px",
                  fontSize: 11,
                  borderRadius: 4,
                  border: "1px solid rgba(255,255,255,0.2)",
                  background: "rgba(255,255,255,0.1)",
                  cursor: "pointer",
                  opacity: 0.7,
                }}
              >
                Test Insight
              </button>
              <button
                onClick={testInsight}
                style={{
                  padding: "4px 8px",
                  fontSize: 11,
                  borderRadius: 4,
                  border: "1px solid rgba(255,255,255,0.2)",
                  background: "rgba(255,255,255,0.1)",
                  cursor: "pointer",
                  opacity: 0.7,
                }}
              >
                Force Insight
              </button>
            </>
          )}
        </div>
      </div>

      <div style={{ marginTop: 8, display: "flex", gap: 4, alignItems: "center" }}>
        <span style={{ fontSize: 11, opacity: 0.6, marginRight: 4 }}>Depth:</span>
        {(["silent", "normal", "deep", "giga"] as DepthMode[]).map((mode) => (
          <button
            key={mode}
            onClick={() => handleDepthModeChange(mode)}
            style={{
              padding: "2px 6px",
              fontSize: 10,
              borderRadius: 4,
              border: "1px solid rgba(255,255,255,0.12)",
              background: depthMode === mode ? "rgba(255,255,255,0.15)" : "rgba(255,255,255,0.04)",
              cursor: "pointer",
              opacity: depthMode === mode ? 1 : 0.6,
              textTransform: "capitalize",
            }}
          >
            {mode}
          </button>
        ))}
      </div>

      <div style={{ marginTop: 8, display: "flex", gap: 4, alignItems: "center" }}>
        <span style={{ fontSize: 11, opacity: 0.6, marginRight: 4 }}>Think:</span>
        {(["analytical", "structured", "wide", "hard", "exploratory"] as ThinkingMode[]).map((mode) => (
          <button
            key={mode}
            onClick={() => handleThinkingModeChange(mode)}
            style={{
              padding: "2px 6px",
              fontSize: 10,
              borderRadius: 4,
              border: "1px solid rgba(255,255,255,0.12)",
              background: thinkingMode === mode ? "rgba(255,255,255,0.15)" : "rgba(255,255,255,0.04)",
              cursor: "pointer",
              opacity: thinkingMode === mode ? 1 : 0.6,
              textTransform: "capitalize",
            }}
          >
            {mode}
          </button>
        ))}
      </div>

      {error && (
        <div style={{ marginTop: 8, fontSize: 12, color: "tomato" }}>
          {error}
        </div>
      )}

      {loading && !data && (
        <div style={{ marginTop: 8, fontSize: 12, opacity: 0.7 }}>Loading…</div>
      )}

      {/* PHASE L2.2: Mode-based rendering */}
      {mode === "insight" && (
        <>
          {insightText && (
            <div style={{ marginTop: 12, fontSize: 12, opacity: 0.8, fontStyle: "italic" }}>
              {insightText}
            </div>
          )}
          {suggest.length > 0 && (
            <div style={{ marginTop: 10, display: "flex", gap: 8, flexWrap: "wrap" }}>
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
                      padding: "6px 12px",
                      fontSize: 12,
                      borderRadius: 8,
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
      )}

      {mode === "question" && visible.length > 0 && (
        <div style={{ marginTop: 10, display: "flex", flexDirection: "column", gap: 8 }}>
          {visible.map((q) => (
            <div key={`q:${q.id}`} style={{ display: "flex", flexDirection: "column", gap: 8 }}>
              <div style={{ fontSize: 14 }}>{q.question}</div>
              <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
                {(q.answers || []).map((a) => {
                  // PHASE L2.2: Show ✅/❌ for yes/no instead of text
                  const displayLabel = a === "yes" ? "✅" : a === "no" ? "❌" : (labelMap[a] ?? a);
                  return (
                    <button
                      key={`q:${q.id}:a:${a}`}
                      onClick={() => answer(q.signal, a)}
                      disabled={loading}
                      style={{
                        padding: "6px 10px",
                        borderRadius: 10,
                        border: "1px solid rgba(255,255,255,0.12)",
                        background: "rgba(255,255,255,0.06)",
                        cursor: "pointer",
                      }}
                    >
                      {displayLabel}
                    </button>
                  );
                })}
              </div>
              <div style={{ fontSize: 11, opacity: 0.6 }}>
                {q.domain} • {q.signal}
              </div>
            </div>
          ))}
        </div>
      )}

      {mode === "idle" && data && !loading && !error && (
        <div style={{ marginTop: 8, fontSize: 12, opacity: 0.7 }}>No questions right now.</div>
      )}
    </div>
  );
}
