
import React, { useState, useEffect, useRef, useCallback } from "react";
import { useSettings } from "../hooks/useSettings";
import { air4 } from '../services/air4Service';
import { Message, MemoryItem, RouterDecision, SystemStats, ResponseStyle } from '../types';
import { Send, Mic, Paperclip, BrainCircuit, Cpu, Sparkles, Activity, Database, Circle, ChevronDown, Check, Star, Copy, ClipboardCheck, PinOff } from 'lucide-react';

interface ChatProps {
    sessionId?: string | null; // Опциональный, Chat.tsx сам управляет sessionId
    initialQuery?: string;
    clearInitialQuery?: () => void;
}

const STORAGE_KEY_ACTIVE_SESSION = 'air4.activeSessionId';

const Chat: React.FC<ChatProps> = ({ sessionId: propSessionId, initialQuery, clearInitialQuery }) => {
  const { settings } = useSettings();
  
  // Единый источник правды для sessionId
  const [sessionId, setSessionId] = useState<string | null>(null);

  const [messages, setMessages] = useState<Message[]>([]);
  const [input, setInput] = useState('');
  const [isThinking, setIsThinking] = useState(false);
  const [routerState, setRouterState] = useState<RouterDecision | null>(null);
  const [stats, setStats] = useState<SystemStats | null>(null);
  const [lastStatsTime, setLastStatsTime] = useState<number>(Date.now());
  const [timeAgo, setTimeAgo] = useState(0);
  const [responseStyle, setResponseStyle] = useState<ResponseStyle>(air4.getResponseStyle());
  const [showStyleMenu, setShowStyleMenu] = useState(false);
  const [inputError, setInputError] = useState(false);
  const [savedMessageIds, setSavedMessageIds] = useState<Set<string>>(new Set());
  const [copiedId, setCopiedId] = useState<string | null>(null);
  const styleMenuRef = useRef<HTMLDivElement>(null);
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLInputElement | null>(null);
  const autoBrainstormRef = useRef(false);

  // ---- Noisy memory guard (facts-only) ----
  const SMALLTALK_RE = /\b(привет|здаров|здравствуйте|hi|hello|hey|спасибо|thx|ok|ок|ага|понял|ясно|норм|нормально|класс|лол|ха-ха|как дела|как ты|как у тебя дела)\b/i;

  const isQuestionLike = (text: string) => {
    const t = (text || '').trim();
    if (!t) return false;
    if (t.includes('?')) return true;
    return /^(что|как|почему|когда|где|зачем|можно ли|подскажи|расскажи|объясни)\b/i.test(t);
  };

  const isTooShort = (text: string) => ((text || '').trim().length < 22);

  const isNoisyMemory = (text: string) => {
    const t = (text || '').trim();
    if (!t) return true;
    if (SMALLTALK_RE.test(t)) return true;
    if (isQuestionLike(t)) return true;
    if (isTooShort(t)) return true;
    return false;
  };
  // ----------------------------------------

  // Pinned facts should be stored as real facts (so they appear in Memory Bank → FACTS)
  const PIN_SOURCE = 'rag_pin';

  // Утилита для обновления sessionId в URL с сохранением всех query params
  const setUrlSessionId = useCallback((id: string) => {
      console.debug('[URL] before', window.location.href);
      const url = new URL(window.location.href);
      url.searchParams.set('session', id);
      const newUrlString = url.toString();
      window.history.replaceState({}, '', newUrlString);
      console.debug('[URL] after', window.location.href);
  }, []);

  // Инициализация sessionId с приоритетом: prop → URL → localStorage → создание новой
  useEffect(() => {
      const initializeSessionId = async () => {
          // ВАЖНО: сначала загружаем все сессии с сервера
          console.debug('[Chat.tsx] Initializing: refreshing sessions from API');
          await air4.refreshSessions();
          
          let selectedId: string | null = null;
          
          // Приоритет 0: prop
          if (propSessionId) {
              selectedId = propSessionId;
              console.debug('[Chat.tsx] Using propSessionId:', propSessionId);
          }
          // Приоритет 1: URL параметр ?session=
          else {
              const urlParams = new URLSearchParams(window.location.search);
              const urlSessionId = urlParams.get('session');
              if (urlSessionId) {
                  selectedId = urlSessionId;
                  console.debug('[Chat.tsx] Found sessionId in URL:', urlSessionId);
              }
          }
          
          // Приоритет 2: localStorage (G1: activeSessionId only)
          if (!selectedId) {
              const storedSessionId = localStorage.getItem(STORAGE_KEY_ACTIVE_SESSION);
              if (storedSessionId && air4.isValidSessionId(storedSessionId)) {
                  // Validate against backend sessions list
                  const sessions = air4.getSessions();
                  const sessionExists = sessions.some(s => s.id === storedSessionId);
                  if (sessionExists) {
                      selectedId = storedSessionId;
                      console.debug('[Chat.tsx] Found valid sessionId in localStorage:', storedSessionId);
                  } else {
                      // Invalid sessionId, remove it
                      localStorage.removeItem(STORAGE_KEY_ACTIVE_SESSION);
                      console.debug('[Chat.tsx] Removed invalid sessionId from localStorage:', storedSessionId);
                  }
              }
          }
          
          // Приоритет 3: первая сессия из backend или создание новой
          if (!selectedId) {
              const sessions = air4.getSessions();
              if (sessions.length > 0) {
                  selectedId = sessions[0].id;
                  console.debug('[Chat.tsx] Using first session from backend:', selectedId);
              } else {
                  console.debug('[Chat.tsx] No sessions found, creating new session');
                  const newSession = await air4.createSession('');
                  selectedId = newSession.id;
              }
          }
          
          // Устанавливаем id и всегда обновляем URL
          setSessionId(selectedId);
          console.debug('[Chat.tsx] sessionId set', selectedId);
          localStorage.setItem(STORAGE_KEY_ACTIVE_SESSION, selectedId);
          setUrlSessionId(selectedId);
          console.debug('[Chat.tsx] SessionId initialized:', { 
              selectedId, 
              urlUpdated: true,
              windowLocationHref: window.location.href,
              windowLocationSearch: window.location.search
          });
      };
      
      // Инициализируем только если sessionId еще не установлен
      if (!sessionId) {
          initializeSessionId();
      } else if (propSessionId && propSessionId !== sessionId) {
          // Если propSessionId изменился извне - обновляем
          console.debug('[Chat.tsx] Updating sessionId from prop:', propSessionId);
          setSessionId(propSessionId);
          console.debug('[Chat.tsx] sessionId set', propSessionId);
          localStorage.setItem(STORAGE_KEY_ACTIVE_SESSION, propSessionId);
          setUrlSessionId(propSessionId);
      }
  }, [propSessionId, sessionId]); // Зависимость от propSessionId и sessionId

  // Защита: сохраняем session param при изменениях URL через popstate
  useEffect(() => {
      if (!sessionId) return;
      
      const checkAndRestoreSession = () => {
          const urlParams = new URLSearchParams(window.location.search);
          const currentSession = urlParams.get('session');
          
          // Если session param отсутствует или отличается - восстанавливаем
          if (currentSession !== sessionId) {
              console.debug('[Chat.tsx] URL session param missing or changed, restoring', { 
                  currentSession, 
                  expectedSession: sessionId,
                  currentUrl: window.location.href
              });
              setUrlSessionId(sessionId);
          }
      };
      
      // Слушаем изменения URL через popstate (навигация назад/вперед)
      window.addEventListener('popstate', checkAndRestoreSession);
      
      return () => {
          window.removeEventListener('popstate', checkAndRestoreSession);
      };
  }, [sessionId, setUrlSessionId]); // Следим за sessionId и setUrlSessionId

  // Load session messages when ID changes
  useEffect(() => {
      if (sessionId) {
          console.debug('[Chat.tsx] Loading session:', { sessionId });
          
          // Сначала проверяем локальный кэш
          const localSession = air4.getSession(sessionId);
          if (localSession && localSession.messages && localSession.messages.length > 0) {
              console.debug('[Chat.tsx] Using local session cache', { 
                  messagesCount: localSession.messages.length 
              });
              setMessages(localSession.messages);
              setSavedMessageIds(new Set()); // Reset local saved state on session change
              return;
          }
          
          // Если в кэше нет или нет сообщений - загружаем с сервера
          console.debug('[Chat.tsx] Loading session from API:', { sessionId });
          (async () => {
              const session = await air4.getSessionById(sessionId);
              if (session) {
                  console.debug('[Chat.tsx] Session loaded from API', { 
                      id: session.id,
                      title: session.title,
                      messagesCount: session.messages?.length || 0
                  });
                  // upsertSession уже вызван внутри getSessionById
                  setMessages(session.messages || []);
              } else {
                  // Session doesn't exist on server - create new
                  console.debug('[Chat.tsx] Session not found on server, creating new');
                  const newSession = air4.createSession('');
                  setSessionId(newSession.id);
                  localStorage.setItem(STORAGE_KEY_ACTIVE_SESSION, newSession.id);
                  setUrlSessionId(newSession.id);
                  setMessages(newSession.messages || []);
              }
              setSavedMessageIds(new Set()); // Reset local saved state on session change
          })();
      }
  }, [sessionId]);

  // Handle outside click for style menu
  useEffect(() => {
      const handleClickOutside = (event: MouseEvent) => {
          if (styleMenuRef.current && !styleMenuRef.current.contains(event.target as Node)) {
              setShowStyleMenu(false);
          }
      };
      document.addEventListener('mousedown', handleClickOutside);
      return () => document.removeEventListener('mousedown', handleClickOutside);
  }, []);

  // Poll for system stats to update header
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
    const interval = setInterval(fetchStats, 5000); // Update every 5 seconds
    return () => clearInterval(interval);
  }, []);

  // Update time ago counter
  useEffect(() => {
      const timer = setInterval(() => {
          setTimeAgo(Math.floor((Date.now() - lastStatsTime) / 1000));
      }, 1000);
      return () => clearInterval(timer);
  }, [lastStatsTime]);

  const scrollToBottom = () => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  };

  useEffect(() => {
    scrollToBottom();
  }, [messages, routerState, isThinking]);

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

  const handleSaveMemory = async (msg: Message) => {
      if (savedMessageIds.has(msg.id)) return;

      // By default save the message content
      let textToSave = String(msg.content ?? '').trim();

      // If starring an assistant message, prefer the previous user message like "Запомни: ..." / "Remember: ..."
      if (msg.role === 'assistant') {
          const idx = messages.findIndex(m => m.id === msg.id);
          const prev = idx > 0 ? messages[idx - 1] : null;

          if (prev?.role === 'user') {
              const raw = String(prev.content ?? '').trim();
              // Accept variants like: "Запомни:", "\"Запомни: ...\"", "«Повтори и запомни полностью: ...»", "Remember: ..."
              const rememberRe = /^\s*[«"'”]?\s*(?:повтори\s+и\s+)?(запомни|запомнить|remember)\b[:\s—-]*/i;
              if (rememberRe.test(raw)) {
                  const cleaned = raw.replace(rememberRe, '').trim();
                  if (cleaned) textToSave = cleaned;
              }
          }
      }

      // Facts-only: do not store smalltalk/questions/too-short lines
      if (isNoisyMemory(textToSave)) {
          console.warn('[memory] blocked noisy memory:', textToSave);
          return;
      }

      console.debug('[Chat.tsx] handleSaveMemory: saving fact', { 
          sessionId, 
          messageId: msg.id, 
          textToSave, 
          source: PIN_SOURCE 
      });
      const success = await air4.addManualMemory(textToSave, PIN_SOURCE);
      console.debug('[Chat.tsx] handleSaveMemory: result', { success });
      if (success) {
          setSavedMessageIds(prev => new Set(prev).add(msg.id));
      }
  };

  // Extract payload from a "remember" style message.
  const getRememberPayload = (rawText: string) => {
      const raw = String(rawText ?? '').trim();
      const rememberRe = /^\s*[«"'”]?\s*(?:повтори\s+и\s+)?(запомни|запомнить|remember)\b[:\s—-]*/i;
      return rememberRe.test(raw) ? raw.replace(rememberRe, '').trim() : raw;
  };

  // Save user's own message into memory as a pinned fact (useful when the fact is only in the user text).
  const handleSaveUserMemory = async (msg: Message) => {
      if (savedMessageIds.has(msg.id)) return;

      // Сохраняем именно исходный текст user-сообщения
      let textToSave = String(msg.content ?? '').trim();

      // Нормализуем: если текст начинается с "Запомни:" / "Запомни," - вырезаем префикс и пробелы
      const rememberPrefixRe = /^\s*(?:запомни|запомнить|remember)[:,]\s*/i;
      if (rememberPrefixRe.test(textToSave)) {
          textToSave = textToSave.replace(rememberPrefixRe, '').trim();
      }

      // Facts-only: do not store smalltalk/questions/too-short lines
      if (isNoisyMemory(textToSave)) {
          console.warn('[memory] blocked noisy memory:', textToSave);
          return;
      }

      console.debug('[Chat.tsx] handleSaveUserMemory: saving fact', { 
          sessionId, 
          messageId: msg.id, 
          textToSave, 
          source: PIN_SOURCE 
      });
      const success = await air4.addManualMemory(textToSave, PIN_SOURCE);
      console.debug('[Chat.tsx] handleSaveUserMemory: result', { success });
      if (success) {
          setSavedMessageIds(prev => new Set(prev).add(msg.id));
          console.log('[memory] saved user message as fact:', textToSave);
      }
  };

  const handleCopy = (text: string, id: string) => {
      navigator.clipboard.writeText(text);
      setCopiedId(id);
      setTimeout(() => setCopiedId(null), 2000);
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    
    // Input Validation
    if (!input.trim()) {
        setInputError(true);
        setTimeout(() => setInputError(false), 3000);
        return;
    }

    if (isThinking || !sessionId) return;
    
    setInputError(false);

    const userMsg: Message = {
      id: Date.now().toString(),
      role: 'user',
      content: input,
      timestamp: Date.now()
    };

    const newMessages = [...messages, userMsg];
    setMessages(newMessages);
    setInput('');
    setIsThinking(true);
    setRouterState(null);

    try {
  console.log('[CHAT settings]', settings);

  // Собираем coreSettings для бэкенда:
  // берём стиль/температуру из settings,
  // а активную модель — напрямую из air4 (там свежий конфиг из localStorage)
  const coreSettings = {
    temperature: (settings as any).temperature,
    responseTone: (settings as any).responseTone,
    outputDensity: (settings as any).outputDensity,
    interfaceLanguage: (settings as any).interfaceLanguage,
    activeModel: air4.getActiveModel(),
  };

  console.debug('[Chat.tsx] handleSubmit: starting streamChat', { 
      sessionId, 
      messagesCount: newMessages.length,
      lastMessage: newMessages[newMessages.length - 1]?.content?.slice(0, 50)
  });
  const stream = air4.streamChat(newMessages, sessionId, coreSettings);
      
  const botMsgId = (Date.now() + 1).toString();
  // ...
      // Placeholder for bot message — контент появится по мере прихода чанков
      setMessages(prev => [...prev, {
        id: botMsgId,
        role: 'assistant',
        content: '',
        timestamp: Date.now()
      }]);

      let fullContent = '';
      let context: MemoryItem[] | undefined = undefined;
      let decision: RouterDecision | undefined = undefined;

      for await (const part of stream) {
        // Обработка нового sessionId (если сессия была создана)
        if (part.newSessionId) {
            console.debug('[Chat.tsx] Received newSessionId from streamChat:', part.newSessionId);
            setSessionId(part.newSessionId);
            localStorage.setItem(STORAGE_KEY_ACTIVE_SESSION, part.newSessionId);
            setUrlSessionId(part.newSessionId);
        }
        
        if (part.decision) {
            decision = part.decision;
            setRouterState(decision);
             setMessages(prev => prev.map(m => 
                m.id === botMsgId 
                    ? { ...m, modelUsed: decision?.model, domain: decision?.domain } 
                    : m
            ));
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
            setMessages(prev => prev.map(m => 
            m.id === botMsgId 
                ? { ...m, content: fullContent } 
                : m
            ));
        }
      }

    } catch (error) {
      console.error("Stream error", error);
    } finally {
      setIsThinking(false);
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

  // Что показывать в шапке как имя модели
  const headerModelName =
    routerState?.model ||
    stats?.modelName ||
    air4.getActiveModel() ||
    (isOffline ? 'Demo / Offline' : 'Mistral-7B');

  // Жива ли память
  const memoryActive = !isOffline;

  const styles: { id: ResponseStyle; label: string }[] = [
      { id: 'short', label: 'Short' },
      { id: 'normal', label: 'Normal' },
      { id: 'detailed', label: 'Detailed' },
  ];

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
          {/* 1. Style Selector */}
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

          {/* 2. Core Status */}
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

          {/* 3. Model Info */}
          <div className="hidden md:flex items-center gap-2 px-3">
            <Cpu className="w-3.5 h-3.5 text-air-500" />
            <span className="text-[11px] font-mono text-slate-200">
              {headerModelName}
            </span>
          </div>

          {/* 4. Memory Status */}
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

          {/* 5. Index Update */}
          <div className="hidden xl:flex items-center gap-2 px-3">
            <Activity className="w-3.5 h-3.5 text-slate-500" />
            <span className="text-[11px] font-mono text-slate-400">
              {stats ? `${timeAgo}s ago` : '...'}
            </span>
          </div>
        </div>
      </div>

      {/* Messages Area */}
      <div className="flex-1 overflow-y-auto p-4 md:p-8 space-y-6 custom-scrollbar scroll-smooth">
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
                {isAssistant && (modelFromPrefix || msg.modelUsed) && (
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
  {modelFromPrefix || msg.modelUsed}
</span>
                    </div>
                )}

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
                        {(() => {
                            // Compute candidate and noisy, following handleSaveMemory logic for assistant messages
                            const idx = messages.findIndex(m => m.id === msg.id);
                            const prev = idx > 0 ? messages[idx - 1] : null;
                            let candidate = String(msg.content ?? '').trim();
                            if (prev?.role === 'user') {
                                const cleaned = getRememberPayload(String(prev.content ?? '')).trim();
                                if (cleaned) candidate = cleaned;
                            }
                            const noisy = isNoisyMemory(candidate);

                            return (
                              <>
                                {noisy && (
                                    <span
                                        className="inline-flex items-center gap-1 px-2 py-0.5 rounded-md text-[10px] bg-white/5 text-slate-400 border border-white/10"
                                        title="Not a fact (short/smalltalk/question)"
                                    >
                                        <PinOff className="w-3 h-3" /> Not a fact
                                    </span>
                                )}
                                <button 
                                    onClick={() => handleSaveMemory(msg)}
                                    disabled={noisy}
                                    className={`p-1.5 rounded-lg transition-all ${
                                        noisy
                                        ? 'bg-white/5 text-slate-600 cursor-not-allowed'
                                        : savedMessageIds.has(msg.id)
                                          ? 'bg-air-500/10 text-air-500'
                                          : 'hover:bg-white/10 text-slate-500 hover:text-air-400'
                                    }`}
                                    title={noisy ? 'Not a fact (short/smalltalk/question)' : 'Send to Memory Bank'}
                                >
                                    <Star className={`w-3.5 h-3.5 ${(!noisy && savedMessageIds.has(msg.id)) ? 'fill-air-500' : ''}`} />
                                </button>
                                <button 
                                    onClick={() => handleCopy(msg.content, msg.id)}
                                    className="p-1.5 hover:bg-white/10 rounded-lg text-slate-500 hover:text-white transition-colors"
                                    title="Copy to Clipboard"
                                >
                                    {copiedId === msg.id ? <ClipboardCheck className="w-3.5 h-3.5 text-emerald-500" /> : <Copy className="w-3.5 h-3.5" />}
                                </button>
                              </>
                            );
                        })()}
                    </div>
                )}
                {/* User Actions Footer */}
                {msg.role === 'user' && !isThinking && (
                    <div className="mt-3 pt-2 border-t border-white/5 flex items-center gap-2 opacity-60 hover:opacity-100 transition-opacity">
                        {(() => {
                            const candidate = getRememberPayload(String(msg.content ?? '')).trim();
                            const noisy = isNoisyMemory(candidate);

                            return (
                              <>
                                {noisy && (
                                    <span
                                        className="inline-flex items-center gap-1 px-2 py-0.5 rounded-md text-[10px] bg-white/5 text-slate-400 border border-white/10"
                                        title="Not a fact (short/smalltalk/question)"
                                    >
                                        <PinOff className="w-3 h-3" /> Not a fact
                                    </span>
                                )}
                                <button
                                    onClick={() => handleSaveUserMemory(msg)}
                                    disabled={noisy}
                                    className={`p-1.5 rounded-lg transition-all ${
                                        noisy
                                        ? 'bg-white/5 text-slate-600 cursor-not-allowed'
                                        : savedMessageIds.has(msg.id)
                                          ? 'bg-air-500/10 text-air-500'
                                          : 'hover:bg-white/10 text-slate-500 hover:text-air-400'
                                    }`}
                                    title={noisy ? 'Not a fact (short/smalltalk/question)' : 'Save as fact'}
                                >
                                    <Star className={`w-3.5 h-3.5 ${(!noisy && savedMessageIds.has(msg.id)) ? 'fill-air-500' : ''}`} />
                                </button>
                                <button
                                    onClick={() => handleCopy(String(msg.content ?? ''), msg.id)}
                                    className="p-1.5 hover:bg-white/10 rounded-lg text-slate-500 hover:text-white transition-colors"
                                    title="Copy to Clipboard"
                                >
                                    {copiedId === msg.id ? <ClipboardCheck className="w-3.5 h-3.5 text-emerald-500" /> : <Copy className="w-3.5 h-3.5" />}
                                </button>
                              </>
                            );
                        })()}
                    </div>
                )}
            </div>
          </div>
        ); })}

        
        <div ref={messagesEndRef} />
      </div>

      {/* Input Area */}
      <div className="p-4 md:p-6 bg-gradient-to-t from-obsidian-950/90 via-obsidian-950/50 to-transparent">
        <form 
            onSubmit={handleSubmit} 
            className={`max-w-4xl mx-auto glass-input rounded-2xl p-2 flex items-end gap-2 shadow-2xl border transition-all duration-300 ${
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