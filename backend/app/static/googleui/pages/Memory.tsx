import React, { useState, useEffect } from 'react';
import { air4 } from '../services/air4Service';
import { MemoryItem } from '../types';
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
  ChevronDown,
} from 'lucide-react';

interface ProfileData {
  subject: string;
  food?: string[];
  country?: string[];
  location?: string[];
  vehicle?: string[];
  goals?: string[];
  other?: string[];
}

const Memory: React.FC = () => {
  const [memories, setMemories] = useState<MemoryItem[]>([]);
  const [searchTerm, setSearchTerm] = useState('');
  const [activeTab, setActiveTab] = useState<'all' | 'facts' | 'sessions' | 'docs' | 'profile'>('all');
  const [loading, setLoading] = useState(false);
  const [profile, setProfile] = useState<ProfileData | null>(null);
  const [profileCategoriesOpen, setProfileCategoriesOpen] = useState<Record<string, boolean>>({
    location: true,
    country: true,
    goals: true,
    food: true,
    vehicle: true,
    other: true,
  });

  const doSearch = async (query: string) => {
    setLoading(true);
    try {
      const results = await air4.getMemories(query);
      setMemories(results);
    } finally {
      setLoading(false);
    }
  };

  const handleDelete = async (id: string, e: React.MouseEvent) => {
    e.stopPropagation();
    if (confirm('Are you sure you want to delete this memory vector?\n\nThis action cannot be undone.')) {
      const success = await air4.deleteMemory(id);
      if (success) {
        setMemories((prev) => prev.filter((m) => m.id !== id));
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

  // Load structured profile when switching to Profile tab
  useEffect(() => {
    if (activeTab !== 'profile') return;

    let cancelled = false;
    const loadProfile = async () => {
      setLoading(true);
      try {
        const p = await air4.getFactsProfile('Arch');
        if (!cancelled) {
          setProfile(p);
        }
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
  }, [activeTab]);

  const filteredMemories = memories.filter((m) => {
    if (activeTab === 'all') return true;

    if (activeTab === 'docs') {
      // Документы: либо явный namespace 'docs', либо любые записи с непустым source
      const src = (m as any).source || '';
      return m.namespace === 'docs' || src !== '';
    }

    return m.namespace === activeTab;
  });

  const tabs: { id: 'all' | 'facts' | 'sessions' | 'docs' | 'profile'; label: string }[] = [
    { id: 'all', label: 'All' },
    { id: 'facts', label: 'Facts' },
    { id: 'profile', label: 'Profile' },
    { id: 'sessions', label: 'Sessions' },
    { id: 'docs', label: 'Docs' },
  ];

  const hasProfileData = (p: ProfileData | null): boolean => {
    if (!p) return false;
    return Boolean(
      (p.location && p.location.length) ||
        (p.country && p.country.length) ||
        (p.food && p.food.length) ||
        (p.vehicle && p.vehicle.length) ||
        (p.goals && p.goals.length) ||
        (p.other && p.other.length)
    );
  };

  // Фильтрация мусорных фактов
  const filterValidFact = (fact: string): boolean => {
    const trimmed = fact.trim();
    if (!trimmed) return false;
    
    // Игнорируем факты < 3 символов
    if (trimmed.length < 3) return false;
    
    // Игнорируем одно слово
    const words = trimmed.split(/\s+/);
    if (words.length === 1) return false;
    
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
      
      // Для категории OTHER: скрываем если < 2 фактов
      if (categoryKey === 'other' && validItems.length < 2) return null;
      
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

    // Сортировка категорий: location, preferences (country), goals, food, other
    const categoryOrder = ['location', 'country', 'goals', 'food', 'vehicle', 'other'];
    const categoryMap: Record<string, React.ReactNode> = {
      location: section('location', 'Location', p.location, 'bg-sky-500/10 text-sky-300 border-sky-500/30', MapPin),
      country: section('country', 'Countries', p.country, 'bg-emerald-500/10 text-emerald-300 border-emerald-500/30', Globe),
      goals: section('goals', 'Goals', p.goals, 'bg-purple-500/15 text-purple-200 border-purple-500/40', Target),
      food: section('food', 'Food', p.food, 'bg-amber-500/10 text-amber-200 border-amber-500/30', Utensils),
      vehicle: section('vehicle', 'Vehicles', p.vehicle, 'bg-cyan-500/10 text-cyan-200 border-cyan-500/30', Layers),
      other: section('other', 'Other', p.other, 'bg-slate-500/10 text-slate-200 border-slate-500/30', Hash),
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
        <div className="flex flex-wrap gap-2">
          {tabs.map((tab) => (
            <button
              key={tab.id}
              onClick={() => setActiveTab(tab.id)}
              className={`px-4 py-1.5 rounded-full text-[10px] font-bold uppercase tracking-wider transition-all duration-300 border ${
                activeTab === tab.id
                  ? 'bg-air-500 text-white border-air-500 shadow-[0_0_15px_rgba(249,115,22,0.3)] scale-105'
                  : 'bg-white/5 text-slate-500 border-white/5 hover:bg-white/10 hover:text-slate-300 hover:border-white/10'
              }`}
            >
              {tab.label}
            </button>
          ))}
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

      {/* Results List */}
      <div className="flex-1 overflow-y-auto space-y-3 custom-scrollbar -mr-4 pr-4 pb-4">
        {activeTab === 'profile' ? (
          renderProfileTab()
        ) : activeTab === 'facts' ? (
          <>
            {filteredMemories.length === 0 ? (
              <div className="h-full flex flex-col items-center justify-center text-slate-600 space-y-4">
                <div className="w-16 h-16 rounded-full bg-white/5 flex items-center justify-center">
                  <Filter className="w-8 h-8 opacity-20" />
                </div>
                <span className="text-sm">
                  {loading ? 'Scanning vector index...' : 'No stored facts.'}
                </span>
              </div>
            ) : (
              filteredMemories.map((memory, index) => (
                <div
                  key={memory.id}
                  className="glass-card p-5 rounded-2xl hover:bg-white/[0.03] transition-all group border border-white/5 hover:border-amber-500/30 animate-fade-in-up relative"
                  style={{ animationDelay: `${index * 0.05}s` }}
                >
                  <div className="flex items-start justify-between mb-3 pr-8">
                    <div className="text-[10px] font-bold uppercase tracking-widest px-2.5 py-1 rounded-md border bg-amber-500/10 text-amber-500 border-amber-500/20 flex items-center gap-2">
                      <Hash className="w-3 h-3" />
                      Facts
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

                  <p className="text-slate-200 text-sm leading-relaxed font-medium mb-4 pl-1 border-l-2 border-amber-500/40 group-hover:border-amber-500 transition-colors py-1">
                    {memory.content}
                  </p>

                  <div className="flex items-center justify-between text-[10px] text-slate-500 font-mono border-t border-white/5 pt-3 mt-2">
                    <span className="flex items-center gap-2">
                      <span className="w-1.5 h-1.5 rounded-full bg-slate-700 group-hover:bg-amber-500 transition-colors" />
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
              ))
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
          filteredMemories.map((memory, index) => (
            <div
              key={memory.id}
              className="glass-card p-5 rounded-2xl hover:bg-white/[0.03] transition-all group border border-white/5 hover:border-air-500/30 animate-fade-in-up relative"
              style={{ animationDelay: `${index * 0.05}s` }}
            >
              <div className="flex items-start justify-between mb-3 pr-8">
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
                {memory.content}
              </p>

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
          ))
        )}
      </div>
    </div>
  );
};

export default Memory;