
import { Agent, MemoryItem, Message, SystemStats, RouterDecision, AppState, Domain, IngestItem, Send3Out, ChatSession, ModelName, ResponseStyle, Language, IngestMode } from '../types';

// API base URL (prefer Vite env; fallback for legacy/static builds)
const API_BASE_URL = (import.meta as any)?.env?.VITE_API_BASE_URL ?? 'http://127.0.0.1:8000';
const STORAGE_KEY_CONFIG = 'air4_config';
const STORAGE_KEY_SESSIONS = 'air4_sessions';

export interface Fact {
  id?: string;
  subject: string;
  predicate: string;
  object: string;
  timestamp: number;
  source_session?: string | null;
  source_message_id?: string | null;
}

// Initial Agents / Modules aligned with Domains
export const AVAILABLE_AGENTS: Agent[] = [
  { id: 'general', name: 'Prime Core', description: 'General logic, reasoning.', icon: 'Cpu', systemPrompt: 'You are AIr4.', domain: 'general', enabled: true },
  { id: 'fitness', name: 'Bio-Monitor', description: 'Health & metrics.', icon: 'Activity', systemPrompt: 'Focus on physiology.', domain: 'fitness', enabled: false },
  { id: 'finance', name: 'Ledger', description: 'Budget & market analysis.', icon: 'DollarSign', systemPrompt: 'Focus on finance.', domain: 'finance', enabled: false },
  { id: 'code', name: 'Dev-Ops', description: 'Code & debugging.', icon: 'Terminal', systemPrompt: 'Focus on code.', domain: 'code', enabled: false },
];

export const AVAILABLE_MODELS: ModelName[] = [
    'Mistral-7B',
    'Hermes-7B',
    'LLaMA-3.1-8B',
    'Qwen-2.5-14B',
    'Mixtral-8x7B',
    'DeepSeek-32B',
    'DeepSeek-14B'
];

interface Air4Config {
    setupComplete: boolean;
    agents: Agent[];
    userName: string;
    activeModel: ModelName;
    responseStyle: ResponseStyle;
    language: Language;
    ingestMode: IngestMode;
    autoTitleSessions: boolean;
}

class Air4Service {
  private config: Air4Config;
  private appState: AppState = AppState.ACTIVE;
  private isOfflineMode: boolean = false;
  private lastHealthCheck: number = 0;
  private sessions: ChatSession[] = [];

  constructor() {
    const savedConfig = localStorage.getItem(STORAGE_KEY_CONFIG);
    if (savedConfig) {
      const parsed = JSON.parse(savedConfig);
      this.config = {
          setupComplete: parsed.setupComplete || false,
          agents: parsed.agents || AVAILABLE_AGENTS,
          userName: parsed.userName || '',
          activeModel: parsed.activeModel || 'Mistral-7B',
          responseStyle: parsed.responseStyle || 'normal',
          language: parsed.language || 'auto',
          ingestMode: parsed.ingestMode || 'smart',
          autoTitleSessions: parsed.autoTitleSessions !== undefined ? parsed.autoTitleSessions : true
      };
    } else {
      this.config = { 
          setupComplete: false, 
          agents: AVAILABLE_AGENTS, 
          userName: '', 
          activeModel: 'Mistral-7B', 
          responseStyle: 'normal',
          language: 'auto',
          ingestMode: 'smart',
          autoTitleSessions: true
      };
    }

    // Загружаем сессии из localStorage при старте
    this.loadSessions();

    // If after loading there are no sessions, create an initial one
    if (this.sessions.length === 0) {
      this.createSession('Local Core Online');
    }
  }

  // --- SESSION MANAGEMENT ---

  getSessions(): ChatSession[] {
      return this.sessions.sort((a, b) => b.timestamp - a.timestamp);
  }

  getSession(id: string): ChatSession | undefined {
      const session = this.sessions.find(s => s.id === id);
      console.debug('[air4Service] getSession:', { 
          requestedId: id, 
          found: !!session, 
          sessionId: session?.id, 
          title: session?.title,
          allSessionIds: this.sessions.map(s => ({ id: s.id, title: s.title }))
      });
      return session;
  }

  async refreshSessions(): Promise<void> {
      console.debug('[air4Service] refreshSessions: fetching from API');
      const apiSessions = await this.fetchSessions();
      
      // Нормализуем все сессии и заменяем локальный кэш
      const normalizedSessions = apiSessions.map((apiSession: any) => 
          this.mapApiSessionToChatSession(apiSession)
      );
      
      this.sessions = normalizedSessions;
      this.saveSessions();
      console.debug('[air4Service] refreshSessions: updated', { 
          count: this.sessions.length,
          ids: this.sessions.map(s => s.id)
      });
  }

