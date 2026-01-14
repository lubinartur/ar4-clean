import React, { useState, useEffect } from 'react';
import { useAir4 } from '../contexts/Air4Context';
import { MemoryItem, Fact } from '../types';
import {
  Search,
  RefreshCw,
  Zap,
  Database,
  Filter,
  Hash,
  Trash2,
  User,
  MapPin,
  Globe,
  Utensils,
  Target,
  Layers,
  Pin,
  Info,
  ChevronDown,
  Copy,
  ClipboardCheck,
} from 'lucide-react';

interface ProfileData {
  subject: string;
  profile?: string[];
}

// Helper для парсинга meta-префикса
function splitMeta(content: string) {
  const text = content ?? "";
  const m = text.match(/^\s*\[Meta:\s*([^\]]+)\]\s*/i);
  if (!m) return { meta: null as string | null, clean: text.trim() };
  const meta = m[1].trim();
  const clean = text.slice(m[0].length).trim();
  return { meta, clean };
}

// Helper для парсинга meta-строки
function parseMeta(meta: string) {
  const obj: Record<string, string> = {};
  meta.split(",").forEach(part => {
    const idx = part.indexOf(":");
    if (idx === -1) return;
    const key = part.slice(0, idx).trim();
    const value = part.slice(idx + 1).trim();
    if (key && value) obj[key] = value;
  });
  return obj;
}

interface MemoryProps {
  activeSessionId: string | null;
}

