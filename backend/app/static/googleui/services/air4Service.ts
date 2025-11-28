
import { Agent, MemoryItem, Message, SystemStats, RouterDecision, AppState, Domain, IngestItem, Send3Out } from '../types';

const API_BASE = 'http://127.0.0.1:8000';
const STORAGE_KEY_CONFIG = 'air4_config';
const STORAGE_KEY_SESSION_ID = 'air4_session_id';

// Initial Agents / Modules aligned with Domains
export const AVAILABLE_AGENTS: Agent[] = [
  { id: 'general', name: 'Prime Core', description: 'General logic, reasoning.', icon: 'Cpu', systemPrompt: 'You are AIr4.', domain: 'general', enabled: true },
  { id: 'fitness', name: 'Bio-Monitor', description: 'Health & metrics.', icon: 'Activity', systemPrompt: 'Focus on physiology.', domain: 'fitness', enabled: false },
  { id: 'finance', name: 'Ledger', description: 'Budget & market analysis.', icon: 'DollarSign', systemPrompt: 'Focus on finance.', domain: 'finance', enabled: false },
  { id: 'code', name: 'Dev-Ops', description: 'Code & debugging.', icon: 'Terminal', systemPrompt: 'Focus on code.', domain: 'code', enabled: false },
];

class Air4Service {
  private config: { setupComplete: boolean; agents: Agent[]; userName: string };
  private appState: AppState = AppState.ACTIVE;
  private ingestQueue: IngestItem[] = [];
  private isOfflineMode: boolean = false;
  private lastHealthCheck: number = 0;

  constructor() {
    const savedConfig = localStorage.getItem(STORAGE_KEY_CONFIG);
    if (savedConfig) {
      this.config = JSON.parse(savedConfig);
    } else {
      this.config = { setupComplete: false, agents: AVAILABLE_AGENTS, userName: '' };
    }
  }

  isSetupComplete(): boolean {
    return this.config.setupComplete;
  }
  
  getUserName(): string {
      return this.config.userName || 'Operator';
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
      localStorage.removeItem(STORAGE_KEY_SESSION_ID);
      window.location.reload();
  }

  saveConfig(agents: Agent[], userName: string) {
    this.config = { setupComplete: true, agents, userName };
    localStorage.setItem(STORAGE_KEY_CONFIG, JSON.stringify(this.config));
  }

  resetChatSession(): void {
    localStorage.removeItem(STORAGE_KEY_SESSION_ID);
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
        modelName: data.model || 'Unknown'
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
          const res = await fetch(`${API_BASE}/ingest/file?tag=ui-upload`, {
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
                status: 'processing',
                progress: 50,
                timestamp: Date.now()
            }));
        }
        return [];
      } catch (e) {
          return [];
      }
  }

  async getSessions(): Promise<any[]> {
    if (this.appState === AppState.PANIC) return [];
    if (this.isOfflineMode) return [];

    try {
      const res = await fetch(`${API_BASE}/sessions`);
      if (!res.ok) throw new Error('Failed to fetch sessions');
      const data = await res.json();
      if (Array.isArray(data)) return data;
      if (Array.isArray(data?.sessions)) return data.sessions;
      return [];
    } catch (e) {
      console.warn('getSessions failed', e);
      return [];
    }
  }

  // --- CHAT LOGIC ---

  async sendMessage(text: string, sessionId?: string | null): Promise<any> {
    if (this.appState === AppState.PANIC) {
      return { reply: 'SYSTEM LOCKED. ACCESS DENIED.' };
    }

    if (this.isOfflineMode) {
      return {
        reply: '⚠️ CORE OFFLINE: UI работает, но соединения с 127.0.0.1:8000 нет. Проверь Uvicorn и Ollama.'
      };
    }

    const payload: any = { text };
    if (sessionId) {
      payload.session_id = sessionId;
    }

    const res = await fetch(`${API_BASE}/chat`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify(payload),
    });

    if (!res.ok) {
      throw new Error(`Failed to send message: ${res.status} ${res.statusText}`);
    }

    return res.json();
  }

  async *streamChat(messages: Message[]): AsyncGenerator<{ chunk?: string, context?: MemoryItem[], decision?: RouterDecision }, void, unknown> {
    if (this.appState === AppState.PANIC) {
       yield { chunk: "SYSTEM LOCKED. ACCESS DENIED." };
       return;
    }

    const lastMessage = messages[messages.length - 1].content;
    let storedSessionId = localStorage.getItem(STORAGE_KEY_SESSION_ID) || undefined;

    // 1. Simulate Router (UI only)
    const simulatedDomain = this.guessDomain(lastMessage);
    yield { 
        decision: { 
            domain: simulatedDomain, 
            model: this.isOfflineMode ? 'Offline-Demo' : 'Mistral-7B', 
            confidence: 0.85, 
            reason: 'Routed via local rules' 
        } 
    };

    // If we already know we are offline, skip fetch to prevent error
    if (this.isOfflineMode) {
        const mockReply = "I am currently unable to reach the local backend (127.0.0.1:8000). I am operating in Offline Demo Mode. I can visualize the UI, but I cannot process real data or retrieve memories until the connection is restored.";
        const chunkSize = 4;
        for (let i = 0; i < mockReply.length; i += chunkSize) {
            yield { chunk: mockReply.slice(i, i + chunkSize) };
            await new Promise(r => setTimeout(r, 15));
        }
        return;
    }

    try {
        // 2. Call Real Backend
        const res = await fetch(`${API_BASE}/send3`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                text: lastMessage,
                session_id: storedSessionId,
                style: 'normal'
            })
        });

        if (!res.ok) {
            throw new Error(`Server responded with status ${res.status}`);
        }

        const data: Send3Out = await res.json();
        
        if (data.session_id) {
            localStorage.setItem(STORAGE_KEY_SESSION_ID, data.session_id);
        }

        if (data.memory_ids && data.memory_ids.length > 0) {
             yield { 
                 context: data.memory_ids.map(id => ({
                     id, 
                     content: `Ref: ${id.substring(0, 8)}...`, 
                     category: 'fact', 
                     namespace: 'facts', 
                     timestamp: Date.now()
                 }))
             };
        }

        const reply = data.reply || "[No response payload]";
        const chunkSize = 5;
        
        for (let i = 0; i < reply.length; i += chunkSize) {
            const chunk = reply.slice(i, i + chunkSize);
            yield { chunk };
            await new Promise(r => setTimeout(r, 10));
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