  async fetchSessionFromAPI(id: string): Promise<ChatSession | null> {
      const apiSessions = await this.fetchSessions();
      const apiSession = apiSessions.find((s: any) => s.id === id || s.session_id === id);
      
      if (apiSession) {
          console.debug('[air4Service] fetchSessionFromAPI: found session', { 
              apiSessionId: apiSession.id || apiSession.session_id 
          });
          const chatSession = this.mapApiSessionToChatSession(apiSession);
          this.upsertSession(chatSession);
          return chatSession;
      }
      
      return null;
  }

  async getSessionById(id: string): Promise<ChatSession | null> {
      if (this.isOfflineMode) return null;
      
      try {
          // Пробуем GET /sessions/{id}
          let res = await fetch(`${API_BASE_URL}/sessions/${id}`);
          
          // Если не сработало, пробуем query параметр
          if (!res.ok && res.status === 404) {
              res = await fetch(`${API_BASE_URL}/sessions?id=${encodeURIComponent(id)}`);
          }
          
          if (!res.ok) {
              console.debug('[air4Service] getSessionById: not found', { id, status: res.status });
              return null;
          }
          
          const data = await res.json();
          
          // Нормализуем ответ API в ChatSession
          const chatSession = this.mapApiSessionToChatSession(data);
          
          // Upsert в локальный кэш
          this.upsertSession(chatSession);
          
          console.debug('[air4Service] getSessionById: loaded', { 
              id: chatSession.id, 
              title: chatSession.title,
              messagesCount: chatSession.messages?.length || 0
          });
          
          return chatSession;
      } catch (e: any) {
          // Ignore AbortError (expected when request is cancelled)
          if (e?.name === 'AbortError' || e?.message?.includes('aborted')) {
              return null; // Return null without logging
          }
          
          // Log real network/API errors (404, 500, etc.)
          console.debug('[air4Service] getSessionById: error', e);
          return null;
      }
  }

  createSession(initialTitle: string = ''): ChatSession {
      const newSession: ChatSession = {
          id: Date.now().toString(),
          title: initialTitle || '', // Единый формат: пустая строка вместо 'New Session'
          lastMessage: '',
          timestamp: Date.now(),
          messages: [{
            id: 'init',
            role: 'assistant',
            content: 'Local Core Online. How can I assist you today?',
            timestamp: Date.now(),
            modelUsed: this.config.activeModel,
            domain: 'general'
          }]
      };
      this.sessions.unshift(newSession);
      this.saveSessions();
      return newSession;
  }

  deleteSession(id: string) {
      this.sessions = this.sessions.filter(s => s.id !== id);
      this.saveSessions();
  }

  deleteAllSessions() {
      this.sessions = [];
      this.saveSessions();
      // Immediately create a fresh one so the UI isn't empty
      this.createSession();
  }

  renameSession(id: string, newTitle: string) {
      this.updateSession(id, { title: newTitle });
  }

  duplicateSession(id: string) {
      const original = this.getSession(id);
      if (original) {
          const newSession = {
              ...original,
              id: Date.now().toString(),
              title: `${original.title} (Copy)`,
              timestamp: Date.now()
          };
          this.sessions.unshift(newSession);
          this.saveSessions();
      }
  }

  exportSession(id: string) {
      const session = this.getSession(id);
      if (session) {
          const dataStr = "data:text/json;charset=utf-8," + encodeURIComponent(JSON.stringify(session, null, 2));
          const downloadAnchorNode = document.createElement('a');
          downloadAnchorNode.setAttribute("href", dataStr);
          downloadAnchorNode.setAttribute("download", `air4_session_${id}.json`);
          document.body.appendChild(downloadAnchorNode);
          downloadAnchorNode.click();
          downloadAnchorNode.remove();
      }
  }

  private loadSessions() {
      const savedSessions = localStorage.getItem(STORAGE_KEY_SESSIONS);
      if (savedSessions) {
          try {
              const parsed = JSON.parse(savedSessions);
              // НЕ затираем this.sessions пустым массивом, если localStorage есть и парсинг успешен
              if (Array.isArray(parsed)) {
                  // Используем загруженные данные, даже если массив пустой
                  this.sessions = parsed;
                  console.debug('[air4Service] loadSessions: loaded from localStorage', { 
                      count: this.sessions.length 
                  });
              } else {
                  // Если не массив - инициализируем пустым
                  this.sessions = [];
                  console.debug('[air4Service] loadSessions: localStorage contains non-array data');
              }
          } catch (e) {
              console.warn('[air4Service] loadSessions: Failed to parse stored sessions', e);
              // При ошибке парсинга - инициализируем пустым массивом и очищаем localStorage
              this.sessions = [];
              localStorage.removeItem(STORAGE_KEY_SESSIONS);
          }
      } else {
          // Если localStorage пуст - инициализируем пустым массивом
          this.sessions = [];
          console.debug('[air4Service] loadSessions: no saved sessions in localStorage');
      }
  }

