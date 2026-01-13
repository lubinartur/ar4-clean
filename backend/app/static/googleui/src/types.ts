export type Domain = 'general' | 'code' | 'finance' | 'fitness' | 'creative' | 'long-docs';
export type ModelName =
  | 'Mistral-7B'
  | 'Hermes-7B'
  | 'LLaMA-3.1-8B'
  | 'Qwen-2.5-14B'
  | 'Mixtral-8x7B'
  | 'DeepSeek-32B'
  | 'DeepSeek-14B'
  | 'Offline-Demo';
  
export type ResponseStyle = 'short' | 'normal' | 'detailed';
export type Language = 'ru' | 'en' | 'auto';
export type IngestMode = 'fast' | 'smart' | 'high-precision';
export type ModelMode = 'fast' | 'normal' | 'think' | 'auto';

export interface RouterDecision {
  domain: Domain;
  model: ModelName;
  confidence: number;
  reason: string;
}

export interface SessionConfig {
  model?: string;
  tone?: string;
  density?: string;
  uiLang?: string;
  streaming?: boolean;
  modelMode?: ModelMode;
}

export interface ChatSession {
  id: string;
  title: string;
  lastMessage: string;
  timestamp: number;
  messages: Message[];
  sessionConfig?: SessionConfig;
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
    model_override?: string;
}

export interface Send3Out {
    session_id: string;
    reply: string;
    usage: any;
    memory_ids: string[];
    updated_at: number;
}

// Fact and FactsProfile interfaces
export interface Fact {
    id: string;
    subject: string;
    predicate: string;
    object: string;
    timestamp: number;
    category?: 'profile' | 'food' | 'country' | 'vehicle' | 'location' | 'goals' | 'other';
}

export interface FactsProfile {
    subject: string;
    food: string[];
    country: string[];
    vehicle: string[];
    location: string[];
    goals: string[];
    other: string[];
}
