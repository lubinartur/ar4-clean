
import React, { useState, useEffect } from 'react';
import { air4 } from '../services/air4Service';
import { ChatSession } from '../types';
import { MessageSquare, Trash2, Calendar, Search, Edit2, Check, X, List } from 'lucide-react';

interface HistoryProps {
  onSelectSession: (id: string) => void;
}

const History: React.FC<HistoryProps> = ({ onSelectSession }) => {
  const [sessions, setSessions] = useState<ChatSession[]>([]);
  const [searchTerm, setSearchTerm] = useState('');
  const [editingId, setEditingId] = useState<string | null>(null);
  const [editTitle, setEditTitle] = useState('');

  const refreshSessions = () => {
    setSessions(air4.getSessions());
  };

  useEffect(() => {
    refreshSessions();
    const interval = setInterval(refreshSessions, 3000);
    return () => clearInterval(interval);
  }, []);

  const handleDelete = (e: React.MouseEvent, id: string) => {
    e.stopPropagation();
    if (confirm('Are you sure you want to permanently delete this chat log?')) {
      air4.deleteSession(id);
      refreshSessions();
    }
  };

  const handleRenameStart = (e: React.MouseEvent, session: ChatSession) => {
    e.stopPropagation();
    setEditingId(session.id);
    setEditTitle(session.title);
  };

  const handleRenameSave = (e: React.MouseEvent) => {
    e.stopPropagation();
    if (editingId && editTitle.trim()) {
      air4.renameSession(editingId, editTitle.trim());
      setEditingId(null);
      refreshSessions();
    }
  };

  const handleRenameCancel = (e: React.MouseEvent) => {
    e.stopPropagation();
    setEditingId(null);
  };

  const filteredSessions = sessions.filter(s => 
    s.title.toLowerCase().includes(searchTerm.toLowerCase()) || 
    s.lastMessage.toLowerCase().includes(searchTerm.toLowerCase())
  );

  return (
    <div className="h-full flex flex-col p-8">
      <div className="mb-8">
        <h2 className="text-2xl font-bold text-white mb-2">Session History</h2>
        <p className="text-slate-400 text-sm">Full archive of your local interactions.</p>
      </div>

      <div className="relative mb-6">
        <Search className="absolute left-4 top-3.5 text-slate-500 w-5 h-5" />
        <input
          type="text"
          placeholder="Search conversation logs..."
          value={searchTerm}
          onChange={(e) => setSearchTerm(e.target.value)}
          className="w-full glass-input rounded-xl pl-12 pr-4 py-3 text-white focus:outline-none focus:border-air-500/50 transition-colors text-sm"
        />
      </div>

      <div className="flex-1 overflow-y-auto space-y-4 custom-scrollbar">
        {filteredSessions.length === 0 ? (
          <div className="text-center py-20 text-slate-600">
            {searchTerm ? 'No matches found.' : 'No history available.'}
          </div>
        ) : (
          filteredSessions.map((session) => (
            <div 
              key={session.id}
              onClick={() => { if (editingId !== session.id) onSelectSession(session.id); }}
              className="glass-card p-5 rounded-xl hover:bg-white/5 transition-all cursor-pointer group border border-white/5 relative"
            >
              <div className="flex items-start justify-between mb-2">
                <div className="flex items-center gap-2 flex-1 mr-4">
                   <div className="p-2 rounded-lg bg-air-500/10 text-air-500 flex-shrink-0">
                      <MessageSquare className="w-4 h-4" />
                   </div>
                   
                   {editingId === session.id ? (
                      <div className="flex items-center gap-2 flex-1" onClick={(e) => e.stopPropagation()}>
                          <input 
                              type="text" 
                              value={editTitle} 
                              onChange={(e) => setEditTitle(e.target.value)}
                              className="flex-1 bg-black/40 border border-air-500/50 rounded px-2 py-1 text-sm text-white focus:outline-none"
                              autoFocus
                              onKeyDown={(e) => {
                                  if (e.key === 'Enter') handleRenameSave(e as any);
                                  if (e.key === 'Escape') handleRenameCancel(e as any);
                              }}
                          />
                          <button onClick={handleRenameSave} className="p-1 hover:text-emerald-400 text-slate-400"><Check className="w-4 h-4"/></button>
                          <button onClick={handleRenameCancel} className="p-1 hover:text-red-400 text-slate-400"><X className="w-4 h-4"/></button>
                      </div>
                   ) : (
                      <h3 className="font-bold text-slate-200 group-hover:text-air-400 transition-colors truncate">
                        {session.title || 'Untitled Session'}
                      </h3>
                   )}
                </div>

                <div className="flex items-center gap-2">
                    {/* Message Count Badge */}
                    <span className="text-[10px] text-slate-500 flex items-center gap-1 bg-white/5 px-2 py-1 rounded" title={`${session.messages.length} messages`}>
                       <List className="w-3 h-3" />
                       {session.messages.length}
                    </span>

                    <span className="text-[10px] text-slate-500 flex items-center gap-1 bg-white/5 px-2 py-1 rounded">
                       <Calendar className="w-3 h-3" />
                       {new Date(session.timestamp).toLocaleDateString()}
                    </span>
                    
                    {editingId !== session.id && (
                        <div className="flex items-center gap-1 opacity-0 group-hover:opacity-100 transition-opacity">
                            <button 
                                onClick={(e) => handleRenameStart(e, session)}
                                className="p-2 hover:bg-white/10 hover:text-air-400 text-slate-600 rounded-lg transition-colors"
                                title="Rename"
                            >
                                <Edit2 className="w-4 h-4" />
                            </button>
                            <button 
                                onClick={(e) => handleDelete(e, session.id)}
                                className="p-2 hover:bg-red-500/20 hover:text-red-400 text-slate-600 rounded-lg transition-colors"
                                title="Delete Log"
                            >
                                <Trash2 className="w-4 h-4" />
                            </button>
                        </div>
                    )}
                </div>
              </div>
              <p className="text-slate-400 text-xs line-clamp-2 pl-11">
                  {session.lastMessage || 'No content...'}
              </p>
            </div>
          ))
        )}
      </div>
    </div>
  );
};

export default History;