  private saveSessions() {
      localStorage.setItem(STORAGE_KEY_SESSIONS, JSON.stringify(this.sessions));
  }

  private updateSession(id: string, updates: Partial<ChatSession>) {
      const index = this.sessions.findIndex(s => s.id === id);
      console.debug('[air4Service] updateSession:', { 
          id, 
          found: index !== -1, 
          updates: { 
              title: updates.title, 
              messagesCount: updates.messages?.length,
              lastMessage: updates.lastMessage?.slice(0, 30)
          }
      });
      if (index !== -1) {
          this.sessions[index] = { ...this.sessions[index], ...updates };
          this.saveSessions();
      } else {
          console.warn('[air4Service] updateSession: session not found!', { id, availableIds: this.sessions.map(s => s.id) });
      }
  }

  // Нормализация API ответа в ChatSession (единое место для маппинга)
  private mapApiSessionToChatSession(apiSession: any): ChatSession {
      return {
          id: apiSession.id || apiSession.session_id || '',
          title: apiSession.title || apiSession.name || '',
          lastMessage: apiSession.last_message || '',
          timestamp: apiSession.timestamp || apiSession.created_at || Date.now(),
          messages: apiSession.messages || []
      };
  }

  // Upsert сессии: если есть - обновить, если нет - добавить
  private upsertSession(chatSession: ChatSession) {
      const existingIndex = this.sessions.findIndex(s => s.id === chatSession.id);
      if (existingIndex !== -1) {
          this.sessions[existingIndex] = chatSession;
          console.debug('[air4Service] upsertSession: updated existing session', { id: chatSession.id });
      } else {
          this.sessions.push(chatSession);
          console.debug('[air4Service] upsertSession: added new session', { id: chatSession.id });
      }
      this.saveSessions();
  }

  // Получение сессий с API
  private async fetchSessions(): Promise<any[]> {
      if (this.isOfflineMode) return [];
      
      try {
          const res = await fetch(`${API_BASE_URL}/sessions`);
          if (!res.ok) return [];
          
          const data = await res.json();
          return Array.isArray(data.sessions) ? data.sessions : (Array.isArray(data) ? data : []);
      } catch (e) {
          console.debug('[air4Service] fetchSessions: error', e);
          return [];
      }
  }

  // --- CONFIG ---

  isSetupComplete(): boolean {
    return this.config.setupComplete;
  }
  
  getUserName(): string {
      return this.config.userName || 'Operator';
  }

  setUserName(name: string) {
      this.config.userName = name;
      this.persistConfig();
  }

  getActiveModel(): ModelName {
      return this.config.activeModel || 'Mistral-7B';
  }

  setActiveModel(model: ModelName) {
      this.config.activeModel = model;
      this.persistConfig();
  }

  getResponseStyle(): ResponseStyle {
      return this.config.responseStyle || 'normal';
  }

  setResponseStyle(style: ResponseStyle) {
      this.config.responseStyle = style;
      this.persistConfig();
  }

  getLanguage(): Language {
      return this.config.language || 'auto';
  }

  setLanguage(lang: Language) {
      this.config.language = lang;
      this.persistConfig();
  }

  getIngestMode(): IngestMode {
      return this.config.ingestMode || 'smart';
  }

  setIngestMode(mode: IngestMode) {
      this.config.ingestMode = mode;
      this.persistConfig();
  }

  getAutoTitle(): boolean {
      return this.config.autoTitleSessions;
  }

  setAutoTitle(enabled: boolean) {
      this.config.autoTitleSessions = enabled;
      this.persistConfig();
  }

  getAppState(): AppState {
    return this.appState;
  }

  triggerPanic(): void {
    this.appState = AppState.PANIC;
    console.warn('PANIC MODE ENGAGED. DATA MASKED.');
  }
  
  resetSystem(): void {
      localStorage.removeItem(STORAGE_KEY_CONFIG);
      localStorage.removeItem(STORAGE_KEY_SESSIONS);
      window.location.reload();
  }

  saveConfig(agents: Agent[], userName: string) {
    this.config.agents = agents;
    this.config.userName = userName;
    this.config.setupComplete = true;
    this.persistConfig();
  }

  private persistConfig() {
      localStorage.setItem(STORAGE_KEY_CONFIG, JSON.stringify(this.config));
  }