const Memory: React.FC<MemoryProps> = ({ activeSessionId }) => {
  const air4 = useAir4();
  const [memories, setMemories] = useState<MemoryItem[]>([]);
  const [searchTerm, setSearchTerm] = useState('');
  const [activeTab, setActiveTab] = useState<'all' | 'facts' | 'sessions' | 'docs' | 'profile' | 'pinned'>('all');
  const [loading, setLoading] = useState(false);
  const [profile, setProfile] = useState<ProfileData | null>(null);
  const [facts, setFacts] = useState<Fact[]>([]);
  const [showNoisyPinned, setShowNoisyPinned] = useState(false);
  const [metaOpen, setMetaOpen] = useState<Record<string, boolean>>({});
  const [queryOpen, setQueryOpen] = useState<Record<string, boolean>>({});
  const [copiedSessionId, setCopiedSessionId] = useState<string | null>(null);
  const [profileCategoriesOpen, setProfileCategoriesOpen] = useState<Record<string, boolean>>({
    profile: true,
  });
  const [bulkDeleteBy, setBulkDeleteBy] = useState<"id" | "tag" | "namespace">("tag");
  const [bulkDeleteValue, setBulkDeleteValue] = useState("");
  
  const toggleMeta = (id: string) => setMetaOpen(p => ({...p, [id]: !p[id]}));
  const toggleQuery = (id: string) => setQueryOpen(p => ({...p, [id]: !p[id]}));
  
  const handleCopySession = (sessionId: string, memoryId: string) => {
    navigator.clipboard.writeText(sessionId);
    setCopiedSessionId(memoryId);
    setTimeout(() => setCopiedSessionId(null), 2000);
  };
  
  // Helper functions для определения мусорных воспоминаний
  const SMALLTALK_RE = /(привет|здаров|как дела|спасибо|ок(ей)?|норм|понял|ага|давай|хорошо|ясно)/i;
  
  function isQuestionLike(text: string) {
    const t = text.trim();
    return t.includes("?") || /^(что|как|почему|зачем|где|когда|сколько|какой|какая|какие|можно ли)\b/i.test(t);
  }
  
  function isTooShort(text: string) {
    return text.trim().length < 22;
  }
  
  function isNoisyMemory(text: string) {
    const t = (text ?? "").trim();
    if (!t) return true;
    if (SMALLTALK_RE.test(t)) return true;
    if (isTooShort(t)) return true;
    if (isQuestionLike(t)) return true;
    return false;
  }

  const doSearch = async (query: string) => {
    setLoading(true);
    try {
      // Use activeSessionId or fall back to first available session
      let sessionId = activeSessionId;
      if (!sessionId) {
        const sessions = air4.getSessions();
        if (sessions.length > 0) {
          sessionId = sessions[0].id;
        } else {
          console.warn('[Memory] No session available for memory search');
          setMemories([]);
          return;
        }
      }
      const results = await air4.getMemories(query, sessionId);
      setMemories(results);
    } finally {
      setLoading(false);
    }
  };

  const handleDelete = async (id: string, e: React.MouseEvent) => {
    e.stopPropagation();
    if (!activeSessionId) {
      alert('No active session selected');
      return;
    }
    if (confirm('Are you sure you want to delete this memory vector?\n\nThis action cannot be undone.')) {
      // Phase E: Pass sessionId for backend validation
      const success = await air4.deleteMemory(id, activeSessionId || undefined);
      if (success) {
        // Refresh memories from backend using the same method as initial load
        await doSearch(searchTerm);
      }
    }
  };

  const handleBulkDelete = async () => {
    if (!activeSessionId) {
      alert('No active session selected');
      return;
    }
    if (!bulkDeleteValue.trim()) {
      alert('Please enter a value to delete');
      return;
    }
    const byLabel = bulkDeleteBy === 'id' ? 'ID' : bulkDeleteBy === 'tag' ? 'tag' : 'namespace';
    const warning = `Are you sure you want to delete ALL memories with ${byLabel}="${bulkDeleteValue}"?\n\nThis action cannot be undone and will affect multiple items.`;
    if (confirm(warning)) {
      const success = await air4.deleteMemoryBy(bulkDeleteBy, bulkDeleteValue.trim(), activeSessionId || undefined);
      if (success) {
        setBulkDeleteValue("");
        // Refresh memories from backend using the same method as initial load
        await doSearch(searchTerm);
      } else {
        alert('Failed to delete memories');
      }
    }
  };

  // Initial load of vector memories
  useEffect(() => {
    void doSearch('');
  }, []);

  // Debounced search for vector memories
  useEffect(() => {
    const timer = setTimeout(() => {
      void doSearch(searchTerm);
    }, 600);
    return () => clearTimeout(timer);
  }, [searchTerm]);

  // Очистка metaOpen и queryOpen при смене activeTab
  useEffect(() => {
    setMetaOpen({});
    setQueryOpen({});
  }, [activeTab]);

  // Load structured profile when switching to Profile tab
  // Force refresh on tab switch (no stale cache)
  useEffect(() => {
    if (activeTab !== 'profile') return;

    let cancelled = false;
    const loadProfile = async () => {
      setLoading(true);
      try {
        console.log('[Store/Profile] Loading profile for tab switch');
        const p = await air4.getFactsProfile('Arch');
        console.log('[Store/Profile] Profile loaded:', p);
        if (!cancelled) {
          setProfile(p);
        }
      } catch (e) {
        console.error('[Store/Profile] Failed to load profile:', e);
      } finally {
        if (!cancelled) {
          setLoading(false);
        }
      }
    };

    void loadProfile();

    return () => {
      cancelled = true;
    };
  }, [activeTab]); // Зависимость от activeTab обеспечивает обновление при переключении

  // Load facts when switching to Facts tab (debug)
  useEffect(() => {
    if (activeTab !== 'facts') return;

    let cancelled = false;
    const loadFacts = async () => {
      setLoading(true);
      try {
        console.log('[Store/Facts] Loading facts for debug');
        const f = await air4.getFacts('Arch', 200);
        console.log('[Store/Facts] Facts loaded:', f.length);
        if (!cancelled) {
          setFacts(f);
        }
      } catch (e) {
        console.error('[Store/Facts] Failed to load facts:', e);
      } finally {
        if (!cancelled) {
          setLoading(false);
        }
      }
    };

    void loadFacts();

    return () => {
      cancelled = true;
    };
  }, [activeTab]);

  const filteredMemories = memories.filter((m) => {
    if (activeTab === 'all') return true;

    if (activeTab === 'pinned') {
      // Pinned: проверяем tag в metadata или в тексте
      const metaTag = (m.meta as any)?.tag;
      const contentHasRagPin = m.content.includes('[Meta:') && m.content.includes('Tag: rag_pin');
      const isPinned = metaTag === 'rag_pin' || contentHasRagPin;
      
      if (!isPinned) return false;
      
      // Если showNoisyPinned === false, фильтруем мусор
      if (!showNoisyPinned) {
        // Извлекаем чистый текст (убираем метаданные префикс)
        let cleanText = m.content;
        if (cleanText.includes('[Meta:')) {
          const metaEnd = cleanText.indexOf(']\n\n');
          if (metaEnd !== -1) {
            cleanText = cleanText.substring(metaEnd + 4);
          }
        }
        return !isNoisyMemory(cleanText);
      }
      
      return true;
    }

    if (activeTab === 'docs') {
      // Документы: либо явный namespace 'docs', либо любые записи с непустым source
      const src = (m as any).source || '';
      return m.namespace === 'docs' || src !== '';
    }

    return m.namespace === activeTab;
  });

  const tabs: { id: 'all' | 'facts' | 'sessions' | 'docs' | 'profile' | 'pinned'; label: string; icon?: React.ComponentType<{ className?: string }> }[] = [
    { id: 'all', label: 'All' },
    { id: 'facts', label: 'Facts' },
    { id: 'profile', label: 'Profile' },
    { id: 'sessions', label: 'Sessions' },
    { id: 'docs', label: 'Docs' },
    { id: 'pinned', label: 'Pinned' },
  ];

  const hasProfileData = (p: ProfileData | null): boolean => {
    if (!p) return false;
    return Boolean(p.profile && p.profile.length > 0);
  };

  // Фильтрация мусорных фактов (только для UI, не трогает backend)
  const filterValidFact = (fact: string): boolean => {
    const trimmed = fact.trim();
    if (!trimmed) return false;
    
    // Игнорируем факты < 3 символов
    if (trimmed.length < 3) return false;
    
    // Игнорируем мусорные паттерны
    const lower = trimmed.toLowerCase();
    
    // FACTS_001, FACTS_002 и т.д.
    if (/^facts_\d+/i.test(trimmed)) return false;
    
    // Только цифры
    if (/^(\d+)$/.test(trimmed)) return false;
    
    // Начинается с "запомнил"
    if (/^запомнил/i.test(trimmed)) return false;
    
    // Содержит "запомни" как отдельное слово (legacy мусор)
    if (/\bзапомни\b/i.test(trimmed)) return false;
    
    // Игнорируем одно слово (но факты вида "predicate — object" пройдут, т.к. содержат "—")
    const words = trimmed.split(/\s+/);
    if (words.length === 1 && !trimmed.includes('—') && !trimmed.includes('-')) return false;
    
    return true;
  };

  const renderProfileTab = () => {
    if (!hasProfileData(profile)) {
      return (
        <div className="h-full flex flex-col items-center justify-center text-slate-600 space-y-4">
          <div className="w-16 h-16 rounded-full bg-purple-500/10 flex items-center justify-center border border-purple-500/30">
            <User className="w-8 h-8 opacity-60 text-purple-400" />
          </div>
          <span className="text-sm">
            {loading ? 'Loading profile from knowledge graph…' : 'No structured profile data yet.'}
          </span>
          <span className="text-[11px] text-slate-500 max-w-xs text-center">
            The assistant will slowly build your profile from chats and facts. Ask personal questions or state preferences to enrich it.
          </span>
        </div>
      );
    }

    const p = profile!;

    const section = (
      categoryKey: string,
      title: string,
      items?: string[],
      accentClasses?: string,
      Icon?: React.ComponentType<{ className?: string }>
    ) => {
      if (!items || items.length === 0) return null;
      
      // Фильтруем мусорные факты
      const validItems = items.filter(filterValidFact);
      if (validItems.length === 0) return null;
      
      const isOpen = profileCategoriesOpen[categoryKey] ?? true;
      
      return (
        <div className="glass-card rounded-2xl p-4 border border-white/10 bg-white/5 flex flex-col gap-2">
          <button
            onClick={() => setProfileCategoriesOpen(prev => ({ ...prev, [categoryKey]: !isOpen }))}
            className="flex items-center justify-between w-full"
          >
            <div
              className={`inline-flex items-center gap-2 text-[11px] font-semibold uppercase tracking-widest px-2.5 py-1 rounded-full border ${
                accentClasses || 'bg-purple-500/10 text-purple-300 border-purple-500/30'
              }`}
            >
              {Icon ? (
                <Icon className="w-3 h-3" />
              ) : (
                <Hash className="w-3 h-3" />
              )}
              {title}
            </div>
            <ChevronDown className={`w-4 h-4 text-slate-400 transition-transform ${isOpen ? 'rotate-180' : ''}`} />
          </button>
          {isOpen && (
            <div className="flex flex-wrap gap-1.5 mt-1">
              {validItems.map((it) => (
                <span
                  key={it}
                  className="px-2 py-1 rounded-full bg-black/30 border border-white/10 text-[11px] text-slate-100"
                >
                  {it}
                </span>
              ))}
            </div>
          )}
        </div>
      );
    };

    // Показываем только profile секцию
    const categoryOrder = ['profile'];
    const categoryMap: Record<string, React.ReactNode> = {
      profile: section('profile', 'Profile', p.profile, 'bg-purple-500/15 text-purple-200 border-purple-500/40', User),
    };
    
    const sections = categoryOrder
      .map(key => categoryMap[key])
      .filter(Boolean);

    return (
      <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-4 animate-fade-in-up">
        {sections}
      </div>
    );
  };

  return (
    <div className="h-full flex flex-col p-8 relative overflow-hidden">
      {/* Header Section */}
      <div className="flex flex-col md:flex-row justify-between items-start md:items-end mb-8 gap-4 flex-shrink-0 animate-fade-in-up">
        <div>
          <div className="flex items-center gap-3 mb-2">
            <div className="p-2 rounded-lg bg-air-500/10 text-air-500 border border-air-500/20 shadow-[0_0_15px_rgba(249,115,22,0.1)]">
              <Database className="w-5 h-5" />
            </div>
            <h2 className="text-2xl font-bold text-white tracking-tight">Store</h2>
          </div>
          <p className="text-sm text-slate-400 max-w-lg leading-relaxed ml-1">
            Documents, notes, and facts.
          </p>
        </div>

        {/* Filter Chips */}
        <div className="flex flex-wrap items-center gap-2">
          {tabs.map((tab) => (
            <button
              key={tab.id}
              onClick={() => setActiveTab(tab.id)}
              className={`px-4 py-1.5 rounded-full text-[10px] font-bold uppercase tracking-wider transition-all duration-300 border flex items-center gap-1.5 ${
                activeTab === tab.id
                  ? tab.id === 'pinned'
                    ? 'bg-emerald-500 text-white border-emerald-500 shadow-[0_0_15px_rgba(16,185,129,0.3)] scale-105'
                    : 'bg-air-500 text-white border-air-500 shadow-[0_0_15px_rgba(249,115,22,0.3)] scale-105'
                  : 'bg-white/5 text-slate-500 border-white/5 hover:bg-white/10 hover:text-slate-300 hover:border-white/10'
              }`}
            >
              {tab.id === 'pinned' && <Pin className="w-3 h-3" />}
              {tab.label}
            </button>
          ))}
          
          {/* Show noisy pinned toggle - только для вкладки Pinned */}
          {activeTab === 'pinned' && (
            <label className="flex items-center gap-1.5 px-3 py-1.5 rounded-full text-[10px] font-medium text-slate-400 border border-white/5 bg-white/5 hover:bg-white/10 cursor-pointer transition-colors">
              <input
                type="checkbox"
                checked={showNoisyPinned}
                onChange={(e) => setShowNoisyPinned(e.target.checked)}
                className="w-3 h-3 rounded border-white/20 bg-white/5 text-emerald-500 focus:ring-emerald-500/50 cursor-pointer"
              />
              <span>Show noisy pinned</span>
            </label>
          )}
        </div>
      </div>

      {/* Search Bar */}
      <div
        className="relative mb-6 flex-shrink-0 animate-fade-in-up"
        style={{ animationDelay: '0.1s' }}
      >
        <div className="absolute left-4 top-1/2 -translate-y-1/2 text-air-500/50">
          <Search className="w-5 h-5" />
        </div>
        <input
          type="text"
          placeholder="Search vectors..."
          value={searchTerm}
          onChange={(e) => setSearchTerm(e.target.value)}
          className="w-full glass-input rounded-2xl pl-12 pr-4 py-4 text-white placeholder-slate-600 focus:outline-none focus:border-air-500/50 focus:bg-white/5 transition-all text-sm shadow-inner border border-white/5"
        />
        {loading && activeTab !== 'profile' && (
          <div className="absolute right-4 top-1/2 -translate-y-1/2 text-air-500">
            <RefreshCw className="w-4 h-4 animate-spin" />
          </div>
        )}
      </div>

      {/* Bulk Delete Controls */}
      <div className="mb-4 flex-shrink-0 flex items-center gap-2 animate-fade-in-up" style={{ animationDelay: '0.15s' }}>
        <select
          value={bulkDeleteBy}
          onChange={(e) => setBulkDeleteBy(e.target.value as "id" | "tag" | "namespace")}
          className="glass-input rounded-lg px-3 py-2 text-white bg-white/5 border border-white/5 focus:outline-none focus:border-red-500/50 focus:bg-white/10 transition-all text-sm"
        >
          <option value="id">ID</option>
          <option value="tag">Tag</option>
          <option value="namespace">Namespace</option>
        </select>
        <input
          type="text"
          placeholder={`Enter ${bulkDeleteBy}...`}
          value={bulkDeleteValue}
          onChange={(e) => setBulkDeleteValue(e.target.value)}
          className="glass-input rounded-lg px-3 py-2 text-white bg-white/5 border border-white/5 focus:outline-none focus:border-red-500/50 focus:bg-white/10 transition-all text-sm flex-1"
        />
        <button
          onClick={handleBulkDelete}
          className="px-4 py-2 rounded-lg text-sm font-medium text-white bg-red-500/20 border border-red-500/30 hover:bg-red-500/30 hover:border-red-500/50 transition-all flex items-center gap-2"
        >
          <Trash2 className="w-4 h-4" />
          Delete
        </button>
      </div>

      {/* Results List */}
      <div className="flex-1 overflow-y-auto space-y-3 custom-scrollbar -mr-4 pr-4 pb-4">
        {activeTab === 'profile' ? (
          renderProfileTab()
        ) : activeTab === 'facts' ? (
          <>
            {facts.length === 0 ? (
              <div className="h-full flex flex-col items-center justify-center text-slate-600 space-y-4">
                <div className="w-16 h-16 rounded-full bg-white/5 flex items-center justify-center">
                  <Filter className="w-8 h-8 opacity-20" />
                </div>
                <span className="text-sm">
                  {loading ? 'Loading facts...' : 'No facts found.'}
                </span>
              </div>
            ) : (
              facts.map((fact, index) => {
                return (
                <div
                  key={fact.id || index}
                  className="glass-card p-5 rounded-2xl hover:bg-white/[0.03] transition-all group border border-white/5 hover:border-amber-500/30 animate-fade-in-up relative"
                  style={{ animationDelay: `${index * 0.05}s` }}
                >
                  <div className="flex items-start justify-between mb-3">
                    <div className="flex items-center gap-2">
                      <div className="text-[10px] font-bold uppercase tracking-widest px-2.5 py-1 rounded-md border bg-amber-500/10 text-amber-500 border-amber-500/20 flex items-center gap-2">
                        <Hash className="w-3 h-3" />
                        Fact
                      </div>
                      {fact.category && (
                        <div className={`text-[10px] font-bold uppercase tracking-widest px-2.5 py-1 rounded-md border flex items-center gap-2 ${
                          fact.category === 'profile' 
                            ? 'bg-purple-500/10 text-purple-400 border-purple-500/30'
                            : 'bg-slate-500/10 text-slate-400 border-slate-500/30'
                        }`}>
                          {fact.category}
                        </div>
                      )}
                    </div>
                  </div>

                  <div className="space-y-2 mb-4">
                    <div className="text-slate-300 text-sm">
                      <span className="text-slate-500 text-xs">Subject:</span>{' '}
                      <span className="font-medium">{fact.subject}</span>
                    </div>
                    <div className="text-slate-300 text-sm">
                      <span className="text-slate-500 text-xs">Predicate:</span>{' '}
                      <span className="font-medium">{fact.predicate}</span>
                    </div>
                    <div className="text-slate-200 text-sm leading-relaxed font-medium pl-1 border-l-2 border-amber-500/40 group-hover:border-amber-500 transition-colors py-1">
                      <span className="text-slate-500 text-xs">Object:</span>{' '}
                      {fact.object}
                    </div>
                  </div>

                  <div className="flex items-center justify-between text-[10px] text-slate-500 font-mono border-t border-white/5 pt-3 mt-2">
                    <span className="flex items-center gap-2">
                      <span className="w-1.5 h-1.5 rounded-full bg-slate-700 group-hover:bg-amber-500 transition-colors" />
                      {fact.source_session && (
                        <>
                          Session: <span className="text-slate-400">{fact.source_session}</span>
                        </>
                      )}
                    </span>
                    <span className="opacity-70">
                      {new Date(fact.timestamp * 1000).toLocaleDateString()} •{' '}
                      {new Date(fact.timestamp * 1000).toLocaleTimeString()}
                    </span>
                  </div>
                </div>
                );
              })
            )}
          </>
        ) : filteredMemories.length === 0 ? (
          <div className="h-full flex flex-col items-center justify-center text-slate-600 space-y-4">
            <div className="w-16 h-16 rounded-full bg-white/5 flex items-center justify-center">
              <Filter className="w-8 h-8 opacity-20" />
            </div>
            <span className="text-sm">
              {loading ? 'Scanning vector index...' : 'No matching memory vectors found.'}
            </span>
          </div>
        ) : (
          filteredMemories.map((memory, index) => {
            const { meta, clean } = splitMeta(memory.content || "");
            
            return (
            <div
              key={memory.id}
              className="glass-card p-5 rounded-2xl hover:bg-white/[0.03] transition-all group border border-white/5 hover:border-air-500/30 animate-fade-in-up relative"
              style={{ animationDelay: `${index * 0.05}s` }}
            >
              <div className="flex items-start justify-between mb-3 pr-8">
                <div className="flex items-center gap-2">
                  {/* Pinned badge */}
                  {(() => {
                    const metaTag = (memory.meta as any)?.tag;
                    const contentHasRagPin = memory.content.includes('[Meta:') && memory.content.includes('Tag: rag_pin');
                    const isPinned = metaTag === 'rag_pin' || contentHasRagPin;
                    if (isPinned) {
                      return (
                        <div className="text-[10px] font-bold uppercase tracking-widest px-2.5 py-1 rounded-md border flex items-center gap-2 bg-emerald-500/10 text-emerald-400 border-emerald-500/30">
                          <Pin className="w-3 h-3" />
                          Pinned
                        </div>
                      );
                    }
                    return null;
                  })()}
                  
                  <div
                    className={`text-[10px] font-bold uppercase tracking-widest px-2.5 py-1 rounded-md border flex items-center gap-2 ${
                      memory.namespace === 'profile'
                        ? 'bg-purple-500/10 text-purple-500 border-purple-500/20'
                        : memory.namespace === 'docs'
                        ? 'bg-emerald-500/10 text-emerald-500 border-emerald-500/20'
                        : memory.namespace === 'facts'
                        ? 'bg-amber-500/10 text-amber-500 border-amber-500/20'
                        : 'bg-blue-500/10 text-blue-500 border-blue-500/20'
                    }`}
                  >
                    <Hash className="w-3 h-3" />
                    {memory.namespace}
                  </div>
                  
                  {meta && (
                    <button
                      onClick={() => toggleMeta(memory.id)}
                      className="px-2 py-0.5 rounded-full text-[9px] font-medium text-slate-400 hover:text-slate-200 border border-white/5 bg-white/5 hover:bg-white/10 transition-colors flex items-center gap-1"
                      title="Toggle metadata"
                    >
                      {metaOpen[memory.id] ? (
                        <>
                          <ChevronDown className="w-2.5 h-2.5 rotate-180" />
                          <span>Meta</span>
                        </>
                      ) : (
                        <>
                          <Info className="w-2.5 h-2.5" />
                          <span>Meta</span>
                        </>
                      )}
                    </button>
                  )}
                </div>

                {memory.relevanceScore !== undefined && (
                  <div className="flex items-center gap-1.5 text-xs font-mono text-slate-400 bg-black/20 px-2 py-1 rounded-full border border-white/5">
                    <Zap
                      className={`w-3 h-3 ${
                        memory.relevanceScore > 0.8
                          ? 'text-amber-400 fill-amber-400'
                          : 'text-slate-600'
                      }`}
                    />
                    <span
                      className={
                        memory.relevanceScore > 0.8
                          ? 'text-amber-200'
                          : 'text-slate-500'
                      }
                    >
                      {(memory.relevanceScore * 100).toFixed(0)}% Match
                    </span>
                  </div>
                )}
              </div>

              <button
                onClick={(e) => handleDelete(memory.id, e)}
                className="absolute top-4 right-4 p-2 text-slate-600 hover:text-red-400 hover:bg-red-500/10 rounded-lg transition-colors opacity-0 group-hover:opacity-100"
                title="Delete Memory"
              >
                <Trash2 className="w-4 h-4" />
              </button>

              <p className="text-slate-200 text-sm leading-relaxed font-medium mb-4 pl-1 border-l-2 border-white/10 group-hover:border-air-500/50 transition-colors py-1">
                {clean}
              </p>
              
              {meta && metaOpen[memory.id] && (() => {
                const metaObj = parseMeta(meta);
                const query = metaObj.Query || metaObj.query;
                const hasLongQuery = query && query.length > 40;
                const showQuery = queryOpen[memory.id];
                
                return (
                  <div className="mt-2 text-xs bg-black/20 border border-white/5 rounded-lg px-3 py-2">
                    <div className="grid gap-y-1 gap-x-3" style={{ gridTemplateColumns: 'auto 1fr' }}>
                      {metaObj.Source && (
                        <>
                          <span className="text-slate-500">Source:</span>
                          <span className={metaObj.Source === 'unknown' ? 'text-slate-500' : 'text-slate-300'}>
                            {metaObj.Source}
                          </span>
                        </>
                      )}
                      {metaObj.Tag && (
                        <>
                          <span className="text-slate-500">Tag:</span>
                          <span className="text-slate-300">{metaObj.Tag}</span>
                        </>
                      )}
                      {metaObj.OriginalTag && (
                        <>
                          <span className="text-slate-500">OriginalTag:</span>
                          <span className="text-slate-300">{metaObj.OriginalTag}</span>
                        </>
                      )}
                      {metaObj.Score && (
                        <>
                          <span className="text-slate-500">Score:</span>
                          <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-md text-[10px] bg-air-500/10 text-air-400 border border-air-500/30">
                            <Zap size={10} /> {metaObj.Score}
                          </span>
                        </>
                      )}
                      {metaObj.PinnedFrom && (
                        <>
                          <span className="text-slate-500">PinnedFrom:</span>
                          <span className="text-slate-300">{metaObj.PinnedFrom}</span>
                        </>
                      )}
                      {metaObj.Session && (
                        <>
                          <span className="text-slate-500">Session:</span>
                          <div className="flex items-center gap-1.5">
                            <span className="text-slate-300">{metaObj.Session}</span>
                            <button
                              onClick={() => handleCopySession(metaObj.Session, memory.id)}
                              className="p-0.5 hover:bg-white/10 rounded text-slate-400 hover:text-slate-200 transition-colors"
                              title={copiedSessionId === memory.id ? 'Copied' : 'Copy session id'}
                            >
                              {copiedSessionId === memory.id ? (
                                <ClipboardCheck size={12} className="text-emerald-400" />
                              ) : (
                                <Copy size={12} />
                              )}
                            </button>
                          </div>
                        </>
                      )}
                    </div>
                    {query && (
                      <div className="mt-2 pt-2 border-t border-white/5">
                        {hasLongQuery ? (
                          <>
                            <button
                              onClick={() => toggleQuery(memory.id)}
                              className="text-slate-400 hover:text-slate-200 text-[10px] font-medium transition-colors"
                            >
                              {showQuery ? 'Hide query' : 'Show query'}
                            </button>
                            {showQuery && (
                              <div className="mt-1 text-slate-300 font-mono break-words text-[10px]">
                                {query}
                              </div>
                            )}
                          </>
                        ) : (
                          <div className="flex items-start gap-2">
                            <span className="text-slate-500">Query:</span>
                            <span className="text-slate-300">{query}</span>
                          </div>
                        )}
                      </div>
                    )}
                  </div>
                );
              })()}

              <div className="flex items-center justify-between text-[10px] text-slate-500 font-mono border-t border-white/5 pt-3 mt-2">
                <span className="flex items-center gap-2">
                  <span className="w-1.5 h-1.5 rounded-full bg-slate-700 group-hover:bg-air-500 transition-colors" />
                  Source:{' '}
                  <span className="text-slate-400">
                    {memory.source || 'System Internal'}
                  </span>
                </span>
                <span className="opacity-70">
                  {new Date(memory.timestamp).toLocaleDateString()} •{' '}
                  {new Date(memory.timestamp).toLocaleTimeString()}
                </span>
              </div>
            </div>
            );
          })
        )}
      </div>
    </div>
  );
};

export default Memory;