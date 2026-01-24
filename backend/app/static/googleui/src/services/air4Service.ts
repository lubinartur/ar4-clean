
import { Agent, MemoryItem, Message, SystemStats, RouterDecision, AppState, Domain, IngestItem, Send3Out, ChatSession, ModelName, ResponseStyle, Language, IngestMode, SessionConfig } from '../types';

// P2.3.1: Debug flag to control console spam (set to true for verbose logging)
const DEBUG_UI = import.meta.env.VITE_DEBUG_UI === 'true' || false;

const STORAGE_KEY_CONFIG = 'air4_config';
const STORAGE_KEY_SESSIONS = 'air4_sessions'; // Legacy, removed in G1
const STORAGE_KEY_ACTIVE_SESSION = 'air4.activeSessionId';

export interface Fact {
  id?: string;
  subject: string;
  predicate: string;
  object: string;
  timestamp: number;
  category?: 'profile' | 'food' | 'country' | 'vehicle' | 'location' | 'goals' | 'other';
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

// Helper function to validate backend session IDs
// Backend session IDs are 8-character hex strings (from uuid.uuid4().hex[:8])
// Timestamp-based IDs are numeric strings and are invalid
function isValidBackendSessionId(id: string | null | undefined): boolean {
  if (!id || typeof id !== 'string') return false;
  // Backend session IDs are exactly 8 hex characters
  // Timestamp-based IDs are numeric strings (e.g., "1768334507041")
  // Check: is exactly 8 chars and all hex digits, or is numeric (invalid)
  if (/^\d+$/.test(id)) {
    // Numeric string = timestamp-based ID = invalid
    return false;
  }
  // Must be exactly 8 hex characters to be valid backend session ID
  return /^[0-9a-f]{8}$/i.test(id);
}

export interface Air4Service {
  // Session Management
  getSessions(): ChatSession[];
  refreshSessions(): Promise<void>;
  getSession(id: string): ChatSession | undefined;
  getSessionById(id: string, signal?: AbortSignal): Promise<ChatSession>;
  isValidSessionId(id: string | null | undefined): boolean;
  createSession(initialTitle?: string): Promise<ChatSession>;
  deleteSession(id: string): void;
  deleteAllSessions(): void;
  renameSession(id: string, newTitle: string): void;
  duplicateSession(id: string): void;
  exportSession(id: string): void;
  upsertSession(session: ChatSession): void;
  
  // Config
  isSetupComplete(): boolean;
  getUserName(): string;
  setUserName(name: string): void;
  getActiveModel(): ModelName;
  setActiveModel(model: ModelName): void;
  getResponseStyle(): ResponseStyle;
  setResponseStyle(style: ResponseStyle): void;
  getLanguage(): Language;
  setLanguage(lang: Language): void;
  getIngestMode(): IngestMode;
  setIngestMode(mode: IngestMode): void;
  getAutoTitle(): boolean;
  setAutoTitle(enabled: boolean): void;
  getAppState(): AppState;
  triggerPanic(): void;
  resetSystem(): void;
  saveConfig(agents: Agent[], userName: string): void;
  
  // API Calls
  getStats(): Promise<SystemStats>;
  getMemories(query: string, sessionId: string): Promise<MemoryItem[]>;
  getMemoryItems(params: { query?: string; typeFilter?: string; tag?: string; limit?: number; offset?: number; sessionId: string }): Promise<{ items: MemoryItem[]; has_more: boolean }>;
  // B2.2: Memory Bank methods
  getMemoryBank(params: { sessionId: string; type?: string; tag?: string; limit?: number; offset?: number }): Promise<{ items: MemoryItem[]; has_more: boolean }>;
  promoteMemoryItem(id: string, target_type: string, target_tag?: string, sessionId?: string): Promise<boolean>;
  archiveMemoryItem(id: string, sessionId?: string): Promise<boolean>;
  unarchiveMemoryItem(id: string, sessionId?: string): Promise<boolean>;  // C3.0: Unarchive memory item
  deleteMemoryItem(id: string, sessionId?: string): Promise<boolean>;
  // B2.5: Manual save to Memory Bank (with confirmation)
  addMemoryNote(sessionId: string, text: string, tag?: string): Promise<{ ok: boolean }>;
  // C1-FIX: Suggest saving based on user intent (user->assistant pair)
  suggestMemoryItem(userText: string, assistantText: string, sessionId: string): Promise<{ ok: boolean; suggest: boolean; confidence: number; reason: string; proposed_tag: string }>;
  getFacts(subject?: string, limit?: number): Promise<Fact[]>;
  getFactsProfile(subject?: string): Promise<{ subject: string; profile?: string[]; }>;
  addManualMemory(content: string, source?: string): Promise<boolean>;
  addMemoryWithMeta(text: string, meta?: { source?: string; tag?: string; originalTag?: string; score?: number; query?: string; sessionId?: string; pinnedFrom?: string }): Promise<boolean>;
  deleteMemory(id: string, sessionId?: string): Promise<boolean>;
  deleteMemoryBy(by: "id" | "tag" | "namespace", value: string, sessionId?: string): Promise<boolean>;
  uploadFile(file: File): Promise<boolean>;
  getIngestQueueStatus(): Promise<IngestItem[]>;
  streamChat(messages: Message[], sessionId: string, coreSettings?: { temperature?: number; responseTone?: string; outputDensity?: string; interfaceLanguage?: string; activeModel?: string; thinkingMode?: string; rag?: boolean }): AsyncGenerator<{ chunk?: string, context?: MemoryItem[], decision?: RouterDecision }, void, unknown>;
  chatStream(payload: { text: string; session_id: string; settings?: any; qb_session_id?: string | null; qb_enabled?: boolean; thinking_mode?: string; conversation_id?: string; rag?: boolean }, handlers: { onToken: (delta: string) => void; onDone: (context_used?: any) => void; onError: (message: string) => void; onMeta?: (resolvedModel: string) => void }, signal?: AbortSignal): Promise<void>;
  getSessionConfig(sessionId: string): SessionConfig | undefined;
  setSessionConfig(sessionId: string, config: SessionConfig): void;
  getConversations(limit?: number, offset?: number, q?: string): Promise<any[]>;
  getConversation(id: string, opts?: { signal?: AbortSignal }): Promise<any>;
  createConversation(title?: string): Promise<{id: string}>;
  // B3 recall: fetch closed sessions list
  getRecallSessions(params: { limit: number; offset: number; q?: string }): Promise<{ ok: boolean; items: any[]; has_more: boolean }>;
  // Session-Conversation mapping
  getSessionConversationMap(): Record<string, string>;
  setSessionConversationMapping(sessionId: string, conversationId: string): void;
  getConversationIdForSession(sessionId: string): string | null;
  normalizeSessionResponse(data: any): { meta: any; messages: any[] };
}

class Air4ServiceImpl implements Air4Service {
  private config: Air4Config;
  private appState: AppState = AppState.ACTIVE;
  private isOfflineMode: boolean = false;
  private lastHealthCheck: number = 0;
  private sessions: ChatSession[] = [];
  private apiBaseUrl: string;

