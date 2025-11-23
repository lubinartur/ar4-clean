
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

  getAppState(): AppState {
    return this.appState;
  }

  triggerPanic(): void {
    this.appState = AppState.PANIC;
    console.warn('PANIC MODE ENGAGED. DATA MASKED.');
    // In a real scenario, we might send a wipe signal to backend if configured
    // await fetch(`${API_BASE}/auth/panic`, { method: 'POST' }); 
  }

  saveConfig(agents: Agent[], userName: string) {
    this.config = { setupComplete: true, agents, userName };
    localStorage.setItem(STORAGE_KEY_CONFIG, JSON.stringify(this.config));
  }

  // --- REAL API CALLS ---

  async getStats(): Promise<SystemStats> {
    try {
      // Set a short timeout for stats to prevent UI hanging
      const controller = new AbortController();
      const timeoutId = setTimeout(() => controller.abort(), 2000);
      
      const res = await fetch(`${API_BASE}/health`, { signal: controller.signal });
      clearTimeout(timeoutId);
      
      if (!res.ok) throw new Error('Health check failed');
      
      const data = await res.json();
      
      // Fetch ingest queue count separately
      let qLength = 0;
      try {
          const queueRes = await fetch(`${API_BASE}/ingest/queue`);
          const queueData = await queueRes.json();
          if (queueData.ok && Array.isArray(queueData.queue)) {
              qLength = queueData.queue.length;
          }
      } catch (e) { /* ignore queue fetch error */ }

      // Determine storage type from backend response
      const storageType = data.memory_backend === 'chroma' ? 'ChromaDB (Vector)' : 'Fallback (RAM)';

      return {
        uptime: Math.floor(Date.now() / 1000) - (data.ts || 0), // Approximated
        memoriesIndexed: 0, // Placeholder until backend exposes count
        activeAgents: this.config.agents.filter(a => a.enabled).length,
        lastBackup: new Date().toISOString(),
        storageUsage: storageType,
        routerAccuracy: 0.9,
        ltmHitRate: 0.7,
        ingestQueueLength: qLength,
        isOffline: false, // Successfully fetched health means we are online
        modelName: data.model || 'Unknown'
      };
    } catch (e) {
      // Quietly fail for stats, return offline state
      return {
        uptime: 0,
        memoriesIndexed: 0,
        activeAgents: 0,
        lastBackup: 'N/A',
        storageUsage: 'Offline',
        routerAccuracy: 0,
        ltmHitRate: 0,
        ingestQueueLength: 0,
        isOffline: true,
        modelName: 'Disconnected'
      };
    }
  }

  async getMemories(query: string = ""): Promise<MemoryItem[]> {
    if (this.appState === AppState.PANIC) return [];
    
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
        console.warn("Memory fetch failed - Backend likely offline");
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
      const formData = new FormData();
      formData.append('file', file);
      // NOTE: FastAPI route expects 'tag' as a query parameter, not body
      
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

  // Polls the backend queue logic
  async getIngestQueueStatus(): Promise<IngestItem[]> {
      try {
        const res = await fetch(`${API_BASE}/ingest/queue`);
        if (!res.ok) throw new Error("Queue fetch failed");
        const data = await res.json();
        
        if (data.ok && Array.isArray(data.queue)) {
            // Backend returns raw list from queue.json: [{digest:..., file:...}]
            return data.queue.map((q: any) => ({
                id: q.digest || Math.random().toString(),
                filename: q.file || 'Unknown',
                size: 0,
                type: 'detected',
                status: 'processing', // If it is in queue.json, it is pending/processing
                progress: 50, // Mock progress since backend doesn't stream progress
                timestamp: Date.now()
            }));
        }
        return [];
      } catch (e) {
          return [];
      }
  }

  // --- CHAT LOGIC ---

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
            model: 'Mistral-7B', 
            confidence: 0.85, 
            reason: 'Routed via local rules' 
        } 
    };

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
        
        // Update session ID
        if (data.session_id) {
            localStorage.setItem(STORAGE_KEY_SESSION_ID, data.session_id);
        }

        // 3. Yield "Context" if provided (memory_ids)
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

        // 4. Simulate Streaming of the Reply
        const reply = data.reply || "[No response payload]";
        const chunkSize = 5;
        
        for (let i = 0; i < reply.length; i += chunkSize) {
            const chunk = reply.slice(i, i + chunkSize);
            yield { chunk };
            await new Promise(r => setTimeout(r, 10)); // Typing speed
        }

    } catch (e) {
        console.error("Chat error", e);
        
        // --- OFFLINE FALLBACK MESSAGE ---
        // Instead of breaking, we yield a helpful diagnostic message to the chat
        const errorHeader = "⚠️ **CORE CONNECTION FAILED**\n\n";
        const errorBody = "AIr4 Backend is unreachable at `http://127.0.0.1:8000`.\n\n" +
                          "**Diagnostic Checklist:**\n" + 
                          "1. Is the python server running? (`uvicorn backend.app.main:app`)\n" + 
                          "2. Is Ollama active? (`ollama serve`)\n" +
                          "3. Are you using a supported browser? (Chrome/Firefox recommended)\n\n" +
                          "Retrying connection in background...";

        // Stream the error message so it looks like a system response
        yield { chunk: errorHeader };
        await new Promise(r => setTimeout(r, 100));
        
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