  private reloadConfigFromStorage() {
      try {
          const savedConfig = localStorage.getItem(STORAGE_KEY_CONFIG);
          if (!savedConfig) {
              return;
          }
          const parsed = JSON.parse(savedConfig);
          this.config = {
              setupComplete: parsed.setupComplete || this.config.setupComplete || false,
              agents: parsed.agents || this.config.agents || AVAILABLE_AGENTS,
              userName: parsed.userName || this.config.userName || '',
              activeModel: parsed.activeModel || this.config.activeModel || 'Mistral-7B',
              responseStyle: parsed.responseStyle || this.config.responseStyle || 'normal',
              language: parsed.language || this.config.language || 'auto',
              ingestMode: parsed.ingestMode || this.config.ingestMode || 'smart',
              autoTitleSessions:
                  parsed.autoTitleSessions !== undefined
                      ? parsed.autoTitleSessions
                      : (this.config.autoTitleSessions !== undefined ? this.config.autoTitleSessions : true),
          };
      } catch (e) {
          console.warn('Failed to reload config from storage', e);
      }
  }

  private getOfflineStats(): SystemStats {
      return {
        uptime: 0,
        memoriesIndexed: 0,
        activeAgents: this.config.agents.filter(a => a.enabled).length,
        lastBackup: 'N/A',
        storageUsage: 'Offline Mode',
        routerAccuracy: 0,
        ltmHitRate: 0,
        ingestQueueLength: 0,
        isOffline: true,
        modelName: 'Demo / Offline'
      };
  }

  // --- REAL API CALLS ---

  async getStats(): Promise<SystemStats> {
    // Retry connection every 10 seconds if offline
    if (this.isOfflineMode && Date.now() - this.lastHealthCheck < 10000) {
        return this.getOfflineStats();
    }

    try {
      const controller = new AbortController();
      const timeoutId = setTimeout(() => controller.abort(), 2000);
      
      const res = await fetch(`${API_BASE_URL}/health`, { signal: controller.signal });
      clearTimeout(timeoutId);
      
      if (!res.ok) throw new Error('Health check failed');
      
      const data = await res.json();
      
      // If we succeed, clear offline mode
      this.isOfflineMode = false;
      this.lastHealthCheck = Date.now();

      let qLength = 0;
      try {
          const queueRes = await fetch(`${API_BASE_URL}/ingest/queue`);
          const queueData = await queueRes.json();
          if (queueData.ok && Array.isArray(queueData.queue)) {
              qLength = queueData.queue.length;
          }
      } catch (e) {
          console.warn('[getStats] Failed to fetch ingest queue', e);
      }

      const storageType = data.memory_backend === 'chroma' ? 'ChromaDB (Vector)' : 'Fallback (RAM)';

      return {
        uptime: Math.floor(Date.now() / 1000) - (data.ts || 0),
        memoriesIndexed: 0,
        activeAgents: this.config.agents.filter(a => a.enabled).length,
        lastBackup: new Date().toISOString(),
        storageUsage: storageType,
        routerAccuracy: 0.9,
        ltmHitRate: 0.7,
        ingestQueueLength: qLength,
        isOffline: false,
        modelName: data.model || this.config.activeModel || 'Unknown'
      };
    } catch (e) {
      this.isOfflineMode = true;
      this.lastHealthCheck = Date.now();
      return this.getOfflineStats();
    }
  }

  async getMemories(query: string = ""): Promise<MemoryItem[]> {
    if (this.appState === AppState.PANIC) return [];
    if (this.isOfflineMode) return []; // Don't fetch if offline
    
    try {
        const q = query || "recent"; 
        console.debug('[air4Service] getMemories: requesting', { query, finalQuery: q });
        const res = await fetch(`${API_BASE_URL}/memory/search?q=${encodeURIComponent(q)}&k=20`);
        if (!res.ok) throw new Error("Search failed");
        
        const data = await res.json();
        console.debug('[air4Service] getMemories: response', { 
            ok: data.ok, 
            resultsCount: data.results?.length || 0,
            sampleResults: data.results?.slice(0, 3).map((r: any) => ({
                id: r.id,
                text: r.text?.slice(0, 50),
                source: r.metadata?.source,
                kind: r.metadata?.kind,
                tag: r.metadata?.tag
            }))
        });
        
        if (data.ok && Array.isArray(data.results)) {
            return data.results.map((item: any) => ({
                id: item.id || Math.random().toString(),
                content: item.text || '',
                category: item.metadata?.kind || 'note',
                namespace: this.mapMetadataToNamespace(item.metadata),
                timestamp: item.metadata?.ts ? item.metadata.ts * 1000 : Date.now(),
                relevanceScore: item.score,
                source: item.metadata?.source || 'unknown',
                meta: item.metadata
            }));
        }
        return [];
    } catch (e) {
        // Don't set offline mode here to avoid race conditions with health check, just return empty
        console.debug('[air4Service] getMemories: error', e);
        return [];
    }
  }