  constructor(apiBaseUrl: string) {
    const DEFAULT_API = 'http://127.0.0.1:8000';
    
    // Use passed apiBaseUrl (already processed through useSettings with priorities: localStorage > .env > default)
    this.apiBaseUrl = apiBaseUrl ? apiBaseUrl.replace(/\/$/, '') : DEFAULT_API;
    
    if (DEBUG_UI) console.log('[air4Service] baseUrl =', this.apiBaseUrl);  // P2.3.1
    const savedConfig = localStorage.getItem(STORAGE_KEY_CONFIG);
    if (savedConfig) {
      const parsed = JSON.parse(savedConfig);
      this.config = {
          setupComplete: parsed.setupComplete || false,
          agents: parsed.agents || AVAILABLE_AGENTS,
          userName: parsed.userName || '',
          activeModel: parsed.activeModel || "auto",
          responseStyle: parsed.responseStyle || 'normal',
          language: parsed.language || 'auto',
          ingestMode: parsed.ingestMode || 'smart',
          autoTitleSessions: parsed.autoTitleSessions !== undefined ? parsed.autoTitleSessions : true
      };
      
      // Нормализация legacy значений activeModel
      if (this.config.activeModel === "mistral-7b-local") {
          this.config.activeModel = "mistral:latest";
      }
      if (this.config.activeModel === "hermes-7b") {
          this.config.activeModel = "nous-hermes2-mixtral:8x7b";
      }
      
      // Сохраняем нормализованный конфиг обратно
      this.persistConfig();
    } else {
      this.config = { 
          setupComplete: false, 
          agents: AVAILABLE_AGENTS, 
          userName: '', 
          activeModel: "auto", 
          responseStyle: 'normal',
          language: 'auto',
          ingestMode: 'smart',
          autoTitleSessions: true
      };
    }

    // G1: Remove legacy sessions storage from localStorage
    if (localStorage.getItem(STORAGE_KEY_SESSIONS)) {
      localStorage.removeItem(STORAGE_KEY_SESSIONS);
      console.info('[G1] removed legacy local sessions cache');
    }

    // G1: Sessions are loaded from backend only, not from localStorage
    this.sessions = [];
  }

  // --- SESSION MANAGEMENT ---

  async refreshSessions(): Promise<void> {
      // G1: Load sessions from backend only
      if (this.isOfflineMode) {
          return;
      }
      
      try {
          const res = await fetch(`${this.apiBaseUrl}/sessions`);
          if (!res.ok) {
              console.warn('[air4Service] refreshSessions: failed to fetch sessions', res.statusText);
              return;
          }
          
          const data = await res.json();
          if (data.ok && Array.isArray(data.sessions)) {
              // Transform backend session format to ChatSession format
              this.sessions = data.sessions.map((s: any) => ({
                  id: s.id,
                  title: s.title || 'New session',
                  messages: [], // Messages are loaded separately via getSessionById
                  lastMessage: '',
                  timestamp: s.updated_at || s.created_at || Date.now(),
              })).filter((s: ChatSession) => isValidBackendSessionId(s.id));
          }
      } catch (e) {
          console.error('[air4Service] refreshSessions error:', e);
      }
  }

  getSessions(): ChatSession[] {
      // G1: Return sessions from memory (loaded via refreshSessions)
      return this.sessions.filter(s => isValidBackendSessionId(s.id))
          .sort((a, b) => b.timestamp - a.timestamp);
  }

  getSession(id: string): ChatSession | undefined {
      return this.sessions.find(s => s.id === id);
  }

  isValidSessionId(id: string | null | undefined): boolean {
      return isValidBackendSessionId(id);
  }

  async getSessionById(id: string, signal?: AbortSignal): Promise<ChatSession> {
      // Guard: only call backend if session ID is valid
      // B4 lifecycle: Session IDs must be created via POST /sessions/new (not legacy /sessions)
      if (!isValidBackendSessionId(id)) {
          throw new Error(`Invalid session ID: ${id}. Session IDs must be created via POST /sessions/new.`);
      }
      const API_BASE_URL = this.apiBaseUrl;
      
      try {
          const res = await fetch(`${API_BASE_URL}/sessions/${id}`, { signal });
          
          if (!res.ok) {
              const errorText = await res.text();
              console.error('[air4Service] fetch failed', res.status, errorText);
              if (res.status === 404) {
                  throw new Error('Session not found');
              }
              throw new Error(`Failed to fetch session: ${res.status} ${res.statusText} - ${errorText}`);
          }

          const rawData = await res.json();
          
          // Normalize session response (single source of truth)
          const normalized = this.normalizeSessionResponse(rawData);
          
          // Use normalized response (backend may return { meta: null, messages: [...] })
          // Нормализация id (может быть session_id или id)
          const sessionId = (normalized.meta?.id) || rawData.id || id;
          
          // Преобразование messages из формата backend в формат Message
          const normalizedMessages: Message[] = (normalized.messages || []).map((msg: any, index: number) => {
              // Нормализация role: поддерживаем разные поля
              const role = msg.role || msg.type || msg.sender || 'user';
              
              // Нормализация content: поддерживаем разные поля
              let content = msg.content || msg.text || msg.message || msg.value || msg.data || '';
              
              // Если content пустой, но есть объект/массив, используем JSON.stringify
              if (!content && (typeof msg === 'object' && (Array.isArray(msg) || Object.keys(msg).length > 0))) {
                  try {
                      content = JSON.stringify(msg).slice(0, 2000);
                  } catch (e) {
                      content = String(msg).slice(0, 2000);
                  }
              }
              
              // Нормализация timestamp
              const timestamp = msg.ts || msg.timestamp || msg.time || rawData.timestamp || Date.now();
              
              return {
                  id: msg.id || `msg-${index}-${timestamp}`,
                  role: role as 'user' | 'assistant' | 'system',
                  content: String(content),
                  timestamp: typeof timestamp === 'number' ? timestamp : Date.now(),
                  modelUsed: msg.modelUsed as ModelName | undefined,
                  domain: msg.domain as Domain | undefined,
              };
          });

          const session: ChatSession = {
              id: sessionId,
              title: (normalized.meta?.title) || rawData.title || 'New session',
              messages: normalizedMessages,
              lastMessage: (normalized.meta?.lastMessage) || rawData.lastMessage || '',
              timestamp: (normalized.meta?.timestamp) || rawData.timestamp || Date.now(),
          };

          return session;
      } catch (error: any) {
          // Ignore AbortError (expected when request is cancelled)
          if (error?.name === 'AbortError' || error?.message?.includes('aborted')) {
              throw error; // Re-throw without logging
          }
          
          // Log real network/API errors (404, 500, etc.)
          console.error('[air4Service] getSessionById error:', error);
          throw error;
      }
  }

  upsertSession(session: ChatSession): void {
      // G1: Update in-memory cache only, backend is source of truth
      const index = this.sessions.findIndex(s => s.id === session.id);
      if (index !== -1) {
          // Обновляем существующую сессию
          this.sessions[index] = session;
      } else {
          // Добавляем новую сессию
          this.sessions.unshift(session);
      }
      // Note: No localStorage save - backend is source of truth
  }

