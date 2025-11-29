
import { Agent, MemoryItem, Message, SystemStats, RouterDecision, AppState, Domain, IngestItem, Send3Out, ChatSession, ModelName, ResponseStyle, Language, IngestMode } from '../types';

const API_BASE = 'http://127.0.0.1:8000';
const STORAGE_KEY_CONFIG = 'air4_config';
const STORAGE_KEY_SESSIONS = 'air4_sessions';

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
    'Mixtral-8x7B'
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

    const savedSessions = localStorage.getItem(STORAGE_KEY_SESSIONS);
    if (savedSessions) {
        this.sessions = JSON.parse(savedSessions);
    } else {
        // Create initial session if none exists
        this.createSession('Local Core Online');
    }
  }

  // --- SESSION MANAGEMENT ---

  getSessions(): ChatSession[] {
      return this.sessions.sort((a, b) => b.timestamp - a.timestamp);
  }

  getSession(id: string): ChatSession | undefined {
      return this.sessions.find(s => s.id === id);
  }

  createSession(initialTitle: string = 'New Session'): ChatSession {
      const newSession: ChatSession = {
          id: Date.now().toString(),
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
      
      const res = await fetch(`${API_BASE}/health`, { signal: controller.signal });
      clearTimeout(timeoutId);
      
      if (!res.ok) throw new Error('Health check failed');
      
      const data = await res.json();
      
      // If we succeed, clear offline mode
      this.isOfflineMode = false;
      this.lastHealthCheck = Date.now();

      let qLength = 0;
      try {
          const queueRes = await fetch(`${API_BASE}/ingest/queue`);
          const queueData = await queueRes.json();
          if (queueData.ok && Array.isArray(queueData.queue)) {
              qLength = queueData.queue.length;
          }
      } catch (e) { /* ignore queue fetch error */ }

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
        const res = await fetch(`${API_BASE}/memory/search?q=${encodeURIComponent(q)}&k=20`);
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
        // Don't set offline mode here to avoid race conditions with health check, just return empty
        return [];
    }
  }
  
  async addManualMemory(content: string, source: string = 'user-selection'): Promise<boolean> {
      if (this.isOfflineMode) return false;
      try {
          const res = await fetch(`${API_BASE}/memory/add`, {
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
          const res = await fetch(`${API_BASE}/ingest/file?tag=ui-upload&mode=${this.config.ingestMode}`, {
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
        const res = await fetch(`${API_BASE}/ingest/queue`);
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

  async *streamChat(messages: Message[], sessionId: string): AsyncGenerator<{ chunk?: string, context?: MemoryItem[], decision?: RouterDecision }, void, unknown> {
    if (this.appState === AppState.PANIC) {
       yield { chunk: "SYSTEM LOCKED. ACCESS DENIED." };
       return;
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
    const selectedModel = this.config.activeModel || 'Mistral-7B';
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
        const mockReply = `[${selectedModel} DEMO MODE - ${currentStyle.toUpperCase()}]\n\nI am currently unable to reach the local backend (127.0.0.1:8000). I am operating in Offline Demo Mode. I can visualize the UI, but I cannot process real data or retrieve memories until the connection is restored.`;
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
        // 2. Call Real Backend
        const res = await fetch(`${API_BASE}/send3`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                text: lastMessage.content,
                session_id: sessionId,
                style: currentStyle, // Pass current response style
                model_override: selectedModel // Send preferred model to backend
            })
        });

        if (!res.ok) {
            throw new Error(`Server responded with status ${res.status}`);
        }

        const data: Send3Out = await res.json();

        if (data.memory_ids && data.memory_ids.length > 0) {
             yield { 
                 context: data.memory_ids.map(id => ({
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
                    contextUsed: data.memory_ids.length > 0 ? [{
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
                          "Connection to `127.0.0.1:8000` failed. I have switched to offline mode to prevent errors.\n\n" +
                          "Please check if your Uvicorn server and Ollama are running.";

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

export const air4 = new Air4Service();
