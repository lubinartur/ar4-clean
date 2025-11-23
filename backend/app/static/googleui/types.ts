
export type Domain = 'general' | 'code' | 'finance' | 'fitness' | 'creative' | 'long-docs';
export type ModelName = 'Mistral-7B' | 'Hermes-7B' | 'LLaMA-3.1-8B' | 'Qwen-2.5-14B' | 'Mixtral-8x7B';

export interface RouterDecision {
  domain: Domain;
  model: ModelName;
  confidence: number;
  reason: string;
}

export interface Message {
  id: string;
  role: 'user' | 'assistant' | 'system';
  content: string;
  timestamp: number;
  contextUsed?: MemoryItem[]; // RAG context visualization
  modelUsed?: ModelName;
  domain?: Domain;
}

export interface MemoryItem {
  id: string;
  content: string;
  category: 'fact' | 'conversation_summary' | 'document' | 'note';
  namespace: 'facts' | 'sessions' | 'docs' | 'profile' | 'ingest';
  timestamp: number;
  relevanceScore?: number;
  source?: string;
  meta?: any;
}

export type IngestStatus = 'queued' | 'processing' | 'indexed' | 'error';

export interface IngestItem {
  id: string;
  filename: string;
  size: number; // in bytes
  type: string;
  status: IngestStatus;
  progress: number; // 0-100
  timestamp: number;
}

export interface Agent {
  id: string;
  name: string;
  description: string;
  icon: string;
  systemPrompt: string;
  domain: Domain;
  enabled: boolean;
}

export interface SystemStats {
  uptime: number;
  memoriesIndexed: number;
  activeAgents: number;
  lastBackup: string;
  storageUsage: string;
  routerAccuracy: number;
  ltmHitRate: number;
  ingestQueueLength: number;
  isOffline: boolean;
  modelName: string;
}

export enum AppState {
  SETUP = 'SETUP',
  LOCKED = 'LOCKED',
  ACTIVE = 'ACTIVE',
  PANIC = 'PANIC'
}

// Backend specific types
export interface Send3In {
    text: string;
    session_id?: string;
    style?: string;
}

export interface Send3Out {
    session_id: string;
    reply: string;
    usage: any;
    memory_ids: string[];
    updated_at: number;
}