  async createSession(initialTitle: string = 'New Session'): Promise<ChatSession> {
      // B4 lifecycle: Call backend POST /sessions/new for authoritative lifecycle management
      // This endpoint ensures exactly one active session by closing previous active session
      let backendSessionId: string;
      let closedPrevious: boolean = false;
      let previousSessionId: string | null = null;
      try {
          const res = await fetch(`${this.apiBaseUrl}/sessions/new`, {
              method: 'POST',
              headers: { 'Content-Type': 'application/json' },
              body: JSON.stringify(initialTitle ? { title: initialTitle } : {})
          });
          if (!res.ok) {
              throw new Error(`Failed to create session: ${res.statusText}`);
          }
          const data = await res.json();
          if (data.ok && data.session_id) {
              backendSessionId = data.session_id;
              closedPrevious = data.closed_previous === true;
              previousSessionId = data.previous_session_id || null;
              if (DEBUG_UI) console.debug(`[B4] createSession: sid=${backendSessionId}, title="${initialTitle}", closed_previous=${closedPrevious}`);  // P2.3.1
              if (closedPrevious && previousSessionId) {
                  if (DEBUG_UI) console.debug('[B4] createSession: closed previous session', previousSessionId);  // P2.3.1
              }
          } else {
              throw new Error('Invalid response from /sessions/new');
          }
      } catch (error) {
          console.error('[air4Service] createSession backend call failed:', error);
          throw new Error('Failed to create session on backend');
      }

      // Create local session with backend session_id
      const newSession: ChatSession = {
          id: backendSessionId, // Use backend session_id
          title: initialTitle,
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
      // G1: No localStorage save - backend is source of truth
      return newSession;
  }

  deleteSession(id: string) {
      // G1: Update in-memory cache only, backend handles actual deletion
      this.sessions = this.sessions.filter(s => s.id !== id);
      // Note: No localStorage save - backend is source of truth
  }

  deleteAllSessions() {
      // G1: Update in-memory cache only, backend handles actual deletion
      this.sessions = [];
      // Note: No localStorage save - backend is source of truth
      // Immediately create a fresh one so the UI isn't empty
      this.createSession().catch(err => {
        console.error('[air4Service] Failed to create session after deleteAll:', err);
      });
  }

  renameSession(id: string, newTitle: string) {
      this.updateSession(id, { title: newTitle });
  }

  duplicateSession(id: string) {
      const original = this.getSession(id);
      if (original) {
          // G1: Create duplicate via backend, then update cache
          this.createSession(`${original.title} (Copy)`).then(newSession => {
              // Note: createSession already adds to this.sessions
          }).catch(err => {
              console.error('[air4Service] Failed to duplicate session:', err);
          });
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

  private updateSession(id: string, updates: Partial<ChatSession>) {
      // G1: Update in-memory cache only, backend is source of truth
      const index = this.sessions.findIndex(s => s.id === id);
      if (index !== -1) {
          this.sessions[index] = { ...this.sessions[index], ...updates };
          // Note: No localStorage save - backend is source of truth
      }
  }

  getSessionConfig(sessionId: string): SessionConfig | undefined {
      const session = this.getSession(sessionId);
      return session?.sessionConfig;
  }

  setSessionConfig(sessionId: string, config: SessionConfig): void {
      const session = this.getSession(sessionId);
      if (session) {
          this.updateSession(sessionId, { sessionConfig: config });
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
      return this.config.activeModel || "auto";
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
      localStorage.removeItem(STORAGE_KEY_SESSIONS); // Legacy, safe to remove
      localStorage.removeItem(STORAGE_KEY_ACTIVE_SESSION);
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
          
          // Нормализация legacy значений activeModel
          if (this.config.activeModel === "mistral-7b-local") {
              this.config.activeModel = "mistral:latest";
          }
          if (this.config.activeModel === "hermes-7b") {
              this.config.activeModel = "nous-hermes2-mixtral:8x7b";
          }
          
          // Сохраняем нормализованный конфиг обратно
          this.persistConfig();
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
      
      const res = await fetch(`${this.apiBaseUrl}/health`, { signal: controller.signal });
      clearTimeout(timeoutId);
      
      if (!res.ok) throw new Error('Health check failed');
      
      const data = await res.json();
      
      // If we succeed, clear offline mode
      this.isOfflineMode = false;
      this.lastHealthCheck = Date.now();

      let qLength = 0;
      try {
          const queueRes = await fetch(`${this.apiBaseUrl}/ingest/queue`);
          const queueData = await queueRes.json();
          if (queueData.ok && Array.isArray(queueData.queue)) {
              qLength = queueData.queue.length;
          }
      } catch (e) {
          console.error('[getStats] Failed to fetch ingest queue', e);
          // Continue with qLength = 0, don't fail the whole stats call
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
      console.error('[getStats] Health check failed', e);
      this.isOfflineMode = true;
      this.lastHealthCheck = Date.now();
      return this.getOfflineStats();
    }
  }

  async getMemories(query: string, sessionId: string): Promise<MemoryItem[]> {
    if (this.appState === AppState.PANIC) return [];
    if (this.isOfflineMode) return []; // Don't fetch if offline
    if (!sessionId) {
      console.error('[getMemories] sessionId is required');
      return [];
    }
    
    try {
        const q = query || "recent"; 
        const res = await fetch(`${this.apiBaseUrl}/memory/search?q=${encodeURIComponent(q)}&session_id=${encodeURIComponent(sessionId)}&k=20`);
        if (!res.ok) throw new Error("Search failed");
        
        const data = await res.json();
        
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
        console.error('[getMemories] Memory search failed', e);
        // Don't set offline mode here to avoid race conditions with health check, just return empty
        return [];
    }
  }

  // B1: Unified read-only memory items API for Store UI
  async getMemoryItems(params: { query?: string; typeFilter?: string; tag?: string; limit?: number; offset?: number; sessionId: string }): Promise<{ items: MemoryItem[]; has_more: boolean }> {
    if (this.appState === AppState.PANIC) return { items: [], has_more: false };
    if (this.isOfflineMode) return { items: [], has_more: false };
    if (!params.sessionId) {
      console.error('[getMemoryItems] sessionId is required');
      return { items: [], has_more: false };
    }

    try {
        // B0.2: Build query - backend requires q (use empty string for list mode, user query for search)
        // Empty string should work as minimal query for listing all items
        const q = params.query || "";
        
        // Build where_json filter based on typeFilter (namespace mapping)
        let whereJson: string | undefined = undefined;
        if (params.typeFilter && params.typeFilter !== 'all') {
            const where: Record<string, string> = {};
            // Map UI tab to metadata namespace/kind
            if (params.typeFilter === 'docs') {
                where['namespace'] = 'docs';
            } else if (params.typeFilter === 'sessions') {
                where['namespace'] = 'sessions';
            } else if (params.typeFilter === 'facts') {
                where['namespace'] = 'facts';
            } else if (params.typeFilter === 'profile') {
                where['namespace'] = 'profile';
            } else if (params.typeFilter === 'pinned') {
                where['tag'] = 'rag_pin';
            }
            // tag filter overrides typeFilter tag
            if (params.tag) {
                where['tag'] = params.tag;
            }
            if (Object.keys(where).length > 0) {
                whereJson = JSON.stringify(where);
            }
        } else if (params.tag) {
            // If only tag is provided without typeFilter
            whereJson = JSON.stringify({ tag: params.tag });
        }

        const limit = params.limit || 50;
        const offset = params.offset || 0;
        
        // Build URL with params
        const urlParams = new URLSearchParams({
            q,
            session_id: params.sessionId,
            limit: limit.toString(),
            offset: offset.toString(),
        });
        if (whereJson) {
            urlParams.set('where_json', whereJson);
        }

        const res = await fetch(`${this.apiBaseUrl}/memory/search?${urlParams.toString()}`);
        if (!res.ok) throw new Error("Memory items fetch failed");
        
        const data = await res.json();
        
        if (data.ok && Array.isArray(data.results)) {
            const items: MemoryItem[] = data.results.map((item: any) => ({
                id: item.id || Math.random().toString(),
                content: item.text || item.content || '',
                category: (item.metadata || item.meta)?.kind || 'note',
                namespace: this.mapMetadataToNamespace(item.metadata || item.meta),
                timestamp: (item.metadata || item.meta)?.ts ? (item.metadata || item.meta).ts * 1000 : Date.now(),
                relevanceScore: item.score,
                source: (item.metadata || item.meta)?.source || 'unknown',
                meta: item.metadata || item.meta
            }));
            return {
                items,
                has_more: data.has_more === true
            };
        }
        return { items: [], has_more: false };
    } catch (e) {
        console.error('[getMemoryItems] Memory items fetch failed', e);
        return { items: [], has_more: false };
    }
  }

  // B2.2: Memory Bank API methods
  async getMemoryBank(params: { sessionId: string; type?: string; tag?: string; limit?: number; offset?: number; includeArchived?: boolean }): Promise<{ items: MemoryItem[]; has_more: boolean }> {
    if (this.appState === AppState.PANIC) return { items: [], has_more: false };
    if (this.isOfflineMode) return { items: [], has_more: false };
    if (!params.sessionId) {
      console.error('[B2.2] getMemoryBank: sessionId is required');
      return { items: [], has_more: false };
    }

    if (DEBUG_UI) console.log(`[B2.2] bank GET sid=${params.sessionId} type=${params.type || 'all'} offset=${params.offset || 0} limit=${params.limit || 50}`);  // P2.3.1

    try {
      const urlParams = new URLSearchParams({
        session_id: params.sessionId,
        limit: (params.limit || 50).toString(),
        offset: (params.offset || 0).toString(),
      });
      // HOTFIX: omit type for ALL - only add type if it's defined, not empty, and not 'all'
      if (params.type && params.type !== 'all' && params.type.trim() !== '') {
        urlParams.set('type', params.type);
      }
      if (params.tag) {
        urlParams.set('tag', params.tag);
      }
      // C3.0: Include archived items flag
      if (params.includeArchived === true) {
        urlParams.set('include_archived', '1');
      }

      const res = await fetch(`${this.apiBaseUrl}/memory/bank?${urlParams.toString()}`);
      if (!res.ok) throw new Error("Memory bank fetch failed");
      
      const data = await res.json();
      
      if (data.ok && Array.isArray(data.items)) {
        const items: MemoryItem[] = data.items.map((item: any) => ({
          id: item.id || Math.random().toString(),
          text: item.text || item.content || '',
          content: item.text || item.content || '',
          category: item.type || item.meta?.kind || 'note',
          namespace: item.namespace || this.mapMetadataToNamespace(item.meta),
          timestamp: item.created_at ? (typeof item.created_at === 'number' ? item.created_at * 1000 : Date.parse(item.created_at)) : Date.now(),
          relevanceScore: item.score || 1.0,
          source: item.meta?.source || 'unknown',
          meta: {
            ...(item.meta || {}),
            ...(item.created_at ? { created_at: item.created_at } : {}),
            ...(item.type ? { type: item.type } : {}),
            ...(item.tag ? { tag: item.tag } : {}),
            ...(item.session_id ? { session_id: item.session_id } : {}),
            ...(item.namespace ? { namespace: item.namespace } : {})
          }
        }));
        return {
          items,
          has_more: data.has_more === true
        };
      }
      return { items: [], has_more: false };
    } catch (e) {
      console.error('[B2.2] getMemoryBank failed', e);
      return { items: [], has_more: false };
    }
  }

  async promoteMemoryItem(id: string, target_type: string, target_tag?: string, sessionId?: string): Promise<boolean> {
    if (this.appState === AppState.PANIC) return false;
    if (this.isOfflineMode) return false;
    
    // Get sessionId from active session if not provided
    if (!sessionId) {
      const sessions = this.getSessions();
      if (sessions.length > 0) {
        sessionId = sessions[0].id;
      } else {
        console.error('[B2.2] promoteMemoryItem: sessionId required');
        return false;
      }
    }

    if (DEBUG_UI) console.log(`[B2.2] promote id=${id} target_type=${target_type} target_tag=${target_tag || 'none'}`);  // P2.3.1

    try {
      const body: any = { id, target_type };
      if (target_tag) {
        body.target_tag = target_tag;
      }
      const res = await fetch(`${this.apiBaseUrl}/memory/promote?session_id=${encodeURIComponent(sessionId)}`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body)
      });
      if (!res.ok) throw new Error("Promote failed");
      const data = await res.json();
      return data.ok === true;
    } catch (e) {
      console.error('[B2.2] promoteMemoryItem failed:', e);
      return false;
    }
  }

  async archiveMemoryItem(id: string, sessionId?: string): Promise<boolean> {
    if (this.appState === AppState.PANIC) return false;
    if (this.isOfflineMode) return false;
    
    if (!sessionId) {
      const sessions = this.getSessions();
      if (sessions.length > 0) {
        sessionId = sessions[0].id;
      } else {
        console.error('[B2.2] archiveMemoryItem: sessionId required');
        return false;
      }
    }

    if (DEBUG_UI) console.log(`[B2.2] archive id=${id}`);  // P2.3.1

    try {
      const res = await fetch(`${this.apiBaseUrl}/memory/archive?session_id=${encodeURIComponent(sessionId)}`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ id })
      });
      if (!res.ok) throw new Error("Archive failed");
      const data = await res.json();
      return data.ok === true;
    } catch (e) {
      console.error('[B2.2] archiveMemoryItem failed:', e);
      return false;
    }
  }

