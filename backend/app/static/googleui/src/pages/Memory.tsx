import React, { useState, useEffect } from 'react';
import { air4 } from '../services/air4Service';
import { MemoryItem } from '../types';
import { Search, RefreshCw, Zap } from 'lucide-react';

const Memory: React.FC = () => {
  const [memories, setMemories] = useState<MemoryItem[]>([]);
  const [searchTerm, setSearchTerm] = useState('');
  const [activeTab, setActiveTab] = useState<'all' | 'facts' | 'sessions' | 'docs' | 'profile'>('all');
  const [loading, setLoading] = useState(false);

  const doSearch = async (query: string) => {
      setLoading(true);
      const results = await air4.getMemories(query);
      setMemories(results);
      setLoading(false);
  };

  useEffect(() => {
    doSearch('');
  }, []);

  useEffect(() => {
      const timer = setTimeout(() => {
          doSearch(searchTerm);
      }, 600);
      return () => clearTimeout(timer);
  }, [searchTerm]);

  const filteredMemories = memories.filter(m => activeTab === 'all' || m.namespace === activeTab);
  const tabs = [
      { id: 'all', label: 'All' },
      { id: 'facts', label: 'Facts' },
      { id: 'sessions', label: 'Chat Logs' },
      { id: 'docs', label: 'Documents' },
  ];

  return (
    <div className="h-full flex flex-col p-8">
      <div className="flex justify-between items-end mb-8">
          <div>
            <h2 className="text-2xl font-bold text-white mb-2">Memory Bank</h2>
            <p className="text-slate-400 text-sm">Semantic vector retrieval system.</p>
          </div>
          <div className="flex gap-2 bg-white/5 p-1 rounded-xl">
              {tabs.map(tab => (
                  <button
                    key={tab.id}
                    onClick={() => setActiveTab(tab.id as any)}
                    className={`px-3 py-1.5 rounded-lg text-xs font-medium transition-all ${
                        activeTab === tab.id ? 'bg-white/10 text-white shadow-sm' : 'text-slate-500 hover:text-slate-300'
                    }`}
                  >
                      {tab.label}
                  </button>
              ))}
          </div>
      </div>

      <div className="relative mb-6">
        <Search className="absolute left-4 top-3.5 text-slate-500 w-5 h-5" />
        <input
          type="text"
          placeholder="Search vectors..."
          value={searchTerm}
          onChange={(e) => setSearchTerm(e.target.value)}
          className="w-full glass-input rounded-xl pl-12 pr-4 py-3 text-white focus:outline-none focus:border-air-500/50 transition-colors text-sm"
        />
        {loading && <RefreshCw className="absolute right-4 top-3.5 text-air-500 w-5 h-5 animate-spin" />}
      </div>

      <div className="flex-1 overflow-y-auto space-y-3 custom-scrollbar">
        {filteredMemories.length === 0 ? (
            <div className="text-center text-slate-600 py-20 text-sm">
                {loading ? 'Scanning...' : 'No memories found.'}
            </div>
        ) : (
            filteredMemories.map((memory) => (
            <div key={memory.id} className="glass-card p-4 rounded-xl hover:bg-white/5 transition-colors group">
                <div className="flex items-start justify-between mb-2">
                    <span className="text-[10px] uppercase tracking-wider font-bold text-air-500 bg-air-500/10 px-2 py-0.5 rounded">
                        {memory.namespace}
                    </span>
                    {memory.relevanceScore !== undefined && (
                        <span className="flex items-center gap-1 text-[10px] text-slate-500">
                           <Zap className="w-3 h-3 text-amber-500" /> {(memory.relevanceScore * 100).toFixed(0)}% Match
                        </span>
                    )}
                </div>
                <p className="text-slate-300 text-sm leading-relaxed">{memory.content}</p>
                <div className="mt-2 text-[10px] text-slate-600">
                    Source: {memory.source || 'System'} • {new Date(memory.timestamp).toLocaleDateString()}
                </div>
            </div>
            ))
        )}
      </div>
    </div>
  );
};

export default Memory;