  async getFacts(subject: string = "Arch", limit: number = 64): Promise<Fact[]> {
      if (this.appState === AppState.PANIC) return [];
      if (this.isOfflineMode) return [];
      try {
          const res = await fetch(`${API_BASE_URL}/facts/?subject=${encodeURIComponent(subject)}&limit=${limit}`);
          if (!res.ok) throw new Error("Facts fetch failed");
          const data = await res.json();
          if (Array.isArray(data)) {
              return data.map((item: any) => ({
                  id: item.id,
                  subject: item.subject,
                  predicate: item.predicate,
                  object: item.object,
                  timestamp: item.timestamp,
                  source_session: item.source_session,
                  source_message_id: item.source_message_id,
              }));
          }
          return [];
      } catch (e) {
          console.error("Failed to load facts", e);
          return [];
      }
  }

  async getFactsProfile(subject: string = "Arch"): Promise<{
      subject: string;
      food?: string[];
      country?: string[];
      location?: string[];
      vehicle?: string[];
      goals?: string[];
      other?: string[];
  }> {
      if (this.appState === AppState.PANIC) {
          return {
              subject,
              food: [],
              country: [],
              location: [],
              vehicle: [],
              goals: [],
              other: [],
          };
      }
      if (this.isOfflineMode) {
          return {
              subject,
              food: [],
              country: [],
              location: [],
              vehicle: [],
              goals: [],
              other: [],
          };
      }

      try {
          const res = await fetch(`${API_BASE_URL}/facts/profile/?subject=${encodeURIComponent(subject)}`);
          if (!res.ok) {
              throw new Error("Facts profile fetch failed");
          }
          const data = await res.json();
          // Ожидаем, что backend вернёт объект с нужной структурой
          return {
              subject: data.subject || subject,
              food: Array.isArray(data.food) ? data.food : [],
              country: Array.isArray(data.country) ? data.country : [],
              location: Array.isArray(data.location) ? data.location : [],
              vehicle: Array.isArray(data.vehicle) ? data.vehicle : [],
              goals: Array.isArray(data.goals) ? data.goals : [],
              other: Array.isArray(data.other) ? data.other : [],
          };
      } catch (e) {
          console.error("Failed to load facts profile", e);
          return {
              subject,
              food: [],
              country: [],
              location: [],
              vehicle: [],
              goals: [],
              other: [],
          };
      }
  }
  
