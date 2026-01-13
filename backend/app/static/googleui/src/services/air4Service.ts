
import { Agent, MemoryItem, Message, SystemStats, RouterDecision, AppState, Domain, IngestItem, Send3Out, ChatSession, ModelName, ResponseStyle, Language, IngestMode, SessionConfig } from '../types';

const STORAGE_KEY_CONFIG = 'air4_config';
const STORAGE_KEY_SESSIONS = 'air4_sessions';

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
  getFacts(subject?: string, limit?: number): Promise<Fact[]>;
  getFactsProfile(subject?: string): Promise<{ subject: string; profile?: string[]; }>;
  addManualMemory(content: string, source?: string): Promise<boolean>;
  addMemoryWithMeta(text: string, meta?: { source?: string; tag?: string; originalTag?: string; score?: number; query?: string; sessionId?: string; pinnedFrom?: string }): Promise<boolean>;
  deleteMemory(id: string): Promise<boolean>;
  uploadFile(file: File): Promise<boolean>;
  getIngestQueueStatus(): Promise<IngestItem[]>;
  streamChat(messages: Message[], sessionId: string, coreSettings?: { temperature?: number; responseTone?: string; outputDensity?: string; interfaceLanguage?: string; activeModel?: string }): AsyncGenerator<{ chunk?: string, context?: MemoryItem[], decision?: RouterDecision }, void, unknown>;
  chatStream(payload: { text: string; session_id: string; settings?: any }, handlers: { onToken: (delta: string) => void; onDone: () => void; onError: (message: string) => void; onMeta?: (resolvedModel: string) => void }, signal?: AbortSignal): Promise<void>;
  getSessionConfig(sessionId: string): SessionConfig | undefined;
  setSessionConfig(sessionId: string, config: SessionConfig): void;
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
    
    console.log('[air4Service] baseUrl =', this.apiBaseUrl);
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

    const savedSessions = localStorage.getItem(STORAGE_KEY_SESSIONS);
    if (savedSessions) {
      try {
        const parsed = JSON.parse(savedSessions);
        this.sessions = Array.isArray(parsed) ? parsed : [];
      } catch (e) {
        console.warn('Failed to parse stored sessions, resetting.', e);
        this.sessions = [];
        localStorage.removeItem(STORAGE_KEY_SESSIONS);
      }
    } else {
      this.sessions = [];
    }

    // If after loading there are no sessions, create an initial one
    // Note: This is fire-and-forget during initialization
    if (this.sessions.length === 0) {
      this.createSession('Local Core Online').catch(err => {
        console.error('[air4Service] Failed to create initial session:', err);
      });
    }
  }

  // --- SESSION MANAGEMENT ---

  getSessions(): ChatSession[] {
      // Filter out invalid (timestamp-based) session IDs from localStorage
      const validSessions = this.sessions.filter(s => isValidBackendSessionId(s.id));
      // If we filtered out invalid sessions, save the cleaned list
      if (validSessions.length !== this.sessions.length) {
          console.warn('[air4Service] Filtered out invalid session IDs from localStorage');
          this.sessions = validSessions;
          this.saveSessions();
      }
      return validSessions.sort((a, b) => b.timestamp - a.timestamp);
  }

  getSession(id: string): ChatSession | undefined {
      return this.sessions.find(s => s.id === id);
  }

  isValidSessionId(id: string | null | undefined): boolean {
      return isValidBackendSessionId(id);
  }

  async getSessionById(id: string, signal?: AbortSignal): Promise<ChatSession> {
      // Guard: only call backend if session ID is valid
      if (!isValidBackendSessionId(id)) {
          throw new Error(`Invalid session ID: ${id}. Session IDs must be created via POST /sessions.`);
      }
      const API_BASE_URL = this.apiBaseUrl;
      
      console.debug('[air4Service] GET', `${this.apiBaseUrl}/sessions/${id}`);
      
      try {
          const res = await fetch(`${API_BASE_URL}/sessions/${id}`, { signal });
          if (!res.ok) {
              if (res.status === 404) {
                  throw new Error('Session not found');
              }
              throw new Error(`Failed to fetch session: ${res.statusText}`);
          }

          const data = await res.json();
          if (!data.ok) {
              throw new Error(data.error || 'Failed to fetch session');
          }

          console.debug('[getSessionById] raw first msg', data.messages?.[0]);

          // Нормализация id (может быть session_id или id)
          const sessionId = data.id || id;
          
          // Преобразование messages из формата backend в формат Message
          const normalizedMessages: Message[] = (data.messages || []).map((msg: any, index: number) => {
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
              const timestamp = msg.ts || msg.timestamp || msg.time || data.timestamp || Date.now();
              
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
              title: data.title || 'New session',
              messages: normalizedMessages,
              lastMessage: data.lastMessage || '',
              timestamp: data.timestamp || Date.now(),
          };

          return session;
      } catch (error) {
          console.error('[air4Service] getSessionById error:', error);
          throw error;
      }
  }

  upsertSession(session: ChatSession): void {
      const index = this.sessions.findIndex(s => s.id === session.id);
      if (index !== -1) {
          // Обновляем существующую сессию
          this.sessions[index] = session;
      } else {
          // Добавляем новую сессию
          this.sessions.unshift(session);
      }
      this.saveSessions();
  }

  async createSession(initialTitle: string = 'New Session'): Promise<ChatSession> {
      // Call backend POST /sessions to create a session with valid session_id
      let backendSessionId: string;
      try {
          const res = await fetch(`${this.apiBaseUrl}/sessions`, {
              method: 'POST',
              headers: { 'Content-Type': 'application/json' }
          });
          if (!res.ok) {
              throw new Error(`Failed to create session: ${res.statusText}`);
          }
          const data = await res.json();
          backendSessionId = data.id;
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

  private saveSessions() {
      localStorage.setItem(STORAGE_KEY_SESSIONS, JSON.stringify(this.sessions));
  }

  private updateSession(id: string, updates: Partial<ChatSession>) {
      const index = this.sessions.findIndex(s => s.id === id);
      if (index !== -1) {
          this.sessions[index] = { ...this.sessions[index], ...updates };
          this.saveSessions();
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

  async getFacts(subject: string = "Arch", limit: number = 64): Promise<Fact[]> {
      if (this.appState === AppState.PANIC) return [];
      if (this.isOfflineMode) return [];
      try {
          const res = await fetch(`${this.apiBaseUrl}/facts?subject=${encodeURIComponent(subject)}&limit=${limit}`);
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
          const url = `${this.apiBaseUrl}/facts/profile?subject=${encodeURIComponent(subject)}`;
          console.log('[Store/Profile] request url:', url);
          const res = await fetch(url);
          if (!res.ok) {
              throw new Error("Facts profile fetch failed");
          }
          const data = await res.json();
          console.log('[Store/Profile] response:', data);

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

  async deleteMemory(id: string): Promise<boolean> {
      if (this.isOfflineMode) return false;
      if (this.appState === AppState.PANIC) return false;
      try {
          const res = await fetch(`${this.apiBaseUrl}/memory/delete`, {
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

  async *streamChat(messages: Message[], sessionId: string, coreSettings?: { temperature?: number; responseTone?: string; outputDensity?: string; interfaceLanguage?: string; activeModel?: string }): AsyncGenerator<{ chunk?: string, context?: MemoryItem[], decision?: RouterDecision }, void, unknown> {
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

        const res = await fetch(`${this.apiBaseUrl}/chat`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                q: lastMessage.content,
                session_id: sessionId,
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
            const currentSession = this.getSession(sessionId);
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
    payload: { text: string; session_id: string; settings?: any },
    handlers: { onToken: (delta: string) => void; onDone: () => void; onError: (message: string) => void; onMeta?: (resolvedModel: string) => void },
    signal?: AbortSignal
  ): Promise<void> {
    try {
      const response = await fetch(`${this.apiBaseUrl}/chat/stream`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          text: payload.text,
          session_id: payload.session_id,
          q: payload.text, // для совместимости
          settings: payload.settings
        }),
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
                
                // Если был event: error, обрабатываем как ошибку
                if (currentEventType === 'error') {
                  handlers.onError(event.message || 'Unknown error');
                  return;
                }
                
                // Иначе проверяем type в JSON (старый формат)
                if (event.type === 'token' && event.delta) {
                  handlers.onToken(event.delta);
                } else if (event.type === 'done') {
                  handlers.onDone();
                  return;
                } else if (event.type === 'error') {
                  handlers.onError(event.message || 'Unknown error');
                  return;
                } else if (event.type === 'meta' && event.resolved_model) {
                  handlers.onMeta?.(event.resolved_model);
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
    payload: { text: string; session_id: string; settings?: any },
    handlers: { onToken: (delta: string) => void; onDone: () => void; onError: (message: string) => void; onMeta?: (resolvedModel: string) => void }
  ): Promise<void> {
    try {
      const response = await fetch(`${this.apiBaseUrl}/chat`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          q: payload.text,
          session_id: payload.session_id,
          settings: payload.settings
        })
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

  private guessDomain(text: string): Domain {
      const lower = text.toLowerCase();
      if (lower.includes('code') || lower.includes('python') || lower.includes('function')) return 'code';
      if (lower.includes('finance') || lower.includes('cost') || lower.includes('price')) return 'finance';
      if (lower.includes('health') || lower.includes('gym') || lower.includes('run')) return 'fitness';
      return 'general';
  }
}

export function createAir4Service(apiBaseUrl: string): Air4Service {
  return new Air4ServiceImpl(apiBaseUrl);
}