
import React, { useState, useEffect, useRef, useCallback } from "react";
import { useSettings } from "../hooks/useSettings";
import { useAir4 } from '../contexts/Air4Context';
import { Message, MemoryItem, RouterDecision, SystemStats, ResponseStyle, ModelName, ModelMode } from '../types';
import { Send, Mic, Paperclip, BrainCircuit, Cpu, Sparkles, Activity, Database, Circle, ChevronDown, Check, Star, Copy, ClipboardCheck, Square, Pin, PinOff, Eye, EyeOff, RotateCw } from 'lucide-react';

interface ChatProps {
    sessionId: string | null;
    initialQuery?: string;
    clearInitialQuery?: () => void;
    onSessionChange?: (id: string) => void;
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


const Chat: React.FC<ChatProps> = ({ sessionId, initialQuery, clearInitialQuery, onSessionChange }) => {
  console.debug('[CHAT MOUNT]', window.location.href);
  const { settings, setSettings } = useSettings();
  const air4 = useAir4();

  const [messages, setMessages] = useState<Message[]>([]);
  const [input, setInput] = useState('');
  const [isThinking, setIsThinking] = useState(false);
  const [routerState, setRouterState] = useState<RouterDecision | null>(null);
  const [stats, setStats] = useState<SystemStats | null>(null);
  const [lastStatsTime, setLastStatsTime] = useState<number>(Date.now());
  const [timeAgo, setTimeAgo] = useState(0);
  const [responseStyle, setResponseStyle] = useState<ResponseStyle>(air4.getResponseStyle());
  const [showStyleMenu, setShowStyleMenu] = useState(false);
  const [modelMode, setModelMode] = useState<ModelMode>(settings.modelMode || 'auto');
  const [showModelModeMenu, setShowModelModeMenu] = useState(false);
  const modelModeMenuRef = useRef<HTMLDivElement>(null);
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
  const styleMenuRef = useRef<HTMLDivElement>(null);
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const messagesContainerRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLInputElement | null>(null);
  const autoBrainstormRef = useRef(false);
  const abortControllerRef = useRef<AbortController | null>(null);
  const requestIdRef = useRef(0);
  const sessionFetchAbortControllerRef = useRef<AbortController | null>(null);
  const lastRequestRef = useRef<{ text: string; session_id: string; settings: any; botMsgId: string } | null>(null);
  const persistThrottleRef = useRef<NodeJS.Timeout | null>(null);
  const scrollThrottleRef = useRef<NodeJS.Timeout | null>(null);
  const lastPersistTimeRef = useRef<number>(0);

  // Load session messages when ID changes
  useEffect(() => {
      // Cancel any in-flight session fetch
      if (sessionFetchAbortControllerRef.current) {
          sessionFetchAbortControllerRef.current.abort();
      }

      if (!sessionId) {
          setMessages([]);
          setSavedMessageIds(new Set());
          setUsedMemory({});
          setUsedMemoryQueries({});
          setPinnedMemoryIds(new Set());
          setSourcesOpen({});
          return;
      }

      // Guard: only call getSessionById if session ID is valid (from backend POST /sessions)
      if (!air4.isValidSessionId(sessionId)) {
          console.warn('[CHAT] Invalid session ID, skipping getSessionById:', sessionId);
          setMessages([]);
          setSavedMessageIds(new Set());
          setUsedMemory({});
          setUsedMemoryQueries({});
          setPinnedMemoryIds(new Set());
          setSourcesOpen({});
          return;
      }

      console.debug('[CHAT] sessionId', sessionId);

      // Create new AbortController for this fetch
      const abortController = new AbortController();
      sessionFetchAbortControllerRef.current = abortController;
      const currentSessionId = sessionId; // Capture for race check

      (async () => {
          try {
              console.debug('[CHAT] fetching session from API', currentSessionId);
              const s = await air4.getSessionById(currentSessionId, abortController.signal);
              
              // Race check: only update if sessionId hasn't changed
              if (abortController.signal.aborted || currentSessionId !== sessionId) {
                  console.debug('[CHAT] session fetch aborted or session changed, ignoring response');
                  return;
              }
              
              console.debug('[CHAT] fetched', { id: s.id, messages: s.messages?.length });
              setMessages(s.messages || []);
              air4.upsertSession(s);
          } catch (e: any) {
              // Ignore AbortError (expected when session changes)
              if (e.name === 'AbortError' || e.message?.includes('aborted')) {
                  console.debug('[CHAT] session fetch aborted');
                  return;
              }
              
              // Handle 404 "Session not found" - create new session and update URL/localStorage
              const is404 = e.message === 'Session not found' || (e.message?.includes && e.message.includes('Session not found'));
              if (is404 && currentSessionId === sessionId) {
                  console.warn('[session] invalid sessionId -> created new', currentSessionId);
                  try {
                      const newSession = await air4.createSession('');
                      const newSessionId = newSession.id;
                      
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
              // Only set empty messages if this is still the current session
              if (currentSessionId === sessionId) {
                  setMessages([]);
              }
          } finally {
              // Only clear state if this is still the current session
              if (currentSessionId === sessionId) {
                  setSavedMessageIds(new Set());
                  setUsedMemory({});
                  setUsedMemoryQueries({});
                  setPinnedMemoryIds(new Set());
                  setSourcesOpen({});
              }
          }
      })();

      return () => {
          // Cleanup: abort fetch if component unmounts or sessionId changes
          if (sessionFetchAbortControllerRef.current) {
              sessionFetchAbortControllerRef.current.abort();
          }
      };
  }, [sessionId, air4]);

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

  const handleSaveMemory = async (msg: Message) => {
      if (savedMessageIds.has(msg.id)) return;
      const success = await air4.addManualMemory(msg.content, 'chat-selection');
      if (success) {
          setSavedMessageIds(prev => new Set(prev).add(msg.id));
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

      // Параллельный запрос к памяти для RAG источников
      const memorySearchPromise = (async () => {
        if (rid !== requestIdRef.current) return; // Защита от гонок
        if (!currentSessionId) return; // No session, skip memory search
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
        await air4.chatStream(
          {
            text: requestText,
            session_id: currentSessionId,
            settings: cleanedSettings
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
            onDone: () => {
              // Защита от гонок: проверяем, что это еще актуальный запрос
              if (rid !== requestIdRef.current) return;
              
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
                  console.warn('[Chat] Failed to persist on done', e);
                }
                
                return finalMessages;
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
        const streamChatSettings = {
          temperature: backendSettings.temperature,
          responseTone: backendSettings.response_tone,
          outputDensity: backendSettings.output_density,
          interfaceLanguage: backendSettings.interface_language,
          activeModel: backendSettings.model || backendSettings.active_model,
        };
        const cleanedStreamChatSettings = clean(streamChatSettings);
        console.log("[CHAT SEND settings]", cleanedStreamChatSettings);
        const stream = air4.streamChat(newMessages, sessionId, cleanedStreamChatSettings);
        
        let context: MemoryItem[] | undefined = undefined;
        let decision: RouterDecision | undefined = undefined;

        for await (const part of stream) {
          // Защита от гонок: проверяем, что это еще актуальный запрос
          if (rid !== requestIdRef.current) break;
          
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
      <div ref={messagesContainerRef} className="flex-1 overflow-y-auto p-4 md:p-8 space-y-6 custom-scrollbar scroll-smooth">
        {messages.map((msg) => {
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

          return (
          <div 
            key={msg.id} 
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

                {/* RAG Context */}
                {msg.role === 'assistant' && msg.contextUsed && msg.contextUsed.length > 0 && (
                    <div className="mb-3 flex flex-col gap-1 pb-3 border-b border-white/5">
                        <div className="flex items-center gap-1 text-[10px] font-bold text-air-400 uppercase tracking-wider">
                            <BrainCircuit className="w-3 h-3" /> Memory Retrieval
                        </div>
                        {msg.contextUsed.map((m, idx) => (
                            <div key={idx} className="text-[10px] text-slate-400 truncate bg-white/5 px-2 py-1.5 rounded flex items-center gap-2 border border-white/5">
                                <span className="w-1 h-1 bg-air-500 rounded-full"></span>
                                {m.content}
                            </div>
                        ))}
                    </div>
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
    </div>
  );
};

export default Chat;