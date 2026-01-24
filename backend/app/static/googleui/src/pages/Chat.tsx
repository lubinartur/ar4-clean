
import React, { useState, useEffect, useRef, useCallback, useMemo } from "react";
import { useSettings } from "../hooks/useSettings";
import { useAir4 } from '../contexts/Air4Context';
import { Message, MemoryItem, RouterDecision, SystemStats, ResponseStyle, ModelName, ModelMode, ContextUsed } from '../types';
import { Send, Mic, Paperclip, BrainCircuit, Cpu, Sparkles, Activity, Database, Circle, ChevronDown, Check, Star, Copy, ClipboardCheck, Square, Pin, PinOff, Eye, EyeOff, RotateCw } from 'lucide-react';
import { QBPanel } from '../components/qb/QBPanel';

interface ChatProps {
    sessionId: string | null;
    initialQuery?: string;
    clearInitialQuery?: () => void;
    onSessionChange?: (id: string) => void;
    selectedConversationId?: string | null;
    onSelectConversation?: (conversationId: string) => void;
    forceReloadTick?: number;
    userSelectTick?: number;
    onOpenSessionReady?: (openSession: (sid: string) => Promise<void>) => void;
    historyLoaded?: boolean;
    sessionOpenTick?: number;
}

// Helper: удаляет поля со значением undefined/null из объекта
function clean<T extends Record<string, any>>(obj: T): Partial<T> {
  const result: Partial<T> = {};
  for (const [key, value] of Object.entries(obj)) {
    if (value !== undefined && value !== null) {
      result[key as keyof T] = value;
    }
  }
  return result;
}

// Helper: hash function for generating stable keys
const hash = (s: string): string => {
  let h = 0;
  for (let i = 0; i < s.length; i++) {
    h = (h * 31 + s.charCodeAt(i)) | 0;
  }
  return String(Math.abs(h));
};