  async addManualMemory(content: string, source: string = 'user-selection'): Promise<boolean> {
      if (this.appState === AppState.PANIC) return false;

      // Heuristic: if this memory comes from RAG / pin actions, treat it as a FACT.
      // Otherwise keep it as a NOTE.
      const kind: 'fact' | 'note' =
          (source === 'rag_pin' || source === 'rag_used_memory') ? 'fact' : 'note';

      try {
      // Debug breadcrumb: we should ALWAYS see this function create a network request.
      const payload = {
          text: content,
          metadata: {
              kind,
              tag: source,
              source: source,
              ts: Math.floor(Date.now() / 1000)
          }
      };
      console.debug('[air4Service] addManualMemory: POST /memory/add', { source, kind, content: content.slice(0, 50), fullPayload: payload });

      const res = await fetch(`${API_BASE_URL}/memory/add`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(payload)
      });

          if (!res.ok) {
              console.warn('[addManualMemory] non-OK response', res.status);
              return false;
          }

          const data = await res.json();
          console.debug('[air4Service] addManualMemory: response', { ok: data.ok, status: res.status, data });

          // If we successfully reached backend, clear offline mode.
          this.isOfflineMode = false;
          this.lastHealthCheck = Date.now();

          return data.ok === true;
      } catch (e) {
          console.error("Failed to add memory", e);

          // Mark offline so UI can reflect backend connectivity problems,
          // but do NOT prevent future attempts — the next call can succeed.
          this.isOfflineMode = true;
          this.lastHealthCheck = Date.now();

          return false;
      }
  }

  // Recall v0.1: Get sessions with preview + counts
  async getRecallSessions(params: { limit?: number; offset?: number; q?: string }): Promise<{ items: Array<{ session_id: string; title: string; updated_at: number; preview: string; counts: { chat: number; note: number } }>; has_more: boolean }> {
      if (this.appState === AppState.PANIC) {
          return { items: [], has_more: false };
      }

      try {
          const urlParams = new URLSearchParams();
          if (params.limit !== undefined) urlParams.append('limit', params.limit.toString());
          if (params.offset !== undefined) urlParams.append('offset', params.offset.toString());
          if (params.q) urlParams.append('q', params.q);

          const res = await fetch(`${API_BASE_URL}/recall/sessions?${urlParams.toString()}`);
          if (!res.ok) {
              console.warn('[getRecallSessions] non-OK response', res.status);
              return { items: [], has_more: false };
          }

          const data = await res.json();
          if (data.ok && Array.isArray(data.items)) {
              // Clear offline mode on success
              this.isOfflineMode = false;
              this.lastHealthCheck = Date.now();
              return {
                  items: data.items,
                  has_more: data.has_more === true
              };
          }
          return { items: [], has_more: false };
      } catch (e) {
          console.error('[getRecallSessions] failed:', e);
          this.isOfflineMode = true;
          this.lastHealthCheck = Date.now();
          return { items: [], has_more: false };
      }
  }

  // B2.5: Inline capture - add memory note via POST /memory/add?session_id=...
  async addMemoryNote(sessionId: string, text: string, tag: string = "manual"): Promise<boolean> {
      if (this.appState === AppState.PANIC) return false;

      try {
          const payload = {
              text: text,
              tag: tag
          };
          console.debug('[air4Service] addMemoryNote: POST /memory/add', { sessionId, tag, text: text.slice(0, 50) });

          const res = await fetch(`${API_BASE_URL}/memory/add?session_id=${encodeURIComponent(sessionId)}`, {
              method: 'POST',
              headers: { 'Content-Type': 'application/json' },
              body: JSON.stringify(payload)
          });

          if (!res.ok) {
              console.warn('[addMemoryNote] non-OK response', res.status);
              return false;
          }

          const data = await res.json();
          console.debug('[air4Service] addMemoryNote: response', { ok: data.ok, status: res.status });

          // If we successfully reached backend, clear offline mode.
          this.isOfflineMode = false;
          this.lastHealthCheck = Date.now();

          return data.ok === true;
      } catch (e) {
          console.error("Failed to add memory note", e);

          // Mark offline so UI can reflect backend connectivity problems,
          // but do NOT prevent future attempts — the next call can succeed.
          this.isOfflineMode = true;
          this.lastHealthCheck = Date.now();

          return false;
      }
  }

  async deleteMemory(id: string): Promise<boolean> {
      if (this.isOfflineMode) return false;
      if (this.appState === AppState.PANIC) return false;
      try {
          const res = await fetch(`${API_BASE_URL}/memory/delete`, {
              method: 'POST',
              headers: { 'Content-Type': 'application/json' },
              body: JSON.stringify({ id })
          });
          if (!res.ok) return false;
          const data = await res.json();
          return data.ok === true;
      } catch (e) {
          console.error("Failed to delete memory", e);
          return false;
      }
  }

  private mapMetadataToNamespace(meta: any): MemoryItem['namespace'] {
      if (!meta) return 'facts';
      // Phase E: Respect backend-provided metadata.namespace as source of truth
      if (meta.namespace && typeof meta.namespace === 'string' && meta.namespace.trim() !== '') {
          return meta.namespace as MemoryItem['namespace'];
      }
      // Fallback: existing mapping logic for old records without namespace
      if (meta.kind === 'file' || meta.source === 'file' || meta.source_path) return 'docs';
      if (meta.type === 'summary' || meta.source === 'summary') return 'sessions';
      if (meta.kind === 'note') return 'facts';
      return 'facts';
  }

  async uploadFile(file: File): Promise<boolean> {
      if (this.isOfflineMode) {
          console.warn("Cannot upload: System is offline");
          return false;
      }

      const formData = new FormData();
      formData.append('file', file);
      
      try {
          const res = await fetch(`${API_BASE_URL}/ingest/file?tag=ui-upload&mode=${this.config.ingestMode}`, {
              method: 'POST',
              body: formData
          });
          if (!res.ok) throw new Error("Upload failed");
          const data = await res.json();
          return data.ok;
      } catch (e) {
          console.error("Upload failed", e);
          return false;
      }
  }

  async getIngestQueueStatus(): Promise<IngestItem[]> {
      if (this.isOfflineMode) return [];

      try {
        const res = await fetch(`${API_BASE_URL}/ingest/queue`);
        if (!res.ok) throw new Error("Queue fetch failed");
        const data = await res.json();
        
        if (data.ok && Array.isArray(data.queue)) {
            return data.queue.map((q: any) => ({
                id: q.digest || Math.random().toString(),
                filename: q.file || 'Unknown',
                size: 0,
                type: 'detected',
                status: q.status || 'processing', // Use backend status if available
                progress: typeof q.progress === 'number' ? q.progress : 50,
                timestamp: Date.now()
            }));
        }
        return [];
      } catch (e) {
          return [];
      }
  }

  // --- CHAT LOGIC ---

  async *streamChat(messages: Message[], sessionId: string, coreSettings?: { temperature?: number; responseTone?: string; outputDensity?: string; interfaceLanguage?: string; activeModel?: string }): AsyncGenerator<{ chunk?: string, context?: MemoryItem[], decision?: RouterDecision, newSessionId?: string }, void, unknown> {
    if (this.appState === AppState.PANIC) {
       yield { chunk: "SYSTEM LOCKED. ACCESS DENIED." };
       return;
    }

    // Reload latest config from storage so activeModel and other settings are fresh
    try {
        this.reloadConfigFromStorage();
    } catch (e) {
        console.warn('Failed to reload config in streamChat', e);
    }

    const lastMessage = messages[messages.length - 1];
    
    // Проверяем и восстанавливаем сессию перед обновлением
    console.debug('[air4Service] streamChat: sessionId', { sessionId, messagesCount: messages.length });
    let session = this.getSession(sessionId);
    let actualSessionId = sessionId;
    
    if (!session) {
        console.warn('[air4Service] streamChat: session not found in local sessions!', { 
            sessionId, 
            availableIds: this.sessions.map(s => s.id) 
        });
        
        // Пытаемся получить сессию из API
        const apiSessions = await this.fetchSessions();
        const apiSession = apiSessions.find((s: any) => s.id === sessionId || s.session_id === sessionId);
        
        if (apiSession) {
            console.debug('[air4Service] streamChat: found session in API, upserting', { 
                apiSessionId: apiSession.id || apiSession.session_id 
            });
            const chatSession = this.mapApiSessionToChatSession(apiSession);
            this.upsertSession(chatSession);
            session = chatSession;
            actualSessionId = chatSession.id;
        } else {
            // Если API не вернул сессию - создаём новую
            console.warn('[air4Service] streamChat: session not found in API, creating new session');
            const newSession = this.createSession(''); // Пустая строка - title будет установлен автоматически
            session = newSession;
            actualSessionId = newSession.id;
            
            // Возвращаем новый sessionId через yield
            yield { newSessionId: newSession.id };
        }
    }
    
    console.debug('[air4Service] streamChat: session resolved', { 
        found: !!session, 
        sessionId: session?.id, 
        actualSessionId,
        title: session?.title 
    });
    
    // Update local session immediately with user message
    if (session) {
        // Auto-title logic: устанавливаем title только если он пустой и это первое сообщение
        let titleUpdate = session.title;
        if (this.config.autoTitleSessions && (!session.title || !session.title.trim()) && session.messages.length <= 1) {
            titleUpdate = lastMessage.content.slice(0, 30) + (lastMessage.content.length > 30 ? '...' : '');
        }

        console.debug('[air4Service] streamChat: updating session', { 
            sessionId: actualSessionId, 
            titleUpdate, 
            messagesCount: messages.length,
            lastMessage: lastMessage.content.slice(0, 50)
        });
        this.updateSession(actualSessionId, {
            messages: messages,
            lastMessage: lastMessage.content,
            timestamp: Date.now(),
            title: titleUpdate
        });
    }

    // 1. Simulate Router (UI only) - Use configured Active Model
    const simulatedDomain = this.guessDomain(lastMessage.content);
    const selectedModel = (coreSettings?.activeModel as ModelName) || this.config.activeModel || 'Mistral-7B';
    const currentStyle = this.config.responseStyle || 'normal';
    
    yield { 
        decision: { 
            domain: simulatedDomain, 
            model: this.isOfflineMode ? 'Offline-Demo' : selectedModel, 
            confidence: 0.85, 
            reason: `Routed via local rules (Style: ${currentStyle})`
        } 
    };

    // If we already know we are offline, skip fetch to prevent error
    if (this.isOfflineMode) {
        const mockReply = `[${selectedModel} DEMO MODE - ${currentStyle.toUpperCase()}]\n\nI am currently unable to reach the local backend (${API_BASE_URL}). I am operating in Offline Demo Mode. I can visualize the UI, but I cannot process real data or retrieve memories until the connection is restored.`;
        const chunkSize = 4;
        let fullMock = "";
        for (let i = 0; i < mockReply.length; i += chunkSize) {
            const chunk = mockReply.slice(i, i + chunkSize);
            fullMock += chunk;
            yield { chunk };
            await new Promise(r => setTimeout(r, 15));
        }

        // Save AI response to session
        if (session) {
             const updatedMsgs = [...messages, {
                 id: Date.now().toString(),
                 role: 'assistant' as const,
                 content: fullMock,
                 timestamp: Date.now(),
                 modelUsed: 'Offline-Demo' as const
             }];
             this.updateSession(actualSessionId, { messages: updatedMsgs });
        }
        return;
    }

    try {
        // 2. Call Real Backend (unified /chat endpoint with strict RAG + profile)
        const settingsPayload = {
            temperature: coreSettings?.temperature,
            response_tone: coreSettings?.responseTone,
            output_density: coreSettings?.outputDensity,
            interface_language: coreSettings?.interfaceLanguage,
            // передаём в backend и человекочитаемое имя модели, и активную модель
            model: selectedModel,
            active_model: selectedModel
        };

        const res = await fetch(`${API_BASE_URL}/chat`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                q: lastMessage.content,
                session_id: actualSessionId,
                style: currentStyle,
                model_override: selectedModel,
                settings: settingsPayload
            })
        });

        if (!res.ok) {
            throw new Error(`Server responded with status ${res.status}`);
        }

        const data: any = await res.json();
        const memoryIds: string[] = Array.isArray(data.memory_ids) ? data.memory_ids : [];

        if (memoryIds.length > 0) {
             yield { 
                 context: memoryIds.map(id => ({
                     id, 
                     content: `Ref: ${id.substring(0, 8)}...`, 
                     category: 'fact' as const, 
                     namespace: 'facts' as const, 
                     timestamp: Date.now()
                 }))
             };
        }

        const reply = data.reply || "[No response payload]";
        const chunkSize = 5;
        let fullReply = "";
        
        for (let i = 0; i < reply.length; i += chunkSize) {
            const chunk = reply.slice(i, i + chunkSize);
            fullReply += chunk;
            yield { chunk };
            await new Promise(r => setTimeout(r, 10));
        }

        // Save complete interaction to local history
        if (session) {
            // Re-fetch session to get any state updates
            const currentSession = this.getSession(actualSessionId);
            if(currentSession) {
                 const updatedMsgs = [...messages, {
                    id: Date.now().toString(),
                    role: 'assistant' as const,
                    content: fullReply,
                    timestamp: Date.now(),
                    modelUsed: selectedModel,
                    contextUsed: memoryIds.length > 0 ? [{
                        id: '1', 
                        content: 'Context used', 
                        category: 'fact' as const, 
                        namespace: 'facts' as const, 
                        timestamp: 0
                    }] : undefined
                }];
                this.updateSession(actualSessionId, { messages: updatedMsgs });
            }
        }

    } catch (e) {
        // Catch connection error, mark as offline, and yield a polite fallback
        console.warn("Backend connection failed. Switching to offline mode.");
        this.isOfflineMode = true;
        
        const errorBody = `⚠️ **CORE OFFLINE**\n\nConnection to \`${API_BASE_URL}\` failed. I have switched to offline mode to prevent errors.\n\nPlease check if your Uvicorn server and Ollama are running.`;

        const chunkSize = 5;
        for (let i = 0; i < errorBody.length; i += chunkSize) {
            yield { chunk: errorBody.slice(i, i + chunkSize) };
            await new Promise(r => setTimeout(r, 5));
        }
    }
  }

  private guessDomain(text: string): Domain {
      const lower = text.toLowerCase();
      if (lower.includes('code') || lower.includes('python') || lower.includes('function')) return 'code';
      if (lower.includes('finance') || lower.includes('cost') || lower.includes('price')) return 'finance';
      if (lower.includes('health') || lower.includes('gym') || lower.includes('run')) return 'fitness';
      return 'general';
  }
}

const air4Instance = new Air4Service();

export const air4 = air4Instance;

// Legacy helper exports for compatibility with older UI code
// Allow imports like `import * as se from '../services/air4Service'` and calls
// se.getLanguage(), se.createSession(), se.getSessions(), etc.
export const getLanguage = () => air4Instance.getLanguage();
export const setLanguage = (lang: Language) => air4Instance.setLanguage(lang);

export const getResponseStyle = () => air4Instance.getResponseStyle();
export const setResponseStyle = (style: ResponseStyle) => air4Instance.setResponseStyle(style);

export const getIngestMode = () => air4Instance.getIngestMode();
export const setIngestMode = (mode: IngestMode) => air4Instance.setIngestMode(mode);

export const getAutoTitle = () => air4Instance.getAutoTitle();
export const setAutoTitle = (enabled: boolean) => air4Instance.setAutoTitle(enabled);

export const getSessions = () => air4Instance.getSessions();
export const createSession = (initialTitle?: string) => air4Instance.createSession(initialTitle);