  // C3.0: Unarchive memory item
  async unarchiveMemoryItem(id: string, sessionId?: string): Promise<boolean> {
    if (this.appState === AppState.PANIC) return false;
    if (this.isOfflineMode) return false;
    
    if (!sessionId) {
      const sessions = this.getSessions();
      if (sessions.length > 0) {
        sessionId = sessions[0].id;
      } else {
        console.error('[C3.0] unarchiveMemoryItem: sessionId required');
        return false;
      }
    }

    if (DEBUG_UI) console.log(`[C3.0] unarchive id=${id}`);  // P2.3.1

    try {
      const res = await fetch(`${this.apiBaseUrl}/memory/unarchive?session_id=${encodeURIComponent(sessionId)}`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ id })
      });
      if (!res.ok) throw new Error("Unarchive failed");
      const data = await res.json();
      return data.ok === true;
    } catch (e) {
      console.error('[C3.0] unarchiveMemoryItem failed:', e);
      return false;
    }
  }

  async deleteMemoryItem(id: string, sessionId?: string): Promise<boolean> {
    if (this.appState === AppState.PANIC) return false;
    if (this.isOfflineMode) return false;
    
    if (!sessionId) {
      const sessions = this.getSessions();
      if (sessions.length > 0) {
        sessionId = sessions[0].id;
      } else {
        console.error('[B2.2] deleteMemoryItem: sessionId required');
        return false;
      }
    }

    if (DEBUG_UI) console.log(`[B2.2] delete id=${id}`);  // P2.3.1

    try {
      const res = await fetch(`${this.apiBaseUrl}/memory/bank/${encodeURIComponent(id)}?session_id=${encodeURIComponent(sessionId)}`, {
        method: 'DELETE'
      });
      if (!res.ok) throw new Error("Delete failed");
      const data = await res.json();
      return data.ok === true;
    } catch (e) {
      console.error('[B2.2] deleteMemoryItem failed:', e);
      return false;
    }
  }

  // B2.5: Manual save to Memory Bank (with confirmation)
  async addMemoryNote(sessionId: string, text: string, tag?: string): Promise<{ ok: boolean }> {
    if (this.appState === AppState.PANIC) return { ok: false };
    if (this.isOfflineMode) return { ok: false };
    
    try {
      const res = await fetch(`${this.apiBaseUrl}/memory/add?session_id=${encodeURIComponent(sessionId)}`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ text, tag: tag || "manual" })
      });
      if (!res.ok) {
        const errorText = await res.text();
        throw new Error(errorText || "Add failed");
      }
      const data = await res.json();
      return { ok: data.ok === true };
    } catch (e) {
      console.error('[addMemoryNote] Failed:', e);
      throw e;
    }
  }

  // C1: Suggest saving based on user intent (user->assistant pair)
  async suggestMemoryItem(userText: string, assistantText: string, sessionId: string): Promise<{ ok: boolean; suggest: boolean; confidence: number; reason: string; proposed_tag: string }> {
    if (this.appState === AppState.PANIC) return { ok: false, suggest: false, confidence: 0, reason: "", proposed_tag: "manual" };
    if (this.isOfflineMode) return { ok: false, suggest: false, confidence: 0, reason: "", proposed_tag: "manual" };
    
    if (DEBUG_UI) console.log('[C1] suggest request sid=', sessionId);  // P2.3.1
    try {
      const res = await fetch(`${this.apiBaseUrl}/memory/suggest?session_id=${encodeURIComponent(sessionId)}`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ user_text: userText, assistant_text: assistantText })
      });
      if (!res.ok) {
        throw new Error("Suggest failed");
      }
      const data = await res.json();
      if (DEBUG_UI) console.log('[C1] suggest response suggest=', data.suggest, 'tag=', data.proposed_tag, 'reason=', data.reason);  // P2.3.1
      return {
        ok: data.ok === true,
        suggest: data.suggest === true,
        confidence: data.confidence || 0,
        reason: data.reason || "",
        proposed_tag: data.proposed_tag || "manual"
      };
    } catch (e) {
      console.error('[C1] suggestMemoryItem failed:', e);
      return { ok: false, suggest: false, confidence: 0, reason: "error", proposed_tag: "manual" };
    }
  }

  async getFacts(subject: string = "Arch", limit: number = 64): Promise<Fact[]> {
      if (this.appState === AppState.PANIC) return [];
      if (this.isOfflineMode) return [];
      try {
          const res = await fetch(`${this.apiBaseUrl}/facts/?subject=${encodeURIComponent(subject)}&limit=${limit}`);
          if (!res.ok) throw new Error("Facts fetch failed");
          const data = await res.json();
          if (Array.isArray(data)) {
              return data.map((item: any) => ({
                  id: item.id,
                  subject: item.subject,
                  predicate: item.predicate,
                  object: item.object,
                  timestamp: item.timestamp,
                  category: item.category,
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
      profile?: string[];
  }> {
      if (this.appState === AppState.PANIC) {
          return {
              subject,
              profile: [],
          };
      }
      if (this.isOfflineMode) {
          return {
              subject,
              profile: [],
          };
      }

      try {
          const url = `${this.apiBaseUrl}/facts/profile/?subject=${encodeURIComponent(subject)}`;
          if (DEBUG_UI) console.log('[Store/Profile] request url:', url);  // P2.3.1
          const res = await fetch(url);
          if (!res.ok) {
              throw new Error("Facts profile fetch failed");
          }
          const data = await res.json();
          if (DEBUG_UI) console.log('[Store/Profile] response:', data);  // P2.3.1

          // Backend returns {subject, profile: [...]}
          return {
              subject: data.subject || subject,
              profile: Array.isArray(data.profile) && data.profile.length > 0 ? data.profile : undefined,
          };
      } catch (e) {
          console.error("Failed to load facts profile", e);
          return {
              subject,
              profile: [],
          };
      }
  }
  
  async addManualMemory(content: string, source: string = 'user-selection'): Promise<boolean> {
      if (this.isOfflineMode) return false;
      try {
          const res = await fetch(`${this.apiBaseUrl}/memory/add`, {
              method: 'POST',
              headers: { 'Content-Type': 'application/json' },
              body: JSON.stringify({ 
                  text: content, 
                  metadata: { 
                      kind: 'note', 
                      source: source,
                      ts: Math.floor(Date.now() / 1000)
                  }
              })
          });
          if (!res.ok) return false;
          const data = await res.json();
          return data.ok;
      } catch (e) {
          console.error("Failed to add memory", e);
          return false;
      }
  }

  async addMemoryWithMeta(
      text: string, 
      meta?: { source?: string; tag?: string; originalTag?: string; score?: number; query?: string; sessionId?: string; pinnedFrom?: string }
  ): Promise<boolean> {
      if (this.isOfflineMode) return false;
      try {
          // Если tag не задан — ставим "rag_pin"
          const finalTag = meta?.tag || 'rag_pin';
          
          // Формируем текст с метаданными как префикс/суффикс
          let enrichedText = text;
          if (meta) {
              const metaParts: string[] = [];
              if (meta.source) metaParts.push(`Source: ${meta.source}`);
              metaParts.push(`Tag: ${finalTag}`); // Всегда добавляем tag
              if (meta.originalTag) metaParts.push(`OriginalTag: ${meta.originalTag}`); // Добавляем originalTag если передан
              if (meta.score !== undefined) metaParts.push(`Score: ${Math.round(meta.score * 100)}%`);
              if (meta.query) metaParts.push(`Query: ${meta.query}`);
              if (meta.sessionId) metaParts.push(`Session: ${meta.sessionId}`);
              if (meta.pinnedFrom) metaParts.push(`PinnedFrom: ${meta.pinnedFrom}`);
              
              if (metaParts.length > 0) {
                  const metaStr = `[Meta: ${metaParts.join(', ')}]\n\n`;
                  enrichedText = metaStr + text;
              }
          }

          const res = await fetch(`${this.apiBaseUrl}/memory/add`, {
              method: 'POST',
              headers: { 'Content-Type': 'application/json' },
              body: JSON.stringify({ 
                  text: enrichedText,
                  tag: finalTag
              })
          });
          if (!res.ok) return false;
          const data = await res.json();
          return data.ok;
      } catch (e) {
          console.error("Failed to add memory with meta", e);
          return false;
      }
  }

  async deleteMemoryBy(by: "id" | "tag" | "namespace", value: string, sessionId?: string): Promise<boolean> {
      if (this.isOfflineMode) return false;
      if (this.appState === AppState.PANIC) return false;
      const sid = (sessionId || '').trim();
      if (!sid) return false;
      try {
          // Phase E: Use DELETE endpoint with by=id|tag|namespace
          // sessionId is required by backend
          const res = await fetch(`${this.apiBaseUrl}/memory/delete?session_id=${encodeURIComponent(sid)}`, {
              method: 'DELETE',
              headers: { 'Content-Type': 'application/json' },
              body: JSON.stringify({ by, value })
          });
          if (!res.ok) {
              if (res.status === 404) return false; // Not found
              return false;
          }
          const data = await res.json();
          return data.status === 'ok' && data.deleted > 0;
      } catch (e) {
          console.error("Failed to delete memory", e);
          return false;
      }
  }

  async deleteMemory(id: string, sessionId?: string): Promise<boolean> {
      return this.deleteMemoryBy("id", id, sessionId);
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
          const res = await fetch(`${this.apiBaseUrl}/ingest/file?tag=ui-upload&mode=${this.config.ingestMode}`, {
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
        const res = await fetch(`${this.apiBaseUrl}/ingest/queue`);
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
          console.error('[getIngestQueueStatus] Failed to fetch ingest queue', e);
          return [];
      }
  }

  // --- CHAT LOGIC ---

  async *streamChat(messages: Message[], sessionId: string, coreSettings?: { temperature?: number; responseTone?: string; outputDensity?: string; interfaceLanguage?: string; activeModel?: string; thinkingMode?: string; rag?: boolean }, conversationId?: string): AsyncGenerator<{ chunk?: string, context?: MemoryItem[], decision?: RouterDecision, conversationId?: string }, void, unknown> {
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
    
    // Update local session immediately with user message
    const session = this.getSession(sessionId);
    if (session) {
        // Auto-title logic: if it's the first real user message and enabled
        let titleUpdate = session.title;
        if (this.config.autoTitleSessions && session.messages.length <= 1) {
            titleUpdate = lastMessage.content.slice(0, 30) + (lastMessage.content.length > 30 ? '...' : '');
        }

        this.updateSession(sessionId, {
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
    
    // G2: Decision will be yielded from backend meta event, but yield initial for UI
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
        const mockReply = `[${selectedModel} DEMO MODE - ${currentStyle.toUpperCase()}]\n\nI am currently unable to reach the local backend (${this.apiBaseUrl}). I am operating in Offline Demo Mode. I can visualize the UI, but I cannot process real data or retrieve memories until the connection is restored.`;
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
             this.updateSession(sessionId, { messages: updatedMsgs });
        }
        return;
    }

    try {
        // G2: Use real streaming via /chat/stream endpoint
        const settingsPayload = {
            temperature: coreSettings?.temperature,
            response_tone: coreSettings?.responseTone,
            output_density: coreSettings?.outputDensity,
            interface_language: coreSettings?.interfaceLanguage,
            model: selectedModel,
            active_model: selectedModel
        };

        let fullReply = "";
        let resolvedModel = selectedModel;
        let streamSuccess = false;

        try {
            // G2: Direct SSE streaming from /chat/stream
            // PHASE Q5: Add thinking_mode to payload
            // C2.0: Add rag flag as query parameter
            const requestPayload: any = {
                q: lastMessage.content,
                text: lastMessage.content,
                session_id: sessionId,
                settings: settingsPayload
            };
            
            // Add thinking_mode if provided
            if (coreSettings?.thinkingMode) {
                requestPayload.thinking_mode = coreSettings.thinkingMode;
            }
            
            // Add conversation_id if provided
            if (conversationId) {
                requestPayload.conversation_id = conversationId;
            }
            
            // C2.0: Build URL with rag query param (default to 1 if not specified)
            const ragValue = coreSettings?.rag !== undefined ? (coreSettings.rag ? "1" : "0") : "1";
            const url = `${this.apiBaseUrl}/chat/stream?rag=${ragValue}`;
            if (DEBUG_UI) console.log(`[C2.0] chat request sid=${sessionId} rag=${ragValue}`);  // P2.3.1
            
            const response = await fetch(url, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(requestPayload)
            });

            if (!response.ok) {
                throw new Error(`Server responded with status ${response.status}`);
            }

            if (!response.body) {
                throw new Error('Response body is null');
            }

            const reader = response.body.getReader();
            const decoder = new TextDecoder();
            let buffer = '';
            let currentEventType: string | null = null;

            try {
                while (true) {
                    const { done, value } = await reader.read();
                    
                    if (done) {
                        break;
                    }

                    buffer += decoder.decode(value, { stream: true });
                    const lines = buffer.split('\n');
                    buffer = lines.pop() || '';

                    for (const line of lines) {
                        const trimmed = line.trim();
                        if (!trimmed) continue;

                        if (trimmed.startsWith('event: ')) {
                            currentEventType = trimmed.slice(7).trim();
                            continue;
                        }

                        if (trimmed.startsWith('data: ')) {
                            const jsonStr = trimmed.slice(6);
                            if (!jsonStr) continue;

                            try {
                                const event = JSON.parse(jsonStr);
                                
                                // Extract conversation_id if present (from conversation_id or conversationId field)
                                const cid = event.conversation_id ?? event.conversationId;
                                
                                if (currentEventType === 'error' || event.type === 'error') {
                                    throw new Error(event.message || 'Unknown error');
                                }
                                
                                if (event.type === 'meta') {
                                    if (event.model) {
                                        resolvedModel = event.model;
                                        yield { 
                                            decision: { domain: simulatedDomain, model: event.model, confidence: 0.85, reason: 'Streaming from backend' },
                                            ...(cid ? { conversationId: cid } : {})
                                        };
                                    } else if (cid) {
                                        // conversation_id might come in meta event without model
                                        yield { conversationId: cid };
                                    }
                                } else if (event.type === 'token' && event.delta) {
                                    fullReply += event.delta;
                                    yield { 
                                        chunk: event.delta,
                                        ...(cid ? { conversationId: cid } : {})
                                    };
                                } else if (event.type === 'done') {
                                    streamSuccess = true;
                                    if (cid) {
                                        yield { conversationId: cid };
                                    }
                                    break;
                                } else if (cid) {
                                    // conversation_id might come in other event types
                                    yield { conversationId: cid };
                                }
                            } catch (e) {
                                // If parsing fails, check if it's plain text with conversation_id pattern
                                // Otherwise, just warn and continue
                                console.warn('[streamChat] Failed to parse SSE event:', jsonStr, e);
                            }
                            
                            currentEventType = null;
                        }
                    }

                    if (streamSuccess) {
                        break;
                    }
                }
            } finally {
                reader.releaseLock();
            }

        } catch (streamError: any) {
            // Fallback to /chat if streaming fails
            console.warn('[streamChat] Streaming failed, falling back to /chat:', streamError);
            
            const fallbackPayload: any = {
                q: lastMessage.content,
                session_id: sessionId,
                style: currentStyle,
                model_override: selectedModel,
                settings: settingsPayload
            };
            
            // Add conversation_id if provided
            if (conversationId) {
                fallbackPayload.conversation_id = conversationId;
            }
            
            const res = await fetch(`${this.apiBaseUrl}/chat`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(fallbackPayload)
            });

            if (!res.ok) {
                throw new Error(`Server responded with status ${res.status}`);
            }

            const data: any = await res.json();
            fullReply = data.reply || "[No response payload]";
            
            // Extract conversation_id from response if present
            const responseCid = data.conversation_id ?? data.conversationId;
            
            // Simulate streaming for fallback
            const chunkSize = 5;
            for (let i = 0; i < fullReply.length; i += chunkSize) {
                const chunk = fullReply.slice(i, i + chunkSize);
                yield { 
                    chunk,
                    ...(responseCid ? { conversationId: responseCid } : {})
                };
                await new Promise(r => setTimeout(r, 10));
            }
        }

        // Save complete interaction to local history
        if (session && fullReply) {
            const currentSession = this.getSession(sessionId);
            if(currentSession) {
                 const updatedMsgs = [...messages, {
                    id: Date.now().toString(),
                    role: 'assistant' as const,
                    content: fullReply,
                    timestamp: Date.now(),
                    modelUsed: resolvedModel as ModelName,
                }];
                this.updateSession(sessionId, { messages: updatedMsgs });
            }
        }

    } catch (e) {
        // Catch connection error, mark as offline, and yield a polite fallback
        console.warn("Backend connection failed. Switching to offline mode.");
        this.isOfflineMode = true;
        
        const errorBody = "⚠️ **CORE OFFLINE**\n\n" +
                          `Connection to \`${this.apiBaseUrl}\` failed. I have switched to offline mode to prevent errors.\n\n` +
                          "Please check if your Uvicorn server and Ollama are running.";

        const chunkSize = 5;
        for (let i = 0; i < errorBody.length; i += chunkSize) {
            yield { chunk: errorBody.slice(i, i + chunkSize) };
            await new Promise(r => setTimeout(r, 5));
        }
    }
  }

  async chatStream(
    payload: { text: string; session_id: string; settings?: any; qb_session_id?: string | null; qb_enabled?: boolean; thinking_mode?: string; conversation_id?: string; rag?: boolean },
    handlers: { onToken: (delta: string) => void; onDone: () => void; onError: (message: string) => void; onMeta?: (resolvedModel: string) => void },
    signal?: AbortSignal
  ): Promise<void> {
    try {
      const body: any = {
        text: payload.text,
        session_id: payload.session_id,
        q: payload.text, // для совместимости
        settings: payload.settings
      };
      
      // Add QB fields if provided
      if (payload.qb_session_id) {
        body.qb_session_id = payload.qb_session_id;
      }
      if (payload.qb_enabled !== undefined) {
        body.qb_enabled = payload.qb_enabled;
      }
      
      // PHASE Q5: Add thinking_mode if provided
      if (payload.thinking_mode) {
        body.thinking_mode = payload.thinking_mode;
      }
      
      // CRITICAL: Add conversation_id if provided
      if (payload.conversation_id) {
        body.conversation_id = payload.conversation_id;
      }
      
      // C2.0: Add rag flag as query parameter (default to 1 if not specified)
      const ragValue = payload.rag !== undefined ? (payload.rag ? "1" : "0") : "1";
      const url = `${this.apiBaseUrl}/chat/stream?rag=${ragValue}`;
      if (DEBUG_UI) console.log(`[C2.0] chatStream request sid=${payload.session_id} rag=${ragValue}`);  // P2.3.1
      
      const response = await fetch(url, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body),
        signal
      });

      // Fallback на обычный /chat если endpoint недоступен
      if (response.status === 404 || response.status === 501 || !response.body) {
        console.warn('[chatStream] SSE endpoint not available, falling back to /chat');
        return this.chatStreamFallback(payload, handlers);
      }

      if (!response.ok) {
        throw new Error(`Server responded with status ${response.status}`);
      }

      const reader = response.body!.getReader();
      const decoder = new TextDecoder();
      let buffer = '';

      try {
        while (true) {
          const { done, value } = await reader.read();
          
          if (done) {
            break;
          }

          buffer += decoder.decode(value, { stream: true });
          const lines = buffer.split('\n');
          buffer = lines.pop() || ''; // Оставляем неполную строку в буфере

          let currentEventType: string | null = null;
          for (const line of lines) {
            const trimmed = line.trim();
            if (!trimmed) continue;

            // Обработка event: строк
            if (trimmed.startsWith('event: ')) {
              currentEventType = trimmed.slice(7).trim();
              continue;
            }

            // Обработка data: строк
            if (trimmed.startsWith('data: ')) {
              const jsonStr = trimmed.slice(6); // Убираем "data: "
              if (!jsonStr) continue;

              try {
                const event = JSON.parse(jsonStr);
                
                // G2: Handle SSE events from /chat/stream
                // Если был event: error, обрабатываем как ошибку
                if (currentEventType === 'error' || event.type === 'error') {
                  handlers.onError(event.message || 'Unknown error');
                  return;
                }
                
                // Handle event types
                if (event.type === 'meta') {
                  handlers.onMeta?.(event.model || event.resolved_model);
                } else if (event.type === 'token' && event.delta) {
                  handlers.onToken(event.delta);
                } else if (event.type === 'done') {
                  // C2.1: Pass context_used from DONE event to handler
                  handlers.onDone(event.context_used);
                  return;
                }
              } catch (e) {
                console.warn('[chatStream] Failed to parse SSE event:', jsonStr, e);
              }
              
              // Сбрасываем тип события после обработки data
              currentEventType = null;
            }
          }
        }

        // Если поток закончился без "done", считаем что завершено
        handlers.onDone();
      } finally {
        reader.releaseLock();
      }
    } catch (error: any) {
      // Если запрос был прерван (AbortError) - пробрасываем ошибку дальше
      if (error.name === 'AbortError' || error.message?.includes('aborted')) {
        throw error;
      }
      console.error('[chatStream] Stream error:', error);
      // Fallback на обычный /chat при ошибке
      return this.chatStreamFallback(payload, handlers);
    }
  }

  private async chatStreamFallback(
    payload: { text: string; session_id: string; settings?: any; qb_session_id?: string | null; qb_enabled?: boolean },
    handlers: { onToken: (delta: string) => void; onDone: () => void; onError: (message: string) => void; onMeta?: (resolvedModel: string) => void }
  ): Promise<void> {
    try {
      const body: any = {
        q: payload.text,
        session_id: payload.session_id,
        settings: payload.settings
      };
      
      // Add QB fields if provided
      if (payload.qb_session_id) {
        body.qb_session_id = payload.qb_session_id;
      }
      if (payload.qb_enabled !== undefined) {
        body.qb_enabled = payload.qb_enabled;
      }
      
      const response = await fetch(`${this.apiBaseUrl}/chat`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body)
      });

      if (!response.ok) {
        throw new Error(`Server responded with status ${response.status}`);
      }

      const data: any = await response.json();
      const reply = data.reply || '[No response]';
      
      // Отдаём весь текст одним чанком
      handlers.onToken(reply);
      handlers.onDone();
    } catch (error: any) {
      handlers.onError(error.message || 'Failed to fetch response');
    }
  }

  async getConversations(limit: number = 50, offset: number = 0, q?: string): Promise<any[]> {
    try {
      const params = new URLSearchParams({
        limit: limit.toString(),
        offset: offset.toString(),
      });
      if (q) {
        params.append('q', q);
      }
      
      const response = await fetch(`${this.apiBaseUrl}/conversations?${params.toString()}`);
      
      if (!response.ok) {
        const errorText = await response.text();
        console.error(`[getConversations] HTTP ${response.status}: ${errorText}`);
        throw new Error(`Failed to fetch conversations: ${response.status}`);
      }
      
      const data = await response.json();
      return data.items || [];
    } catch (error: any) {
      console.error('[getConversations] Error:', error);
      throw error;
    }
  }

  async getConversation(id: string, opts?: { signal?: AbortSignal }): Promise<any> {
    try {
      const response = await fetch(`${this.apiBaseUrl}/conversations/${id}`, {
        signal: opts?.signal
      });
      
      if (!response.ok) {
        if (response.status === 404) {
          throw new Error('Conversation not found');
        }
        const errorText = await response.text();
        console.error(`[getConversation] HTTP ${response.status}: ${errorText}`);
        throw new Error(`Failed to fetch conversation: ${response.status}`);
      }
      
      return await response.json();
    } catch (error: any) {
      // Don't log AbortError (expected when request is cancelled)
      if (error.name !== 'AbortError') {
        console.error('[getConversation] Error:', error);
      }
      throw error;
    }
  }

  // B3 recall: fetch closed sessions list
  async getRecallSessions(params: { limit: number; offset: number; q?: string }): Promise<{ ok: boolean; items: any[]; has_more: boolean }> {
    if (this.appState === AppState.PANIC) {
      return { ok: false, items: [], has_more: false };
    }
    if (this.isOfflineMode) {
      return { ok: false, items: [], has_more: false };
    }
    
    try {
      const urlParams = new URLSearchParams({
        limit: params.limit.toString(),
        offset: params.offset.toString(),
      });
      if (params.q) {
        urlParams.append('q', params.q);
      }
      
      const response = await fetch(`${this.apiBaseUrl}/recall/sessions?${urlParams.toString()}`);
      
      if (!response.ok) {
        const errorText = await response.text();
        console.error(`[getRecallSessions] HTTP ${response.status}: ${errorText}`);
        throw new Error(`Failed to fetch recall sessions: ${response.status}`);
      }
      
      const data = await response.json();
      // Backend returns { ok: true, items: [...], has_more: boolean }
      return {
        ok: data.ok !== false,
        items: Array.isArray(data.items) ? data.items : [],
        has_more: data.has_more === true
      };
    } catch (error: any) {
      // Don't log AbortError (expected when request is cancelled)
      if (error.name !== 'AbortError') {
        console.error('[getRecallSessions] Error:', error);
      }
      throw error;
    }
  }

  async createConversation(title?: string): Promise<{id: string}> {
    try {
      const body: any = {};
      if (title) {
        body.title = title;
      }
      
      const response = await fetch(`${this.apiBaseUrl}/conversations`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body)
      });
      
      if (!response.ok) {
        const errorText = await response.text();
        console.error(`[createConversation] HTTP ${response.status}: ${errorText}`);
        throw new Error(`Failed to create conversation: ${response.status}`);
      }
      
      return await response.json();
    } catch (error: any) {
      console.error('[createConversation] Error:', error);
      throw error;
    }
  }

  // Session-Conversation mapping helpers
  getSessionConversationMap(): Record<string, string> {
    try {
      const stored = localStorage.getItem('air4_session_conversation_map');
      if (!stored) return {};
      return JSON.parse(stored);
    } catch (e) {
      console.error('[getSessionConversationMap] Error:', e);
      return {};
    }
  }

  setSessionConversationMapping(sessionId: string, conversationId: string): void {
    try {
      const map = this.getSessionConversationMap();
      map[sessionId] = conversationId;
      localStorage.setItem('air4_session_conversation_map', JSON.stringify(map));
      if (DEBUG_UI) console.debug('[setSessionConversationMapping]', { sessionId, conversationId });  // P2.3.1
    } catch (e) {
      console.error('[setSessionConversationMapping] Error:', e);
    }
  }

  getConversationIdForSession(sessionId: string): string | null {
    const map = this.getSessionConversationMap();
    const cid = map[sessionId] || null;
    return cid;
  }

  private guessDomain(text: string): Domain {
      const lower = text.toLowerCase();
      if (lower.includes('code') || lower.includes('python') || lower.includes('function')) return 'code';
      if (lower.includes('finance') || lower.includes('cost') || lower.includes('price')) return 'finance';
      if (lower.includes('health') || lower.includes('gym') || lower.includes('run')) return 'fitness';
      return 'general';
  }

  // Normalize session response: handle meta=null case and different response formats
  // Single source of truth for /sessions/{id} response shape
  normalizeSessionResponse(data: any): { meta: any; messages: any[] } {
      if (!data) return { meta: null, messages: [] };

      // messages: try data.messages first, then data.turns
      const messages = Array.isArray(data.messages)
          ? data.messages
          : Array.isArray(data.turns)
              ? data.turns
              : [];

      // meta/session info: try data.meta, then data.session, then build from top-level fields
      const meta =
          data.meta && typeof data.meta === "object" ? data.meta :
          data.session && typeof data.session === "object" ? data.session :
          (data.id ? { id: data.id, title: data.title, created_at: data.created_at, updated_at: data.updated_at, turns: data.turns, summary: data.summary } : null);

      return { meta, messages };
  }
}

export function createAir4Service(apiBaseUrl: string): Air4Service {
  return new Air4ServiceImpl(apiBaseUrl);
}