const Chat: React.FC<ChatProps> = ({ sessionId, initialQuery, clearInitialQuery, onSessionChange, selectedConversationId, onSelectConversation, forceReloadTick = 0, userSelectTick = 0, onOpenSessionReady, historyLoaded = false, sessionOpenTick = 0 }) => {
  console.debug('[CHAT MOUNT]', window.location.href);
  const { settings, setSettings } = useSettings();
  const air4 = useAir4();

  const [messages, setMessages] = useState<Message[]>([]);
  const [input, setInput] = useState('');
  const [isThinking, setIsThinking] = useState(false);
  const [conversationId, setConversationId] = useState<string | null>(null);
  const [routerState, setRouterState] = useState<RouterDecision | null>(null);
  const [stats, setStats] = useState<SystemStats | null>(null);
  const [lastStatsTime, setLastStatsTime] = useState<number>(Date.now());
  const [timeAgo, setTimeAgo] = useState(0);
  const [responseStyle, setResponseStyle] = useState<ResponseStyle>(air4.getResponseStyle());
  const [showStyleMenu, setShowStyleMenu] = useState(false);
  const [modelMode, setModelMode] = useState<ModelMode>(settings.modelMode || 'auto');
  const [showModelModeMenu, setShowModelModeMenu] = useState(false);
  const modelModeMenuRef = useRef<HTMLDivElement>(null);
  // C2.0: RAG toggle state (persisted per session)
  const [ragEnabled, setRagEnabled] = useState<boolean>(true);
  const [inputError, setInputError] = useState(false);
  const [savedMessageIds, setSavedMessageIds] = useState<Set<string>>(new Set());
  const [copiedId, setCopiedId] = useState<string | null>(null);
  const [streamError, setStreamError] = useState<string | null>(null);
  const [usedMemory, setUsedMemory] = useState<Record<string, MemoryItem[]>>({});
  const [usedMemoryQueries, setUsedMemoryQueries] = useState<Record<string, string>>({});
  const [pinnedMemoryIds, setPinnedMemoryIds] = useState<Set<string>>(new Set());
  const [sourcesOpen, setSourcesOpen] = useState<Record<string, boolean>>({});
  const [retryAvailable, setRetryAvailable] = useState(false);
  const [userJustSentMessage, setUserJustSentMessage] = useState(false);
  // C2.2: Context transparency - per-message expanded state (not global)
  const [contextExpandedByMsg, setContextExpandedByMsg] = useState<Record<string, boolean>>({});
  // C2.2: Copy status per item (key: `${msgId}:${itemId}`)
  const [copiedByItem, setCopiedByItem] = useState<Record<string, boolean>>({});
  const [qbSessionId, setQbSessionId] = useState<string | null>(null);
  const [qbEnabled, setQbEnabled] = useState(true);
  const [qbRefreshTrigger, setQbRefreshTrigger] = useState(0);
  // B2.5: Save confirmation modal state
  const [isSaveModalOpen, setIsSaveModalOpen] = useState(false);
  const [saveText, setSaveText] = useState('');
  const [saveTag, setSaveTag] = useState('manual');
  const [saveMessageId, setSaveMessageId] = useState<string | null>(null);
  const [saveToast, setSaveToast] = useState<string | null>(null);
  // C2: Memory suggest persistence state (localStorage-backed)
  const [handledSuggestions, setHandledSuggestions] = useState<Record<string, "saved" | "dismissed">>(() => {
    try {
      const stored = localStorage.getItem("air4_suggest_handled_v1");
      return stored ? JSON.parse(stored) : {};
    } catch {
      return {};
    }
  });
  // C3: suggestedCache includes timestamp for TTL
  const [suggestedCache, setSuggestedCache] = useState<Record<string, { suggest: boolean; proposed_tag: string; confidence: number; reason: string; ts: number }>>(() => {
    try {
      const stored = localStorage.getItem("air4_suggest_cache_v1");
      if (!stored) return {};
      const parsed = JSON.parse(stored);
      // C3: Filter out entries older than 14 days
      const now = Date.now();
      const ttlMs = 14 * 24 * 60 * 60 * 1000; // 14 days
      const filtered: Record<string, any> = {};
      for (const [key, value] of Object.entries(parsed)) {
        const entry = value as any;
        // If entry has ts and is within TTL, or if entry doesn't have ts (backward compatibility), keep it
        if (entry.ts && (now - entry.ts) > ttlMs) {
          continue; // Skip expired entries
        }
        // Ensure ts is present (for old entries without ts)
        filtered[key] = { ...entry, ts: entry.ts || now };
      }
      return filtered;
    } catch {
      return {};
    }
  });
  const styleMenuRef = useRef<HTMLDivElement>(null);
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const messagesContainerRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLInputElement | null>(null);
  const autoBrainstormRef = useRef(false);
  const abortControllerRef = useRef<AbortController | null>(null);
  const requestIdRef = useRef(0);
  const sessionFetchAbortControllerRef = useRef<AbortController | null>(null);
  const restoredForSessionRef = useRef<string | null>(null);
  const forceReloadRef = useRef<number>(0);
  const inflightKeyRef = useRef<string | null>(null);
  const userSelectTickRef = useRef<number>(0);
  const lastLoadedSessionRef = useRef<string | null>(null);
  const selectTickRef = useRef<number>(0);
  const bootRestoredRef = useRef<string | null>(null);
  const bootDoneRef = useRef<boolean>(false);
  const loadingSessionIdRef = useRef<string | null>(null);
  const abortRef = useRef<AbortController | null>(null);
  const suggestAbortControllerRef = useRef<AbortController | null>(null);
  const lastRequestRef = useRef<{ text: string; session_id: string; settings: any; botMsgId: string } | null>(null);
  const persistThrottleRef = useRef<NodeJS.Timeout | null>(null);
  const scrollThrottleRef = useRef<NodeJS.Timeout | null>(null);
  const lastPersistTimeRef = useRef<number>(0);

  // QB session management
  const QB_KEY = "air4.qb_session_id";

  async function ensureQbSession(): Promise<string> {
    const existing = localStorage.getItem(QB_KEY);
    if (existing) return existing;
    const res = await fetch("/qb/sessions", { method: "POST" });
    const json = await res.json();
    const sid = json?.session_id;
    if (!sid) throw new Error("QB session create failed");
    localStorage.setItem(QB_KEY, sid);
    return sid;
  }

  // REMOVED: Automatic QB session creation on mount
  // QB session is now created only after first user message or first AIR4 message
  // This prevents QB from being the first message in a new session

  // Load conversation messages
  const loadConversation = useCallback(async (conversationId: string) => {
    try {
      const data = await air4.getConversation(conversationId);
      
      // Transform API messages to UI Message format
      const mappedMessages: Message[] = (data.messages || []).map((msg: any, idx: number) => ({
        id: msg.id || `msg-${idx}-${Date.now()}`,
        role: msg.role === 'system' ? 'assistant' : (msg.role as 'user' | 'assistant'),
        content: msg.content || '',
        timestamp: msg.created_at ? new Date(msg.created_at).getTime() : Date.now() - (data.messages.length - idx) * 1000,
      }));
      
      setMessages(mappedMessages);
      setConversationId(conversationId);
      setSavedMessageIds(new Set());
      setUsedMemory({});
      setUsedMemoryQueries({});
      setPinnedMemoryIds(new Set());
      setSourcesOpen({});
      
      // Clear sessionId when loading conversation (to avoid conflicts)
      if (onSessionChange) {
        onSessionChange(null);
      }
      
      // Clear lastLoadedSessionRef when loading conversation (conversation mode)
      lastLoadedSessionRef.current = null;
      
      console.debug('[CHAT] Loaded conversation:', { conversationId, messageCount: mappedMessages.length });
    } catch (error: any) {
      console.error('[CHAT] Failed to load conversation:', error);
      // Show error but don't break UI - only clear if not loading a session
      if (!lastLoadedSessionRef.current) {
        setMessages([]);
      }
      setConversationId(null);
    }
  }, [air4, onSessionChange]);

  // Handle conversation selection from Sidebar
  useEffect(() => {
    // Guard: Don't load conversation if we just loaded a session (avoid clobbering)
    if (selectedConversationId && !lastLoadedSessionRef.current) {
      loadConversation(selectedConversationId);
    }
  }, [selectedConversationId, loadConversation]);

  // Map session messages array to UI Message format
  const mapSessionMessagesToUi = useCallback((messages: any[]): Message[] => {
      if (!Array.isArray(messages)) return [];
      return messages.map((msg: any, idx: number) => ({
          id: msg.id || `msg-${idx}-${Date.now()}`,
          role: (msg.role === 'system' ? 'assistant' : (msg.role || 'user')) as 'user' | 'assistant',
          content: msg.content || msg.text || msg.message || '',
          timestamp: msg.timestamp || msg.ts || msg.created_at ? 
              (typeof (msg.timestamp || msg.ts || msg.created_at) === 'number' ? 
                  (msg.timestamp || msg.ts || msg.created_at) : 
                  new Date(msg.created_at || msg.timestamp || msg.ts).getTime()) : 
              Date.now(),
      }));
  }, []);

  // Explicit openSession function - NO guards, always executes fetch
  // Abort ONLY when switching to a DIFFERENT sessionId
  const openSession = useCallback(async (sessionId: string) => {
      console.log('[openSession] START', sessionId);
      
      // ❗ Abort ТОЛЬКО если грузился ДРУГОЙ sessionId
      if (abortRef.current && loadingSessionIdRef.current !== null && loadingSessionIdRef.current !== sessionId) {
          abortRef.current.abort();
      }
      
      const ac = new AbortController();
      abortRef.current = ac;
      sessionFetchAbortControllerRef.current = ac; // Keep for compatibility
      loadingSessionIdRef.current = sessionId;
      
      try {
          // Direct fetch to backend
          const apiBaseUrl = air4.apiBaseUrl || (typeof window !== 'undefined' ? window.location.origin : '');
          const res = await fetch(`${apiBaseUrl}/sessions/${sessionId}`, { signal: ac.signal });
          
          if (!res.ok) {
              const text = await res.text();
              throw new Error(`HTTP ${res.status}: ${text.slice(0, 200)}`);
          }
          
          const raw = JSON.parse(await res.text());
          
          // Normalize session response (single source of truth for /sessions shape)
          const normalized = air4.normalizeSessionResponse(raw);
          const arr = normalized.messages;
          
          // Map messages to UI format (takes ONLY messages array)
          const uiMsgs = mapSessionMessagesToUi(arr);
          
          // Always set messages (force reload)
          if (uiMsgs.length === 0) {
              // Add opening message for empty sessions
              const openingMessage: Message = {
                  id: `opening-${Date.now()}`,
                  role: 'assistant',
                  content: 'Я здесь.\nЕсли хочешь — можем продолжить с того, что было,\nили начать с того, что сейчас важно.',
                  timestamp: Date.now()
              };
              setMessages([openingMessage]);
              console.log('[openSession] DONE', sessionId, 'len=1 (opening)');
          } else {
              setMessages(uiMsgs);
              console.log('[openSession] DONE', sessionId, 'len=', uiMsgs.length);
          }
          
          setSavedMessageIds(new Set());
          setUsedMemory({});
          setUsedMemoryQueries({});
          setPinnedMemoryIds(new Set());
          setSourcesOpen({});
          setConversationId(null);
          // C1: Cancel pending suggest requests when switching sessions
          if (suggestAbortControllerRef.current) {
            suggestAbortControllerRef.current.abort();
            suggestAbortControllerRef.current = null;
          }
          
          // Update refs
          lastLoadedSessionRef.current = sessionId;
          restoredForSessionRef.current = sessionId;
          
      } catch (e: any) {
          if (e?.name === 'AbortError' || ac.signal.aborted) {
              return; // Silent abort on switch
          }
          console.error('[openSession] ERROR', sessionId, e);
          // Don't set empty messages - let previous messages stay visible
      } finally {
          // Clear loading ref only if this is still the current loading session
          if (loadingSessionIdRef.current === sessionId) {
              loadingSessionIdRef.current = null;
          }
      }
  }, [air4, mapSessionMessagesToUi]);

  // Expose openSession to parent component
  useEffect(() => {
      if (onOpenSessionReady) {
          onOpenSessionReady(openSession);
      }
  }, [onOpenSessionReady, openSession]);

  // Load session messages (session-only, without conversation mapping)
  const loadSessionMessages = useCallback(async (sessionIdToLoad: string) => {
      // Cancel any in-flight session fetch
      if (sessionFetchAbortControllerRef.current) {
          sessionFetchAbortControllerRef.current.abort();
      }

      // B4 lifecycle: Guard - only call getSessionById if session ID is valid (from backend POST /sessions/new)
      if (!air4.isValidSessionId(sessionIdToLoad)) {
          console.warn('[CHAT] Invalid session ID, skipping getSessionById:', sessionIdToLoad);
          // Only clear if this is not the already loaded session
          if (lastLoadedSessionRef.current !== sessionIdToLoad) {
              setMessages([]);
          }
          setSavedMessageIds(new Set());
          setUsedMemory({});
          setUsedMemoryQueries({});
          setPinnedMemoryIds(new Set());
          setSourcesOpen({});
          return;
      }

      console.debug('[CHAT] loadSessionMessages: sessionId', sessionIdToLoad);

      // Create new AbortController for this fetch
      const abortController = new AbortController();
      sessionFetchAbortControllerRef.current = abortController;
      const currentSessionId = sessionIdToLoad; // Capture for race check

      try {
          console.debug('[CHAT] fetching session from API', currentSessionId);
          const s = await air4.getSessionById(currentSessionId, abortController.signal);
          
          // Race check: only update if sessionId hasn't changed
          if (abortController.signal.aborted || currentSessionId !== sessionIdToLoad) {
              console.debug('[CHAT] session fetch aborted or session changed, ignoring response');
              return;
          }
          
          console.debug('[CHAT] fetched', { id: s.id, messages: s.messages?.length });
          const loadedMessages = s.messages || [];
          
          // Add opening message for new empty sessions
          if (loadedMessages.length === 0) {
            const openingMessage: Message = {
              id: `opening-${Date.now()}`,
              role: 'assistant',
              content: 'Я здесь.\nЕсли хочешь — можем продолжить с того, что было,\nили начать с того, что сейчас важно.',
              timestamp: Date.now()
            };
            const messagesWithOpening = [openingMessage];
            setMessages(messagesWithOpening);
            console.log('[load] setMessages(len=', messagesWithOpening.length, ') sessionId=', sessionIdToLoad);
            // Persist opening message to session (local)
            air4.upsertSession({
              ...s,
              messages: messagesWithOpening
            });
          } else {
            setMessages(loadedMessages);
            console.log('[load] setMessages(len=', loadedMessages.length, ') sessionId=', sessionIdToLoad);
            air4.upsertSession(s);
          }
          
          // Set guard and lock after successful load
          lastLoadedSessionRef.current = sessionIdToLoad;
          if (loadedMessages.length > 0) {
              restoredForSessionRef.current = sessionIdToLoad;
          }
          
          // Create QB session if session has messages (not a new session)
          // This allows QB to work in existing sessions, but prevents auto-start on new sessions
          if (qbEnabled && !qbSessionId && loadedMessages.length > 0) {
            ensureQbSession().then(setQbSessionId).catch(console.error);
          }
      } catch (e: any) {
              // Ignore AbortError (expected when session changes)
              if (e.name === 'AbortError' || e.message?.includes('aborted')) {
                  console.debug('[CHAT] session fetch aborted');
                  return;
              }
              
              // Handle 404 "Session not found" - create new session and update URL/localStorage
              // B4 lifecycle: Create new session via POST /sessions/new when session not found
              const is404 = e.message === 'Session not found' || (e.message?.includes && e.message.includes('Session not found'));
              if (is404 && currentSessionId === sessionIdToLoad) {
                  console.warn('[session] invalid sessionId -> created new', currentSessionId);
                  try {
                      const newSession = await air4.createSession('');
                      const newSessionId = newSession.id;
                      
                      // Add opening message for new session
                      const openingMessage: Message = {
                          id: `opening-${Date.now()}`,
                          role: 'assistant',
                          content: 'Я здесь.\nЕсли хочешь — можем продолжить с того, что было,\nили начать с того, что сейчас важно.',
                          timestamp: Date.now()
                      };
                      const messagesWithOpening = [openingMessage];
                      setMessages(messagesWithOpening);
                      
                      // Update session with opening message
                      air4.upsertSession({
                          ...newSession,
                          messages: messagesWithOpening
                      });
                      
                      // Update URL parameter (replaceState to avoid adding history entry)
                      const url = new URL(window.location.href);
                      url.searchParams.set('session', newSessionId);
                      window.history.replaceState({}, '', url.toString());
                      
                      // Update sessionId in React state (via callback to parent component)
                      if (onSessionChange) {
                          onSessionChange(newSessionId);
                      }
                      
                      return; // Don't set empty messages, let URL update trigger re-render
                  } catch (createError) {
                      console.error('[CHAT] Failed to create new session after 404:', createError);
                      // Fall through to set empty messages
                  }
              }
              
              console.debug('[CHAT] fetch failed', e);
              // Only set empty messages if this is still the current session AND not already loaded
              if (currentSessionId === sessionIdToLoad && lastLoadedSessionRef.current !== sessionIdToLoad) {
                  setMessages([]);
                  setSavedMessageIds(new Set());
                  setUsedMemory({});
                  setUsedMemoryQueries({});
                  setPinnedMemoryIds(new Set());
                  setSourcesOpen({});
              }
          }
  }, [air4, qbEnabled, qbSessionId, ensureQbSession, setQbSessionId, onSessionChange]);

  // ЕДИНЫЙ эффект загрузки: зависит от sessionId и sessionOpenTick
  // Это решает "повторный клик не грузит", потому что tick меняется всегда
  useEffect(() => {
      if (!sessionId) {
          restoredForSessionRef.current = null;
          inflightKeyRef.current = null;
          lastLoadedSessionRef.current = null;
          bootRestoredRef.current = null;
          loadingSessionIdRef.current = null;
          // OK to clear messages when switching to no session (explicit clear)
          setMessages([]);
          setSavedMessageIds(new Set());
          setUsedMemory({});
          setUsedMemoryQueries({});
          setPinnedMemoryIds(new Set());
          setSourcesOpen({});
          // Clear conversationId when switching to no session
          setConversationId(null);
          return;
      }
      
      // Always call openSession when sessionId or sessionOpenTick changes
      openSession(sessionId);
      
      // Cleanup: abort on unmount or sessionId change
      return () => {
          if (sessionFetchAbortControllerRef.current) {
              sessionFetchAbortControllerRef.current.abort();
          }
      };
  }, [sessionId, sessionOpenTick, openSession]); // sessionOpenTick forces reload on same sessionId

  // Handle outside click for style menu and model mode menu
  useEffect(() => {
    const handleClickOutside = (event: MouseEvent) => {
      if (styleMenuRef.current && !styleMenuRef.current.contains(event.target as Node)) {
        setShowStyleMenu(false);
      }
      if (modelModeMenuRef.current && !modelModeMenuRef.current.contains(event.target as Node)) {
        setShowModelModeMenu(false);
      }
    };
    document.addEventListener('mousedown', handleClickOutside);
    return () => document.removeEventListener('mousedown', handleClickOutside);
  }, []);

  // Sync modelMode from settings
  useEffect(() => {
    if (settings.modelMode) {
      setModelMode(settings.modelMode);
    }
  }, [settings.modelMode]);

  // C2.0: Load RAG setting from localStorage when session changes
  useEffect(() => {
    if (sessionId) {
      const key = `air4_rag_enabled_v1:${sessionId}`;
      const stored = localStorage.getItem(key);
      const enabled = stored !== null ? stored === "1" : true; // default true
      setRagEnabled(enabled);
      console.debug(`[C2.0] Loaded RAG setting for session ${sessionId}: ${enabled}`);
    } else {
      setRagEnabled(true); // default when no session
    }
  }, [sessionId]);

  // C2.0: Save RAG setting to localStorage when toggled
  const handleRagToggle = useCallback(() => {
    const newValue = !ragEnabled;
    setRagEnabled(newValue);
    if (sessionId) {
      const key = `air4_rag_enabled_v1:${sessionId}`;
      localStorage.setItem(key, newValue ? "1" : "0");
      console.debug(`[C2.0] Saved RAG setting for session ${sessionId}: ${newValue}`);
    }
  }, [ragEnabled, sessionId]);

  // Load stats on mount only (polling is handled in Sidebar)
  useEffect(() => {
    const fetchStats = async () => {
        try {
            const s = await air4.getStats();
            setStats(s);
            setLastStatsTime(Date.now());
            setTimeAgo(0);
        } catch (e) {
            // Silently fail or set offline in service
        }
    };
    fetchStats();
  }, [air4]);

  // Update time ago counter
  useEffect(() => {
      const timer = setInterval(() => {
          setTimeAgo(Math.floor((Date.now() - lastStatsTime) / 1000));
      }, 1000);
      return () => clearInterval(timer);
  }, [lastStatsTime]);

  // If we have a stream error and a stored last request, ensure retry becomes available
  useEffect(() => {
    if (streamError && lastRequestRef.current) {
      setRetryAvailable(true);
    }
  }, [streamError]);

  // Cleanup throttle timers on unmount
  useEffect(() => {
      return () => {
          if (persistThrottleRef.current) {
              clearTimeout(persistThrottleRef.current);
          }
          if (scrollThrottleRef.current) {
              clearTimeout(scrollThrottleRef.current);
          }
      };
  }, []);

  // Helper functions для определения мусорных воспоминаний
  const SMALLTALK_RE = /(привет|здаров|как дела|спасибо|ок(ей)?|норм|понял|ага|давай|хорошо|ясно)/i;
  
  function isQuestionLike(text: string) {
    const t = text.trim();
    return t.includes("?") || /^(что|как|почему|зачем|где|когда|сколько|какой|какая|какие|можно ли)\b/i.test(t);
  }
  
  function isTooShort(text: string) {
    return text.trim().length < 22;
  }
  
  function isNoisyMemory(text: string, query?: string) {
    const t = (text ?? "").trim();
    if (!t) return true;
    if (SMALLTALK_RE.test(t)) return true;
    if (isTooShort(t)) return true;
    if (isQuestionLike(t)) return true;
    // Эхо запроса: если память почти равна query
    if (query) {
      const q = query.trim().toLowerCase();
      const s = t.toLowerCase();
      if (q && (s === q || s.includes(q) || q.includes(s))) return true;
    }
    return false;
  }

  // Check if user is near bottom of messages container
  const isNearBottom = useCallback((): boolean => {
    const container = messagesContainerRef.current;
    if (!container) return true; // Default to true if container not found
    
    const threshold = 200; // pixels from bottom
    const scrollBottom = container.scrollHeight - container.scrollTop - container.clientHeight;
    return scrollBottom <= threshold;
  }, []);

  // Throttled scroll to bottom (max once per 100ms)
  const scrollToBottom = useCallback(() => {
    if (scrollThrottleRef.current) return; // Skip if throttled
    
    scrollThrottleRef.current = setTimeout(() => {
      scrollThrottleRef.current = null;
    }, 100);
    
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, []);

  // Auto-scroll only if near bottom OR user just sent a message
  useEffect(() => {
    if (userJustSentMessage || isNearBottom()) {
      scrollToBottom();
      // Reset flag after scrolling
      if (userJustSentMessage) {
        setUserJustSentMessage(false);
      }
    }
  }, [messages, routerState, isThinking, userJustSentMessage, isNearBottom, scrollToBottom]);

  useEffect(() => {
      if (initialQuery) {
          setInput(initialQuery);
          if (clearInitialQuery) clearInitialQuery();
          if (inputRef.current) {
              const len = initialQuery.length;
              inputRef.current.focus();
              try {
                  inputRef.current.setSelectionRange(len, len);
              } catch (e) {
                  // ignore selection errors
              }
          }
      }
  }, [initialQuery, clearInitialQuery]);


  useEffect(() => {
      if (initialQuery) {
          setInput(initialQuery);
          if (inputRef.current) {
              const len = initialQuery.length;
              inputRef.current.focus();
              try {
                  inputRef.current.setSelectionRange(len, len);
              } catch (e) {
                  // ignore selection errors
              }
          }
          if (clearInitialQuery) clearInitialQuery();
      }
  }, [initialQuery]);

  const handleStyleChange = (style: ResponseStyle) => {
      setResponseStyle(style);
      air4.setResponseStyle(style);
      setShowStyleMenu(false);
  };

  const handleModelModeChange = (mode: ModelMode) => {
      setModelMode(mode);
      setSettings({ ...settings, modelMode: mode });
      setShowModelModeMenu(false);
  };

  // C3.1: Emit localStorage change event for Sidebar sync
  const emitLocalStorageChange = useCallback(() => {
    window.dispatchEvent(new Event("air4:ls"));
  }, []);

  // C2: Persist handledSuggestions to localStorage
  useEffect(() => {
    try {
      localStorage.setItem("air4_suggest_handled_v1", JSON.stringify(handledSuggestions));
    } catch (e) {
      console.warn('[C2] Failed to save handledSuggestions to localStorage:', e);
    }
  }, [handledSuggestions]);

  // C2: Persist suggestedCache to localStorage
  useEffect(() => {
    try {
      localStorage.setItem("air4_suggest_cache_v1", JSON.stringify(suggestedCache));
    } catch (e) {
      console.warn('[C2] Failed to save suggestedCache to localStorage:', e);
    }
  }, [suggestedCache]);

  // B2.5: Open save confirmation modal instead of direct save
  const handleSaveMemory = (msg: Message) => {
      const trimmedContent = (msg.content || '').trim();
      if (trimmedContent.length < 5) {
          alert('Message must be at least 5 characters to save');
          return;
      }
      setSaveText(trimmedContent);
      setSaveTag('manual');
      setSaveMessageId(msg.id);
      setIsSaveModalOpen(true);
  };

  // C2: Handle suggestion Save (prefills modal with suggested tag, marks as handled)
  const handleSuggestionSave = (msg: Message, proposedTag: string) => {
      const trimmedContent = (msg.content || '').trim();
      if (trimmedContent.length < 5) {
          alert('Message must be at least 5 characters to save');
          return;
      }
      if (!sessionId) return;
      
      const suggestKey = `${sessionId}:${msg.id}`;
      setSaveText(trimmedContent);
      setSaveTag(proposedTag || 'manual');
      setSaveMessageId(msg.id);
      setIsSaveModalOpen(true);
      // C2: Mark as handled when opening save modal (will be confirmed as "saved" after successful save)
      setHandledSuggestions(prev => ({ ...prev, [suggestKey]: "saved" }));
  };

  // C2: Dismiss suggestion (mark as handled)
  const handleDismissSuggestion = (msgId: string) => {
      if (!sessionId) return;
      const suggestKey = `${sessionId}:${msgId}`;
      setHandledSuggestions(prev => ({ ...prev, [suggestKey]: "dismissed" }));
      // C3.1: Notify Sidebar about change
      emitLocalStorageChange();
  };

  // C3: Clear all suggestions for current session
  const handleClearSuggestionsForSession = () => {
      if (!sessionId) return;
      const prefix = `${sessionId}:`;
      
      // Remove from handledSuggestions
      setHandledSuggestions(prev => {
          const updated = { ...prev };
          for (const key in updated) {
              if (key.startsWith(prefix)) {
                  delete updated[key];
              }
          }
          return updated;
      });
      
      // Remove from suggestedCache
      setSuggestedCache(prev => {
          const updated = { ...prev };
          for (const key in updated) {
              if (key.startsWith(prefix)) {
                  delete updated[key];
              }
          }
          return updated;
      });
      
      // C3.1: Notify Sidebar about change (after both state updates)
      emitLocalStorageChange();
  };

  // B2.5: Confirm and save to Memory Bank
  const handleConfirmSave = async () => {
      if (!sessionId) {
          alert('No active session');
          setIsSaveModalOpen(false);
          return;
      }
      if (!saveText || saveText.trim().length < 5) {
          alert('Note must be at least 5 characters');
          return;
      }
      
      try {
          const result = await air4.addMemoryNote(sessionId, saveText.trim(), saveTag || 'manual');
          if (result.ok) {
              if (saveMessageId) {
                  setSavedMessageIds(prev => new Set(prev).add(saveMessageId));
                  // C2: Mark suggestion as "saved" after successful save
                  const suggestKey = `${sessionId}:${saveMessageId}`;
                  setHandledSuggestions(prev => ({ ...prev, [suggestKey]: "saved" }));
                  // C3.1: Notify Sidebar about change
                  emitLocalStorageChange();
              }
              setIsSaveModalOpen(false);
              setSaveToast('Saved');
              setTimeout(() => setSaveToast(null), 2000);
              // B2.6: Dispatch event to notify Memory.tsx to refresh
              window.dispatchEvent(new CustomEvent("air4:memory-saved", { detail: { sessionId } }));
          } else {
              alert('Failed to save');
          }
      } catch (error: any) {
          console.error('[Save] Failed:', error);
          alert(error?.message || 'Failed to save');
      }
  };

  const handleCopy = (text: string, id: string) => {
    navigator.clipboard.writeText(text);
    setCopiedId(id);
    setTimeout(() => setCopiedId(null), 2000);
  };

  const toggleSources = (msgId: string) => {
    setSourcesOpen(prev => ({ ...prev, [msgId]: !prev[msgId] }));
  };

  const handlePinMemory = async (memoryItem: MemoryItem, messageId: string) => {
    const memoryKey = `${messageId}-${memoryItem.id}`;
    if (pinnedMemoryIds.has(memoryKey)) return;
    
    // Получаем текст запроса из сохраненных queries
    const query = usedMemoryQueries[messageId] || '';
    
    // Guard: проверяем, не является ли память мусором
    if (isNoisyMemory(memoryItem.content, query)) {
      console.warn('[handlePinMemory] Blocked noisy memory:', memoryItem.content);
      return false;
    }
    
    // Сохраняем оригинальный category как originalTag
    const originalTag = memoryItem.category || 'note';
    
    // Сохраняем структурно с метаданными
    // Принудительно ставим tag = "rag_pin" независимо от item.category
    const success = await air4.addMemoryWithMeta(
      memoryItem.content,
      {
        source: memoryItem.source,
        tag: 'rag_pin', // Принудительно rag_pin
        originalTag: originalTag, // Сохраняем оригинальный category
        score: memoryItem.relevanceScore,
        query: query,
        sessionId: sessionId || undefined,
        pinnedFrom: 'rag_used_memory'
      }
    );
    if (success) {
      setPinnedMemoryIds(prev => new Set(prev).add(memoryKey));
    }
  };

  // Throttled persist to localStorage (max once per 250ms)
  const persistMessagesToStorage = useCallback((msgs: Message[], sid: string | null) => {
    if (!sid) return;
    
    const now = Date.now();
    if (persistThrottleRef.current) {
      // If throttled, schedule for later
      clearTimeout(persistThrottleRef.current);
    }
    
    persistThrottleRef.current = setTimeout(() => {
      persistThrottleRef.current = null;
      lastPersistTimeRef.current = Date.now();
      
      try {
        const session = air4.getSession(sid);
        if (session) {
          air4.upsertSession({
            ...session,
            messages: msgs,
            lastMessage: msgs.length > 0 ? msgs[msgs.length - 1].content : '',
            timestamp: Date.now()
          });
        }
      } catch (e) {
        console.warn('[Chat] Failed to persist messages', e);
      }
    }, Math.max(0, 250 - (now - lastPersistTimeRef.current)));
  }, [air4]);

  const handleSubmit = async (e?: React.FormEvent, retryRequest?: { text: string; session_id: string; settings: any; botMsgId: string }) => {
    if (e) e.preventDefault();
    
    const isRetry = !!retryRequest;
    const requestText = retryRequest?.text || input.trim();
    
    // Input Validation
    if (!requestText) {
        if (!isRetry) {
            setInputError(true);
            setTimeout(() => setInputError(false), 3000);
        }
        return;
    }

    const currentSessionId = retryRequest?.session_id || sessionId;
    if (!currentSessionId) return;
    
    // CRITICAL: Determine conversation_id for persistence
    // Source of truth: (1) conversationId state, (2) mapping by sessionId
    let cid: string | null = conversationId ?? null;
    if (!cid && currentSessionId) {
        const mapped = air4.getConversationIdForSession(currentSessionId);
        if (mapped) {
            cid = mapped;
            // Synchronize state for stability
            setConversationId(mapped);
            console.debug('[handleSubmit] resolved conversation_id from mapping:', { sessionId: currentSessionId, conversationId: mapped });
        }
    }
    
    // CRITICAL: Compute all needed values EARLY, before any state updates or network calls
    // This ensures lastRequestRef.current is set even if network fails immediately
    const sessionConfig = currentSessionId ? air4.getSessionConfig(currentSessionId) : undefined;
    const sessionModel = sessionConfig?.model;
    const globalModel = air4.getActiveModel?.() || "auto";
    const effectiveModel = sessionModel || globalModel || "auto";
    
    const backendSettings: Record<string, any> = {
      temperature: (settings as any).temperature,
      response_tone: sessionConfig?.tone || (settings as any).responseTone,
      output_density: sessionConfig?.density || (settings as any).outputDensity,
      interface_language: sessionConfig?.uiLang || (settings as any).interfaceLanguage,
      model_mode: sessionConfig?.modelMode || modelMode || 'auto',
      model: effectiveModel,
    };

    if (sessionConfig?.streaming !== undefined) {
      backendSettings.streaming = sessionConfig.streaming;
    }

    // Whitelist only backend-accepted keys to avoid Pydantic validation errors
    const BACKEND_ACCEPTED_KEYS = ['temperature', 'response_tone', 'output_density', 'interface_language', 'model_mode', 'model', 'streaming'];
    const cleanedSettings: Record<string, any> = {};
    for (const key of BACKEND_ACCEPTED_KEYS) {
      if (backendSettings[key] !== undefined && backendSettings[key] !== null) {
        cleanedSettings[key] = backendSettings[key];
      }
    }
    const streamingEnabled = sessionConfig?.streaming !== undefined 
      ? sessionConfig.streaming 
      : (settings.streaming !== false); // default true
    
    // PHASE Q5: Get thinking_mode from localStorage (same key as QB panel uses)
    const thinkingMode = typeof window !== 'undefined' 
      ? (localStorage.getItem("air4.thinking_mode") || "structured")
      : "structured";
    
    const botMsgId = retryRequest?.botMsgId || (Date.now() + 1).toString();
    
    // CRITICAL: Store request for retry IMMEDIATELY, before any network calls
    lastRequestRef.current = {
      text: requestText,
      session_id: currentSessionId,
      settings: cleanedSettings,
      botMsgId: botMsgId
    };
    
    // Защита от двойной отправки: если уже идет генерация, прерываем текущий запрос
    if (isThinking && abortControllerRef.current) {
        abortControllerRef.current.abort();
    }
    
    // Генерируем новый requestId для защиты от гонок
    requestIdRef.current += 1;
    const rid = requestIdRef.current;
    
    setInputError(false);
    setRetryAvailable(false); // Clear retry on new attempt

    // If retry, remove the partial assistant message
    let currentMessages = messages;
    if (isRetry && retryRequest) {
      currentMessages = messages.filter(m => m.id !== retryRequest.botMsgId);
      setMessages(currentMessages);
    }

    const userMsg: Message = {
      id: Date.now().toString(),
      role: 'user',
      content: requestText,
      timestamp: Date.now()
    };

    const newMessages = [...currentMessages, userMsg];
    setMessages(newMessages);
    if (!isRetry) {
      setInput('');
    }
    setIsThinking(true);
    setRouterState(null);
    setUserJustSentMessage(true); // Flag for auto-scroll

    // Count user messages before adding this one
    const userMessagesCountBefore = currentMessages.filter(m => m.role === 'user').length;
    
    // Create QB session only after first user message (not on session creation)
    // This prevents QB from being the first message in a new session
    if (qbEnabled && !qbSessionId && userMessagesCountBefore === 0) {
      // First user message in new session - create QB session now
      try {
        const qbSid = await ensureQbSession();
        setQbSessionId(qbSid);
      } catch (e) {
        console.warn('[Chat] Failed to create QB session', e);
      }
    }
    
    // Enable QB only after first user message (not on the first message itself)
    const qbEnabledForRequest = qbEnabled && userMessagesCountBefore >= 1;

    let didFail = false;
    try {
      setStreamError(null);
      
      // Создаём AbortController для нового запроса
      const abortController = new AbortController();
      abortControllerRef.current = abortController;

      // Placeholder for bot message - устанавливаем modelUsed из effectiveModel (даже если "auto")
      setMessages(prev => [...prev, {
        id: botMsgId,
        role: 'assistant',
        content: '',
        timestamp: Date.now(),
        modelUsed: effectiveModel as ModelName
      }]);

      // Persist user message immediately
      persistMessagesToStorage([...newMessages, {
        id: botMsgId,
        role: 'assistant',
        content: '',
        timestamp: Date.now(),
        modelUsed: effectiveModel as ModelName
      }], currentSessionId);

      // C2.0: Параллельный запрос к памяти для RAG источников (только если RAG включен)
      const memorySearchPromise = (async () => {
        if (rid !== requestIdRef.current) return; // Защита от гонок
        if (!currentSessionId) return; // No session, skip memory search
        // C2.0: Skip memory search if RAG is disabled
        if (!ragEnabled) {
          console.debug(`[C2.0] rag disabled: skipping memory search for session ${currentSessionId}`);
          return;
        }
        try {
          const memoryResults = await air4.getMemories(requestText, currentSessionId);
          // Берем top-5 результатов
          const topResults = memoryResults.slice(0, 5);
          // Проверяем актуальность запроса перед сохранением
          if (rid === requestIdRef.current && topResults.length > 0) {
            setUsedMemory(prev => ({ ...prev, [botMsgId]: topResults }));
            setUsedMemoryQueries(prev => ({ ...prev, [botMsgId]: requestText }));
          }
        } catch (e) {
          console.warn('[Chat] Memory search failed', e);
        }
      })();

      let fullContent = '';

      if (streamingEnabled) {
        // Используем новый SSE стриминг
        // PHASE Q5: Pass thinking_mode from localStorage
        // C2.0: Pass rag flag to chatStream
        await air4.chatStream(
          {
            text: requestText,
            session_id: currentSessionId,
            settings: cleanedSettings,
            qb_enabled: qbEnabledForRequest,
            qb_session_id: qbSessionId,
            thinking_mode: thinkingMode,
            conversation_id: cid ?? undefined,
            rag: ragEnabled // C2.0: RAG toggle
          },
          {
            onToken: (delta: string) => {
              // Защита от гонок: проверяем, что это еще актуальный запрос
              if (rid !== requestIdRef.current) return;
              fullContent += delta;
              setMessages(prev => {
                const updatedMessages = prev.map(m => 
                  m.id === botMsgId 
                    ? { ...m, content: fullContent } 
                    : m
                );
                // Persist during streaming (throttled)
                persistMessagesToStorage(updatedMessages, currentSessionId);
                return updatedMessages;
              });
            },
            onDone: (context_used?: any) => {
              // Защита от гонок: проверяем, что это еще актуальный запрос
              if (rid !== requestIdRef.current) return;
              
              // C2.1: Final persist on completion with context_used
              setMessages(prev => {
                const finalMessages = prev.map(m => 
                  m.id === botMsgId 
                    ? { ...m, content: fullContent, context_used: context_used || undefined } 
                    : m
                );
                
                // Clear throttle and persist immediately
                if (persistThrottleRef.current) {
                  clearTimeout(persistThrottleRef.current);
                  persistThrottleRef.current = null;
                }
                try {
                  const session = air4.getSession(currentSessionId);
                  if (session) {
                    air4.upsertSession({
                      ...session,
                      messages: finalMessages,
                      lastMessage: fullContent,
                      timestamp: Date.now()
                    });
                  }
                } catch (e) {
                  console.warn('[Chat] Failed to persist on done', e);
                }
                
                // Trigger QB refresh after AIR4 response (only after first user message)
                // Count user messages from finalMessages (includes the message we just sent)
                const userCount = finalMessages.filter(m => m.role === 'user').length;
                if (qbEnabled && userCount >= 1) {
                  setQbRefreshTrigger(trigger => trigger + 1);
                }
                
                return finalMessages;
              });
              
              // C2: Suggest saving based on user intent (user->assistant pair) with persistence
              // Only call once per completed assistant message, check cache and handled state first
              if (!currentSessionId || !fullContent || fullContent.trim().length < 5) {
                return;
              }
              
              const suggestKey = `${currentSessionId}:${botMsgId}`;
              
              // C2: Skip if already handled
              if (handledSuggestions[suggestKey]) {
                return;
              }
              
              // C2: Skip if already in cache (positive or negative result)
              if (suggestedCache[suggestKey]) {
                return;
              }
              
              // C2.0: Skip memory suggest if RAG is disabled
              if (!ragEnabled) {
                console.debug(`[C2.0] rag disabled: skipping memory suggest for session ${currentSessionId}`);
                return;
              }
              
              // Cancel any pending suggest request
              if (suggestAbortControllerRef.current) {
                suggestAbortControllerRef.current.abort();
              }
              
              // Create new AbortController for this suggest request
              const suggestAbortController = new AbortController();
              suggestAbortControllerRef.current = suggestAbortController;
              
              // Use requestText (the user message that triggered this assistant response)
              const userText = requestText || "";
              
              // C2: Call suggest with user_text + assistant_text (only if not in cache/handled)
              air4.suggestMemoryItem(userText, fullContent, currentSessionId).then(result => {
                // Check if request was aborted
                if (suggestAbortController.signal.aborted) {
                  return;
                }
                
                // C3: Save result to cache (both positive and negative) with timestamp
                if (result.ok) {
                  setSuggestedCache(prev => ({
                    ...prev,
                    [suggestKey]: {
                      suggest: result.suggest,
                      proposed_tag: result.proposed_tag,
                      confidence: result.confidence,
                      reason: result.reason,
                      ts: Date.now()
                    }
                  }));
                  // C3.1: Notify Sidebar about change
                  emitLocalStorageChange();
                }
              }).catch(err => {
                // Ignore AbortError (expected when switching sessions)
                if (err?.name === 'AbortError') {
                  return;
                }
                console.warn('[C2] Suggest failed for message', botMsgId, err);
              });
              
              setIsThinking(false);
              abortControllerRef.current = null;
            },
            onError: (message: string) => {
              // Защита от гонок: проверяем, что это еще актуальный запрос
              if (rid !== requestIdRef.current) return;
              console.warn('[stream error]', { message, sessionId: currentSessionId, requestId: rid });
              setStreamError(message);
              didFail = true;
              
              // CRITICAL: Reset thinking state FIRST so retry button can appear
              setIsThinking(false);
              abortControllerRef.current = null;
              
              // Persist partial message if any content was received
              setMessages(prev => {
                const errorMessages = prev.map(m => 
                  m.id === botMsgId 
                    ? { ...m, content: fullContent } 
                    : m
                );
                
                // Only keep assistant message if it has content
                const filteredMessages = errorMessages.filter(m => 
                  m.id !== botMsgId || m.role !== 'assistant' || (m.content && m.content.trim() !== '')
                );
                
                // Persist current state (even if partial)
                if (persistThrottleRef.current) {
                  clearTimeout(persistThrottleRef.current);
                  persistThrottleRef.current = null;
                }
                try {
                  const session = air4.getSession(currentSessionId);
                  if (session) {
                    air4.upsertSession({
                      ...session,
                      messages: filteredMessages,
                      lastMessage: filteredMessages.length > 0 ? filteredMessages[filteredMessages.length - 1].content : '',
                      timestamp: Date.now()
                    });
                  }
                } catch (e) {
                  console.warn('[Chat] Failed to persist on error', e);
                }
                
                return filteredMessages;
              });
              
              // Enable retry (not for AbortError - that's handled in catch block)
              setRetryAvailable(true);
            },
            onMeta: (resolvedModel: string) => {
              // Защита от гонок: проверяем, что это еще актуальный запрос
              if (rid !== requestIdRef.current) return;
              // Обновляем routerState с resolved_model
              setRouterState(prev => ({ ...prev, model: resolvedModel }));
              // Если placeholder msg.modelUsed === "auto", обновляем его на resolved_model
              setMessages(prev => prev.map(m => 
                m.id === botMsgId && m.modelUsed === "auto"
                  ? { ...m, modelUsed: resolvedModel as ModelName }
                  : m
              ));
            }
          },
          abortController.signal
        );
      } else {
        // Fallback на старый метод streamChat
        // Преобразуем в формат для streamChat (camelCase)
        // PHASE Q5: Add thinkingMode from localStorage
        // C2.0: Include rag flag in settings
        const streamChatSettings = {
          temperature: backendSettings.temperature,
          responseTone: backendSettings.response_tone,
          outputDensity: backendSettings.output_density,
          interfaceLanguage: backendSettings.interface_language,
          activeModel: backendSettings.model || backendSettings.active_model,
          thinkingMode: thinkingMode,
          rag: ragEnabled // C2.0: RAG toggle
        };
        const cleanedStreamChatSettings = clean(streamChatSettings);
        console.log("[CHAT SEND settings]", cleanedStreamChatSettings);
        // CRITICAL: Pass cid (resolved from state or mapping) to streamChat
        const stream = air4.streamChat(newMessages, sessionId, cleanedStreamChatSettings, cid ?? undefined);
        
        let context: MemoryItem[] | undefined = undefined;
        let decision: RouterDecision | undefined = undefined;

        for await (const part of stream) {
          // Защита от гонок: проверяем, что это еще актуальный запрос
          if (rid !== requestIdRef.current) break;
          
          // Extract conversation_id from stream if present
          if (part.conversationId && !conversationId) {
            const newConversationId = part.conversationId;
            setConversationId(newConversationId);
            console.debug('[CHAT] Received conversation_id from stream:', newConversationId);
            
            // Save mapping: sessionId -> conversationId (only if mapping doesn't exist or is different)
            if (currentSessionId) {
              const existingCid = air4.getConversationIdForSession(currentSessionId);
              if (existingCid !== newConversationId) {
                air4.setSessionConversationMapping(currentSessionId, newConversationId);
                console.log('[map] set', currentSessionId, '->', newConversationId);
              } else {
                console.debug('[CHAT] Mapping already exists:', { sessionId: currentSessionId, conversationId: newConversationId });
              }
            }
          }
          
          if (part.decision) {
            decision = part.decision;
            setRouterState(decision);
            // Обновляем modelUsed ТОЛЬКО если effectiveModel === "auto"
            // Если effectiveModel != "auto" — игнорируем routerDecision.model
            if (effectiveModel === "auto") {
              setMessages(prev => prev.map(m => 
                m.id === botMsgId 
                  ? { ...m, modelUsed: decision?.model, domain: decision?.domain } 
                  : m
              ));
            } else {
              // Обновляем только domain, modelUsed оставляем как есть
              setMessages(prev => prev.map(m => 
                m.id === botMsgId 
                  ? { ...m, domain: decision?.domain } 
                  : m
              ));
            }
          }

          if (part.context) {
            context = part.context;
            setMessages(prev => prev.map(m => 
              m.id === botMsgId 
                ? { ...m, contextUsed: context } 
                : m
            ));
          }
          
          if (part.chunk) {
            fullContent += part.chunk;
            setMessages(prev => {
              const updatedMessages = prev.map(m => 
                m.id === botMsgId 
                  ? { ...m, content: fullContent } 
                  : m
              );
              // Persist during streaming (throttled)
              persistMessagesToStorage(updatedMessages, currentSessionId);
              return updatedMessages;
            });
          }
        }
        
        // Защита от гонок: проверяем, что это еще актуальный запрос
        if (rid === requestIdRef.current) {
          // Final persist on completion
          setMessages(prev => {
            const finalMessages = prev.map(m => 
              m.id === botMsgId 
                ? { ...m, content: fullContent } 
                : m
            );
            
            // Clear throttle and persist immediately
            if (persistThrottleRef.current) {
              clearTimeout(persistThrottleRef.current);
              persistThrottleRef.current = null;
            }
            try {
              const session = air4.getSession(currentSessionId);
              if (session) {
                air4.upsertSession({
                  ...session,
                  messages: finalMessages,
                  lastMessage: fullContent,
                  timestamp: Date.now()
                });
              }
            } catch (e) {
              console.warn('[Chat] Failed to persist on done (non-streaming)', e);
            }
            
            return finalMessages;
          });
          
          setIsThinking(false);
        }
      }

    } catch (error: any) {
      // Защита от гонок: проверяем, что это еще актуальный запрос
      if (rid !== requestIdRef.current) return;
      
      // Если запрос был прерван (AbortError) - не показываем ошибку, просто завершаем
      if (error.name === 'AbortError' || error.message?.includes('aborted')) {
        setIsThinking(false);
        abortControllerRef.current = null;
        // Do NOT set retryAvailable for AbortError (user cancelled)
        return;
      }
      didFail = true;
      console.error("Stream error", error);
      setStreamError(error.message || 'Произошла ошибка при отправке сообщения');
      
      // CRITICAL: Reset thinking state FIRST so retry button can appear
      setIsThinking(false);
      abortControllerRef.current = null;
      
      // Persist current state before error
      setMessages(prev => {
        if (persistThrottleRef.current) {
          clearTimeout(persistThrottleRef.current);
          persistThrottleRef.current = null;
        }
        try {
          const session = air4.getSession(currentSessionId);
          if (session) {
            const currentMsgs = prev.filter(m => m.id !== botMsgId || (m.content && m.content.trim() !== ''));
            air4.upsertSession({
              ...session,
              messages: currentMsgs,
              lastMessage: currentMsgs.length > 0 ? currentMsgs[currentMsgs.length - 1].content : '',
              timestamp: Date.now()
            });
          }
        } catch (e) {
          console.warn('[Chat] Failed to persist on catch error', e);
        }
        return prev;
      });
      
      // Enable retry
      setRetryAvailable(true);
    } finally {
      // Защита от гонок: проверяем, что это еще актуальный запрос
      if (rid === requestIdRef.current) {
        setIsThinking(false);
        abortControllerRef.current = null;
        // If the request failed (non-abort), ensure retry becomes available
        if (didFail && lastRequestRef.current) {
          setRetryAvailable(true);
        }
      }
    }
  };

  if (!sessionId) {
      return (
          <div className="h-full flex items-center justify-center text-slate-500">
              Select or create a session to begin.
          </div>
      )
  }

    // Determine display values for header
  const isOffline = stats?.isOffline ?? false;

  // Определяем effectiveModel для отображения
  const sessionConfigForDisplay = sessionId ? air4.getSessionConfig(sessionId) : undefined;
  const sessionModelForDisplay = sessionConfigForDisplay?.model;
  const globalModelForDisplay = air4.getActiveModel?.() || "auto";
  const effectiveModelForDisplay = sessionModelForDisplay || globalModelForDisplay || "auto";
  
  // Что показывать в шапке как имя модели
  const headerModelName = (() => {
    if (effectiveModelForDisplay === "auto") {
      // Если auto, показываем router decision или "auto (router)"
      return routerState?.model || "auto (router)";
    }
    // Если конкретная модель, показываем её
    return effectiveModelForDisplay;
  })();

  // Жива ли память
  const memoryActive = !isOffline;

  const styles: { id: ResponseStyle; label: string }[] = [
      { id: 'short', label: 'Short' },
      { id: 'normal', label: 'Normal' },
      { id: 'detailed', label: 'Detailed' },
  ];

  const modelModes: { id: ModelMode; label: string }[] = [
      { id: 'fast', label: 'Fast' },
      { id: 'normal', label: 'Normal' },
      { id: 'think', label: 'Think' },
      { id: 'auto', label: 'Auto' },
  ];

  // Определяем id последнего сообщения ассистента
  const lastAssistantId = messages.length > 0 
    ? (() => {
        for (let i = messages.length - 1; i >= 0; i--) {
          if (messages[i].role === 'assistant') {
            return messages[i].id;
          }
        }
        return null;
      })()
    : null;

  // Получаем sessionConfig и формируем бейджи для переопределенных полей
  const sessionConfig = sessionId ? air4.getSessionConfig(sessionId) : undefined;
  const overrideBadges: string[] = [];
  
  if (sessionConfig) {
    if (sessionConfig.model !== undefined) {
      overrideBadges.push(`Model: ${sessionConfig.model}`);
    }
    if (sessionConfig.tone !== undefined) {
      const toneLabels: Record<string, string> = { bro: 'Bro', strict: 'Strict', neutral: 'Neutral' };
      overrideBadges.push(`Tone: ${toneLabels[sessionConfig.tone] || sessionConfig.tone}`);
    }
    if (sessionConfig.density !== undefined) {
      const densityLabels: Record<string, string> = { short: 'Short', balanced: 'Balanced', deep: 'Deep' };
      overrideBadges.push(`Density: ${densityLabels[sessionConfig.density] || sessionConfig.density}`);
    }
    if (sessionConfig.uiLang !== undefined) {
      const langLabels: Record<string, string> = { auto: 'Auto', en: 'EN', ru: 'RU' };
      overrideBadges.push(`Lang: ${langLabels[sessionConfig.uiLang] || sessionConfig.uiLang}`);
    }
    if (sessionConfig.streaming !== undefined) {
      overrideBadges.push(`Streaming: ${sessionConfig.streaming ? 'on' : 'off'}`);
    }
  }

  return (
    <div className="flex flex-col h-full relative">
            {/* Enhanced System Status Header */}
            {/* Minimal top status bar */}
      <div className="h-16 flex items-center justify-between px-4 md:px-6 border-b border-white/5 bg-black/30 backdrop-blur-md">
        {/* Left: лёгкий лейбл диалога + ID */}
        <div className="flex flex-col gap-0.5">
          <div className="flex items-center gap-2 text-[11px] text-slate-400">
            <span className="hidden sm:inline text-slate-200 font-medium">
              Think
            </span>
            <span className="hidden md:inline-block text-[10px] font-mono text-slate-600">
              ID: {sessionId.slice(-8)}
            </span>
          </div>
          <span className="hidden sm:inline text-[10px] text-slate-500">
            Reasoning and decisions
          </span>
        </div>

        {/* Right: компактные баджи */}
        <div className="flex items-center gap-1 md:gap-3">
          {/* 1. Model Mode Selector */}
          <div className="relative px-2 md:px-4" ref={modelModeMenuRef}>
            <button
              onClick={() => setShowModelModeMenu(!showModelModeMenu)}
              className="flex items-center gap-1.5 text-[11px] font-medium text-slate-400 hover:text-white transition-colors"
            >
              <span className="text-slate-200">
                {modelModes.find(m => m.id === modelMode)?.label || 'Auto'}
              </span>
              <ChevronDown className="w-3 h-3 text-slate-500" />
            </button>

            {showModelModeMenu && (
              <div className="absolute top-full right-0 mt-2 w-32 bg-[#0a0f1e] border border-white/10 rounded-xl shadow-xl z-50 overflow-hidden animate-in fade-in zoom-in-95 duration-100">
                {modelModes.map((m) => (
                  <button
                    key={m.id}
                    onClick={() => handleModelModeChange(m.id)}
                    className={`w-full flex items-center justify-between px-3 py-2 text-[11px] font-medium hover:bg-white/5 transition-colors ${
                      modelMode === m.id
                        ? 'text-purple-400 bg-purple-500/5'
                        : 'text-slate-400'
                    }`}
                  >
                    {m.label}
                    {modelMode === m.id && <Check className="w-3 h-3" />}
                  </button>
                ))}
              </div>
            )}
          </div>

          {/* 2. Style Selector (Output Density) */}
          <div className="relative px-2 md:px-4" ref={styleMenuRef}>
            <button
              onClick={() => setShowStyleMenu(!showStyleMenu)}
              className="flex items-center gap-1.5 text-[11px] font-medium text-slate-400 hover:text-white transition-colors"
            >
              <span className="text-slate-200">
                {responseStyle.charAt(0).toUpperCase() + responseStyle.slice(1)}
              </span>
              <ChevronDown className="w-3 h-3 text-slate-500" />
            </button>

            {showStyleMenu && (
              <div className="absolute top-full right-0 mt-2 w-32 bg-[#0a0f1e] border border-white/10 rounded-xl shadow-xl z-50 overflow-hidden animate-in fade-in zoom-in-95 duration-100">
                {styles.map((s) => (
                  <button
                    key={s.id}
                    onClick={() => handleStyleChange(s.id)}
                    className={`w-full flex items-center justify-between px-3 py-2 text-[11px] font-medium hover:bg-white/5 transition-colors ${
                      responseStyle === s.id
                        ? 'text-air-500 bg-air-500/5'
                        : 'text-slate-400'
                    }`}
                  >
                    {s.label}
                    {responseStyle === s.id && <Check className="w-3 h-3" />}
                  </button>
                ))}
              </div>
            )}
          </div>

          {/* C2.0: RAG Toggle */}
          <div className="px-2 md:px-4">
            <button
              onClick={handleRagToggle}
              className={`flex items-center gap-1.5 px-2.5 py-1 rounded-lg text-[11px] font-medium transition-colors ${
                ragEnabled
                  ? 'bg-emerald-500/20 text-emerald-400 border border-emerald-500/40'
                  : 'bg-slate-800/50 text-slate-500 border border-slate-700/50'
              }`}
              title={ragEnabled ? 'RAG: ON (click to disable)' : 'RAG: OFF (click to enable)'}
            >
              <BrainCircuit className={`w-3 h-3 ${ragEnabled ? 'text-emerald-400' : 'text-slate-500'}`} />
              <span>{ragEnabled ? 'ON' : 'OFF'}</span>
            </button>
          </div>

          {/* 3. Core Status */}
          <div className="hidden md:flex items-center gap-2 px-3">
            <div
              className={`w-2 h-2 rounded-full ${
                isOffline
                  ? 'bg-red-500'
                  : 'bg-emerald-500 shadow-[0_0_8px_rgba(16,185,129,0.4)]'
              }`}
            />
            <span
              className={`text-[11px] font-medium ${
                isOffline ? 'text-red-400' : 'text-emerald-400'
              }`}
            >
              {isOffline ? 'Offline' : 'Online'}
            </span>
          </div>

          {/* 4. Model Info */}
          <div className="hidden md:flex items-center gap-2 px-3">
            <Cpu className="w-3.5 h-3.5 text-air-500" />
            <span className="text-[11px] font-mono text-slate-200">
              Model: {headerModelName}
            </span>
            {sessionModelForDisplay && (
              <span className="text-[9px] text-slate-500 font-normal">
                (session override)
              </span>
            )}
          </div>

          {/* C3: Clear suggestions button (only if sessionId exists) */}
          {sessionId && (() => {
            const prefix = `${sessionId}:`;
            const hasUnhandledSuggestions = Object.keys(suggestedCache).some(key => 
              key.startsWith(prefix) && 
              suggestedCache[key].suggest === true && 
              !handledSuggestions[key]
            );
            if (!hasUnhandledSuggestions) return null;
            return (
              <button
                onClick={handleClearSuggestionsForSession}
                className="px-2 py-1 text-[10px] font-medium text-amber-400 hover:text-amber-300 hover:bg-amber-500/10 rounded transition-colors"
                title="Clear suggestions for this session"
              >
                Clear suggestions
              </button>
            );
          })()}

          {/* 5. Memory Status */}
          <div className="hidden md:flex items-center gap-2 px-3">
            <Database
              className={`w-3.5 h-3.5 ${
                memoryActive ? 'text-indigo-400' : 'text-slate-600'
              }`}
            />
            <span
              className={`text-[11px] font-medium ${
                memoryActive ? 'text-indigo-300' : 'text-slate-500'
              }`}
            >
              {memoryActive ? 'ChromaDB' : 'Inactive'}
            </span>
          </div>

          {/* 6. Index Update */}
          <div className="hidden xl:flex items-center gap-2 px-3">
            <Activity className="w-3.5 h-3.5 text-slate-500" />
            <span className="text-[11px] font-mono text-slate-400">
              {stats ? `${timeAgo}s ago` : '...'}
            </span>
          </div>
        </div>
      </div>

      {/* Session Overrides Badges */}
      {overrideBadges.length > 0 && (
        <div className="px-4 md:px-6 py-2 border-b border-white/5 bg-black/20 flex items-center gap-2 flex-wrap">
          <span className="text-[10px] text-slate-500 font-bold uppercase tracking-wider">Overrides:</span>
          {overrideBadges.map((badge, idx) => (
            <span
              key={idx}
              className="px-2 py-0.5 text-[10px] font-medium text-air-400 border border-air-500/30 rounded-full bg-air-500/5"
            >
              {badge}
            </span>
          ))}
        </div>
      )}

      {/* Messages Area */}
      {/* QB Panel */}
      <QBPanel
        enabled={qbEnabled}
        refreshTrigger={qbRefreshTrigger}
        userTurnsCount={useMemo(() => messages.filter(m => m.role === 'user').length, [messages])}
        onAnswered={(payload) => {
          // optional: can update local UI state with payload.snapshot/score
        }}
      />

      <div ref={messagesContainerRef} className="flex-1 overflow-y-auto p-4 md:p-8 space-y-6 custom-scrollbar scroll-smooth">
        {/* DEBUG: messages count */}
        {process.env.NODE_ENV === 'development' && (
          <div className="text-xs text-slate-500 mb-2">DEBUG: messages:{messages.length}</div>
        )}
        {messages.map((msg, index) => {
          const isAssistant = msg.role === 'assistant';

          let displayContent = msg.content as string;
          let modelFromPrefix: string | null = null;

          if (isAssistant && typeof msg.content === 'string') {
              const m = msg.content.match(/^\[([^\]]+)\]\s?(.*)$/s);
              if (m) {
                  modelFromPrefix = m[1];
                  displayContent = m[2] || '';
              }
          }

          // Generate stable, unique key
          const msgKey = msg.id 
            ? `msg:${msg.id}` 
            : `msg:${msg.role}:${msg.timestamp ?? index}:${hash(msg.content ?? '').slice(0, 8)}`;

          return (
          <div 
            key={msgKey} 
            className={`flex flex-col ${msg.role === 'user' ? 'items-end' : 'items-start'} animate-message-in`}
            style={{ animationFillMode: 'both' }}
          >
            
            {/* Metadata (Avatar name + Timestamp) */}
            <div className="text-[10px] text-slate-500 mb-1 px-1 flex items-center gap-2">
                <span className="font-medium">{msg.role === 'user' ? 'You' : 'AIr4 Core'}</span>
                <span className="opacity-50 text-[9px] font-mono">
                    {new Date(msg.timestamp).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}
                </span>
            </div>

            {/* Bubble */}
            <div className={`max-w-[85%] md:max-w-[70%] p-4 rounded-2xl text-sm leading-relaxed whitespace-pre-wrap relative shadow-sm ${
                msg.role === 'user' 
                  ? 'bg-air-600 text-white rounded-br-sm shadow-[0_4px_20px_rgba(234,88,12,0.2)]' 
                  : 'glass-card text-slate-200 rounded-bl-sm border-white/5 shadow-[0_4px_20px_rgba(0,0,0,0.2)]'
            }`}>
                
                {/* Model badge */}
                {isAssistant && (() => {
                  // Определяем что показывать в бейдже
                  let displayModel: string | null = null;
                  if (modelFromPrefix) {
                    displayModel = modelFromPrefix;
                  } else if (msg.modelUsed) {
                    if (msg.modelUsed === "auto") {
                      // Если modelUsed === "auto" и есть decision -> показываем decision.model (или msg.modelUsed если нет decision)
                      displayModel = routerState?.model || msg.modelUsed;
                    } else {
                      // Если modelUsed !== "auto" -> показываем msg.modelUsed
                      displayModel = msg.modelUsed;
                    }
                  }
                  
                  return displayModel ? (
                    <div className="mb-2 flex items-center gap-2">
                      <span className="
  inline-flex items-center gap-1.5 
  px-3 py-1 
  rounded-lg
  bg-black/20
  border border-air-500/40
  text-air-400
  font-mono text-[12px] font-semibold
">
  <Cpu className="w-4 h-4 text-air-400" />
  {displayModel}
</span>
                    </div>
                  ) : null;
                })()}

                {/* C2.2: Context transparency - show context used by model with per-message expand/collapse */}
                {msg.role === 'assistant' && ragEnabled && msg.context_used && (
                    (() => {
                        const hasMemory = msg.context_used.memory && msg.context_used.memory.length > 0;
                        const hasDocs = msg.context_used.docs && msg.context_used.docs.length > 0;
                        const hasContext = hasMemory || hasDocs;
                        // C2.2: Per-message expanded state (use message id, fallback to stable key)
                        const msgKey = msg.id || `${msg.role}-${index}-${msg.timestamp || Date.now()}`;
                        const isExpanded = contextExpandedByMsg[msgKey] || false;
                        
                        // C2.2: Copy ID handler
                        const handleCopyId = async (itemId: string) => {
                            const copyKey = `${msgKey}:${itemId}`;
                            try {
                                await navigator.clipboard.writeText(itemId);
                                setCopiedByItem(prev => ({ ...prev, [copyKey]: true }));
                                setTimeout(() => {
                                    setCopiedByItem(prev => {
                                        const next = { ...prev };
                                        delete next[copyKey];
                                        return next;
                                    });
                                }, 1000);
                            } catch (e) {
                                console.debug('[C2.2] Failed to copy ID:', e);
                            }
                        };
                        
                        // C2.3: Open in Store handler
                        const handleOpenInStore = (item: { id: string; kind?: string | null }, currentSessionId: string | null) => {
                            try {
                                if (!currentSessionId) {
                                    console.debug('[C2.3] No active session, cannot open in store');
                                    return;
                                }
                                // C2.3: Determine tab based on item kind
                                const effectiveKind = item.kind || 'note';
                                const targetTab = effectiveKind === 'note' ? 'notes' : 'all';
                                
                                // C2.3: Store params in localStorage for Memory page to read
                                const navParams = {
                                    session_id: currentSessionId,
                                    tab: targetTab,
                                    q: item.id
                                };
                                localStorage.setItem('air4_memory_nav_params', JSON.stringify(navParams));
                                
                                // C2.3: Dispatch custom event to trigger navigation
                                window.dispatchEvent(new CustomEvent('air4:navigate-to-memory', { detail: navParams }));
                            } catch (e) {
                                console.debug('[C2.3] Failed to open in store:', e);
                            }
                        };
                        
                        if (!hasContext) {
                            return (
                                <div className="mb-3 text-[10px] text-slate-500 italic pb-3 border-b border-white/5">
                                    No external context used
                                </div>
                            );
                        }
                        
                        return (
                            <div className="mb-3 pb-3 border-b border-white/5">
                                <button
                                    onClick={() => setContextExpandedByMsg(prev => ({ ...prev, [msgKey]: !isExpanded }))}
                                    className="flex items-center gap-1.5 text-[10px] font-medium text-slate-400 hover:text-air-400 transition-colors mb-2"
                                >
                                    <BrainCircuit className="w-3 h-3" />
                                    <span>Context</span>
                                    <ChevronDown className={`w-3 h-3 transition-transform ${isExpanded ? 'rotate-180' : ''}`} />
                                </button>
                                
                                {isExpanded && (
                                    <div className="flex flex-col gap-2">
                                        {/* Memory items */}
                                        {hasMemory && (
                                            <div>
                                                <div className="text-[10px] font-semibold text-slate-400 mb-1">Memory</div>
                                                {msg.context_used.memory!.map((item, idx) => {
                                                    const copyKey = `${msgKey}:${item.id}`;
                                                    const isCopied = copiedByItem[copyKey] || false;
                                                    // C2.2: Build meta line (namespace • tag • source)
                                                    const metaParts: string[] = [];
                                                    if (item.namespace) metaParts.push(item.namespace);
                                                    if (item.tag) metaParts.push(item.tag);
                                                    if (item.source) metaParts.push(item.source);
                                                    const metaLine = metaParts.length > 0 ? metaParts.join(' • ') : null;
                                                    
                                                    return (
                                                        <div key={idx} className="text-[10px] text-slate-400 bg-white/5 px-2 py-1.5 rounded mb-1 border border-white/5">
                                                            <div className="flex items-center gap-2 mb-1 flex-wrap">
                                                                <span className={`px-1.5 py-0.5 rounded text-[9px] font-medium ${
                                                                    item.kind === 'chat' ? 'bg-blue-500/20 text-blue-400' :
                                                                    item.kind === 'note' ? 'bg-purple-500/20 text-purple-400' :
                                                                    item.kind === 'fact' ? 'bg-emerald-500/20 text-emerald-400' :
                                                                    'bg-slate-500/20 text-slate-400'
                                                                }`}>
                                                                    {item.kind}
                                                                </span>
                                                                {item.score > 0 && (
                                                                    <span className="text-[9px] text-slate-500">score: {item.score.toFixed(2)}</span>
                                                                )}
                                                                {/* C2.2: Copy ID button */}
                                                                <button
                                                                    onClick={(e) => {
                                                                        e.stopPropagation();
                                                                        handleCopyId(item.id);
                                                                    }}
                                                                    className="text-[9px] text-slate-500 hover:text-air-400 transition-colors px-1.5 py-0.5 rounded hover:bg-white/5"
                                                                    title="Copy ID"
                                                                >
                                                                    {isCopied ? 'Copied' : 'Copy ID'}
                                                                </button>
                                                                {/* C2.3: Open in Store button */}
                                                                <button
                                                                    onClick={(e) => {
                                                                        e.stopPropagation();
                                                                        handleOpenInStore(item, sessionId);
                                                                    }}
                                                                    className="text-[9px] text-slate-500 hover:text-air-400 transition-colors px-1.5 py-0.5 rounded hover:bg-white/5"
                                                                    title="Open in Store"
                                                                >
                                                                    Open
                                                                </button>
                                                            </div>
                                                            {/* C2.2: Meta line (namespace • tag • source) */}
                                                            {metaLine && (
                                                                <div className="text-[9px] text-slate-500 mb-1 italic">{metaLine}</div>
                                                            )}
                                                            <div className="text-slate-300 line-clamp-2">{item.preview}</div>
                                                        </div>
                                                    );
                                                })}
                                            </div>
                                        )}
                                        
                                        {/* Docs items */}
                                        {hasDocs && (
                                            <div>
                                                <div className="text-[10px] font-semibold text-slate-400 mb-1">Docs</div>
                                                {msg.context_used.docs!.map((doc, idx) => (
                                                    <div key={idx} className="text-[10px] text-slate-400 bg-white/5 px-2 py-1.5 rounded mb-1 border border-white/5">
                                                        <div className="font-medium text-slate-300 mb-1">{doc.title || doc.source}</div>
                                                        <div className="text-slate-400 line-clamp-2">{doc.preview}</div>
                                                    </div>
                                                ))}
                                            </div>
                                        )}
                                    </div>
                                )}
                            </div>
                        );
                    })()
                )}
                
                {isAssistant && !displayContent && isThinking ? (
                    <div className="flex items-center gap-1">
                        <span className="w-1.5 h-1.5 bg-air-400 rounded-full dot-pulse"></span>
                        <span className="w-1.5 h-1.5 bg-air-400 rounded-full dot-pulse" style={{ animationDelay: '0.15s' }}></span>
                        <span className="w-1.5 h-1.5 bg-air-400 rounded-full dot-pulse" style={{ animationDelay: '0.30s' }}></span>
                        <span className="text-[10px] text-air-300/70 font-mono ml-2">Processing...</span>
                    </div>
                ) : (
                    displayContent
                )}

                {/* B2.5: User message actions (Save button) */}
                {msg.role === 'user' && (
                    <div className="mt-3 pt-2 border-t border-white/10 flex items-center gap-2 opacity-60 hover:opacity-100 transition-opacity">
                        <button 
                            onClick={() => handleSaveMemory(msg)}
                            className={`p-1.5 rounded-lg transition-all ${
                                savedMessageIds.has(msg.id) 
                                ? 'bg-air-500/10 text-air-500' 
                                : 'hover:bg-white/10 text-slate-400 hover:text-air-400'
                            }`}
                            title="Save to Memory Bank"
                        >
                            <Star className={`w-3.5 h-3.5 ${savedMessageIds.has(msg.id) ? 'fill-air-500' : ''}`} />
                        </button>
                        <button 
                            onClick={() => handleCopy(msg.content, msg.id)}
                            className="p-1.5 hover:bg-white/10 rounded-lg text-slate-400 hover:text-white transition-colors"
                            title="Copy to Clipboard"
                        >
                            {copiedId === msg.id ? <ClipboardCheck className="w-3.5 h-3.5 text-emerald-500" /> : <Copy className="w-3.5 h-3.5" />}
                        </button>
                    </div>
                )}

                {/* C2: Suggested to save pill (GoogleUI design, persistence-aware) */}
                {(() => {
                  if (msg.role !== 'assistant' || isThinking || !sessionId) return false;
                  const suggestKey = `${sessionId}:${msg.id}`;
                  const cacheEntry = suggestedCache[suggestKey];
                  const handled = handledSuggestions[suggestKey];
                  return cacheEntry?.suggest === true && !handled;
                })() && (
                    <div className="mt-3 pt-2 border-t border-white/5">
                        <div className="flex items-center gap-2 px-3 py-2 glass-card bg-amber-500/10 border border-amber-500/30 rounded-lg">
                            <span className="text-xs text-amber-400 font-medium flex-1">💡 Suggested to save</span>
                            <button
                                onClick={() => {
                                  const suggestKey = sessionId ? `${sessionId}:${msg.id}` : null;
                                  const cacheEntry = suggestKey ? suggestedCache[suggestKey] : null;
                                  handleSuggestionSave(msg, cacheEntry?.proposed_tag || 'manual');
                                }}
                                className="px-3 py-1 text-xs font-medium text-white bg-amber-600 hover:bg-amber-700 rounded-lg transition-colors shadow-sm"
                            >
                                Save
                            </button>
                            <button
                                onClick={() => handleDismissSuggestion(msg.id)}
                                className="px-3 py-1 text-xs font-medium text-slate-400 hover:text-slate-200 rounded-lg hover:bg-white/10 transition-colors"
                            >
                                Dismiss
                            </button>
                        </div>
                    </div>
                )}

                {/* AI Actions Footer */}
                {msg.role === 'assistant' && !isThinking && (
                    <div className="mt-3 pt-2 border-t border-white/5 flex items-center gap-2 opacity-60 hover:opacity-100 transition-opacity">
                        <button 
                            onClick={() => handleSaveMemory(msg)}
                            className={`p-1.5 rounded-lg transition-all ${
                                savedMessageIds.has(msg.id) 
                                ? 'bg-air-500/10 text-air-500' 
                                : 'hover:bg-white/10 text-slate-500 hover:text-air-400'
                            }`}
                            title="Send to Memory Bank"
                        >
                            <Star className={`w-3.5 h-3.5 ${savedMessageIds.has(msg.id) ? 'fill-air-500' : ''}`} />
                        </button>
                        <button 
                            onClick={() => handleCopy(msg.content, msg.id)}
                            className="p-1.5 hover:bg-white/10 rounded-lg text-slate-500 hover:text-white transition-colors"
                            title="Copy to Clipboard"
                        >
                            {copiedId === msg.id ? <ClipboardCheck className="w-3.5 h-3.5 text-emerald-500" /> : <Copy className="w-3.5 h-3.5" />}
                        </button>
                        {usedMemory[msg.id] && usedMemory[msg.id].length > 0 && (
                            <button 
                                onClick={() => toggleSources(msg.id)}
                                className="p-1.5 hover:bg-white/10 rounded-lg text-slate-500 hover:text-air-400 transition-colors"
                                title={sourcesOpen[msg.id] ? "Hide sources" : "Show sources"}
                            >
                                {sourcesOpen[msg.id] ? <EyeOff className="w-3.5 h-3.5" /> : <Eye className="w-3.5 h-3.5" />}
                            </button>
                        )}
                    </div>
                )}
            </div>

            {/* Used Memory Sources - показываем если sourcesOpen[msg.id] === true */}
            {msg.role === 'assistant' && usedMemory[msg.id] && usedMemory[msg.id].length > 0 && sourcesOpen[msg.id] === true && (
              <div className="mt-2 max-w-[85%] md:max-w-[70%] px-4 py-2 bg-black/20 rounded-xl border border-white/5">
                <div className="flex items-center gap-1.5 mb-2 text-[10px] font-bold text-air-400 uppercase tracking-wider">
                  <Database className="w-3 h-3" />
                  Used memory
                </div>
                <div className="flex flex-col gap-1.5">
                  {usedMemory[msg.id].map((item, idx) => {
                    const memoryKey = `${msg.id}-${item.id}`;
                    const isPinned = pinnedMemoryIds.has(memoryKey);
                    const scorePercent = item.relevanceScore ? Math.round(item.relevanceScore * 100) : null;
                    const shortText = item.content.length > 120 
                      ? item.content.substring(0, 120) + '...' 
                      : item.content;
                    const textLines = shortText.split('\n').slice(0, 2).join('\n');
                    const noisy = isNoisyMemory(item.content, usedMemoryQueries[msg.id]);
                    
                    return (
                      <div 
                        key={item.id || idx} 
                        className="flex items-start gap-2 p-2 bg-white/5 rounded-lg border border-white/5 hover:border-air-500/20 transition-colors"
                      >
                        <div className="flex-1 min-w-0">
                          <div className="flex items-center gap-2 mb-1">
                            {scorePercent !== null && (
                              <span className="text-[9px] font-mono text-air-400 font-bold">
                                {scorePercent}%
                              </span>
                            )}
                            {item.source && (
                              <span className="text-[9px] text-slate-500 font-medium">
                                {item.source}
                              </span>
                            )}
                          </div>
                          <p className="text-[10px] text-slate-300 leading-relaxed whitespace-pre-wrap line-clamp-2">
                            {textLines}
                          </p>
                        </div>
                        {noisy ? (
                          <div 
                            className="flex-shrink-0 px-2 py-1 rounded text-[9px] text-slate-500 border border-slate-700/50 bg-slate-800/30 cursor-default"
                            title="Не сохраняю: short/smalltalk/question/echo"
                          >
                            Not a fact
                          </div>
                        ) : (
                          <button
                            onClick={() => handlePinMemory(item, msg.id)}
                            disabled={isPinned}
                            className={`flex-shrink-0 p-1.5 rounded transition-all ${
                              isPinned
                                ? 'bg-emerald-500/10 text-emerald-400 cursor-default'
                                : 'hover:bg-white/10 text-slate-500 hover:text-air-400'
                            }`}
                            title={isPinned ? 'Pinned' : 'Pin to memory'}
                          >
                            {isPinned ? (
                              <PinOff className="w-3 h-3" />
                            ) : (
                              <Pin className="w-3 h-3" />
                            )}
                          </button>
                        )}
                      </div>
                    );
                  })}
                </div>
              </div>
            )}
          </div>
        ); })}

        
        <div ref={messagesEndRef} />
      </div>

      {/* Error Message */}
      {streamError && (
        <div className="px-4 md:px-6 py-2 bg-red-500/10 border-t border-red-500/30">
          <div className="max-w-4xl mx-auto text-sm text-red-400 flex items-center gap-2">
            <span className="text-red-500">⚠️</span>
            <span>{streamError}</span>
            <button 
              onClick={() => setStreamError(null)}
              className="ml-auto text-red-500 hover:text-red-400"
            >
              ✕
            </button>
          </div>
        </div>
      )}

      {/* Input Area */}
      <div className="p-4 md:p-6 bg-gradient-to-t from-obsidian-950/90 via-obsidian-950/50 to-transparent">
        <form 
            onSubmit={handleSubmit} 
            className={`max-w-4xl mx-auto glass-input rounded-2xl p-2 flex items-end gap-2 shadow-2xl border transition-all duration-300 relative ${
                inputError 
                ? 'border-red-500/50 shadow-[0_0_20px_rgba(239,68,68,0.25)] animate-shake' 
                : 'border-white/10 focus-within:border-air-500/30'
            }`}
        >
          <button type="button" className="p-3 text-slate-400 hover:text-white hover:bg-white/10 rounded-xl transition-colors">
              <Paperclip className="w-5 h-5" />
          </button>
          
          <div className="flex-1 py-3">
            <input
                type="text"
                    ref={inputRef}
                value={input}
                onChange={(e) => {
                    setInput(e.target.value);
                    if(inputError) setInputError(false);
                }}
                placeholder={inputError ? "Message cannot be empty..." : "Send a message to the Core..."}
                className={`w-full bg-transparent border-none outline-none text-white placeholder-slate-500 resize-none ${inputError ? 'placeholder-red-400/50' : ''}`}
            />
          </div>
          
          {/* Debug: Retry button conditions */}
          <div className="absolute -top-6 left-0 text-[9px] font-mono text-slate-600 opacity-50">
            retryAvail:{String(retryAvailable)} hasLast:{String(!!lastRequestRef.current)} thinking:{String(isThinking)}
          </div>
          
          {isThinking && abortControllerRef.current ? (
            <button 
              type="button"
              onClick={() => {
                if (abortControllerRef.current) {
                  abortControllerRef.current.abort();
                }
              }}
              className="p-3 rounded-xl transition-all shadow-lg bg-red-600 text-white hover:bg-red-700 shadow-red-600/20"
              title="Stop generating"
            >
              <Square className="w-5 h-5" />
            </button>
          ) : (lastRequestRef.current && (retryAvailable || !!streamError)) ? (
            <button 
              type="button"
              onClick={() => {
                if (lastRequestRef.current) {
                  handleSubmit(undefined, lastRequestRef.current);
                }
              }}
              className="p-3 rounded-xl transition-all shadow-lg bg-amber-600 text-white hover:bg-amber-700 shadow-amber-600/20"
              title="Retry last request"
            >
              <RotateCw className="w-5 h-5" />
            </button>
          ) : (
            <button 
              type="submit" 
              disabled={isThinking}
              className={`p-3 rounded-xl transition-all shadow-lg ${
                  isThinking 
                  ? 'bg-slate-800 text-slate-500 cursor-not-allowed' 
                  : 'bg-gradient-to-tr from-air-600 to-amber-600 text-white hover:brightness-110 shadow-air-600/20'
              }`}
            >
                <Send className="w-5 h-5" />
            </button>
          )}
        </form>
        <div className="text-center mt-3 flex items-center justify-center gap-2">
            <span className="w-1.5 h-1.5 rounded-full bg-emerald-500 shadow-[0_0_5px_rgba(16,185,129,0.5)]"></span>
            <span className="text-[10px] text-slate-600 font-mono uppercase tracking-widest">
                System Secure • AES-256 Encrypted
            </span>
        </div>
      </div>

      {/* B2.5: Save confirmation modal */}
      {isSaveModalOpen && (
        <div className="fixed inset-0 bg-black/60 flex items-center justify-center z-50" onClick={() => setIsSaveModalOpen(false)}>
          <div className="glass-card p-6 rounded-2xl max-w-md w-full mx-4 border border-white/10 shadow-2xl" onClick={(e) => e.stopPropagation()}>
            <h3 className="text-lg font-semibold text-white mb-4">Save to Memory Bank?</h3>
            <div className="space-y-4">
              <div>
                <label className="block text-sm text-slate-300 mb-2">Note</label>
                <textarea
                  value={saveText}
                  onChange={(e) => setSaveText(e.target.value)}
                  className="w-full glass-input p-3 rounded-lg text-white bg-white/5 border border-white/10 focus:border-air-500/50 focus:outline-none resize-none"
                  rows={4}
                  placeholder="Note text..."
                />
              </div>
              <div>
                <label className="block text-sm text-slate-300 mb-2">Tag (optional)</label>
                <input
                  type="text"
                  value={saveTag}
                  onChange={(e) => setSaveTag(e.target.value)}
                  className="w-full glass-input p-3 rounded-lg text-white bg-white/5 border border-white/10 focus:border-air-500/50 focus:outline-none"
                  placeholder="manual"
                />
              </div>
              <div className="text-xs text-slate-400">Type: note (fixed)</div>
              <div className="flex gap-3 justify-end pt-2">
                <button
                  onClick={() => setIsSaveModalOpen(false)}
                  className="px-4 py-2 rounded-lg text-sm text-slate-300 hover:text-white hover:bg-white/10 transition-colors"
                >
                  Cancel
                </button>
                <button
                  onClick={handleConfirmSave}
                  disabled={!saveText || saveText.trim().length < 5}
                  className="px-4 py-2 rounded-lg text-sm font-medium text-white bg-air-600 hover:bg-air-700 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
                >
                  Save
                </button>
              </div>
            </div>
          </div>
        </div>
      )}

      {/* B2.5: Save toast notification */}
      {saveToast && (
        <div className="fixed bottom-4 right-4 glass-card px-4 py-3 rounded-lg border border-emerald-500/30 bg-emerald-500/10 text-emerald-400 z-50 animate-fade-in">
          {saveToast}
        </div>
      )}
    </div>
  );
};

export default Chat;