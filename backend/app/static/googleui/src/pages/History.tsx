
import React, { useState, useEffect, useRef, useCallback } from 'react';
import { useAir4 } from '../contexts/Air4Context';
import { ChatSession } from '../types';
import { MessageSquare, Trash2, Calendar, Search, Edit2, Check, X, ArrowRight, Archive, StickyNote } from 'lucide-react';  // P2.3.4: Replaced Hash with StickyNote for note badge

interface RecallSession {
  session_id: string;
  title: string;
  updated_at: number;
  preview: string;
  counts: { chat: number; note: number };
}

interface HistoryProps {
  onSelectSession: (id: string) => void;
  onUserSelectSession?: () => void;
  onOpenSession?: (sid: string) => void;
  onForceOpenSession?: (sessionId: string) => void;
}

const History: React.FC<HistoryProps> = ({ onSelectSession, onUserSelectSession, onOpenSession, onForceOpenSession }) => {
  const air4 = useAir4();
  const [sessions, setSessions] = useState<RecallSession[]>([]);
  const [searchTerm, setSearchTerm] = useState('');
  const [debouncedSearchTerm, setDebouncedSearchTerm] = useState('');
  const [loading, setLoading] = useState(false);
  const [editingId, setEditingId] = useState<string | null>(null);
  const [editTitle, setEditTitle] = useState('');
  const [hasMore, setHasMore] = useState(false);
  const [offset, setOffset] = useState(0);
  const offsetRef = useRef(0);
  const abortControllerRef = useRef<AbortController | null>(null);
  
  // Sync ref with state
  useEffect(() => {
    offsetRef.current = offset;
  }, [offset]);

  // Debounce search term (250ms)
  useEffect(() => {
    const timer = setTimeout(() => {
      setDebouncedSearchTerm(searchTerm);
      setOffset(0); // Reset offset on search change
    }, 250);
    return () => clearTimeout(timer);
  }, [searchTerm]);

  // Load recall sessions
  const loadRecallSessions = useCallback(async (reset: boolean) => {
    // Cancel previous request
    if (abortControllerRef.current) {
      abortControllerRef.current.abort();
    }
    
    const ac = new AbortController();
    abortControllerRef.current = ac;
    
    setLoading(true);
    
    try {
      const currentOffset = reset ? 0 : offsetRef.current;
      const result = await air4.getRecallSessions({
        limit: 50,
        offset: currentOffset,
        q: debouncedSearchTerm || undefined,
      });
      
      if (!ac.signal.aborted) {
        if (reset) {
          setSessions(result.items);
          const newOffset = result.items.length;
          setOffset(newOffset);
          offsetRef.current = newOffset;
        } else {
          setSessions(prev => [...prev, ...result.items]);
          setOffset(prev => {
            const newOffset = prev + result.items.length;
            offsetRef.current = newOffset;
            return newOffset;
          });
        }
        setHasMore(result.has_more);
      }
    } catch (e: any) {
      if (e?.name !== 'AbortError') {
        console.error('[Recall] Failed to load sessions:', e);
      }
    } finally {
      if (!ac.signal.aborted) {
        setLoading(false);
      }
    }
  }, [air4, debouncedSearchTerm]);

  // Load sessions when search term changes or on mount
  useEffect(() => {
    loadRecallSessions(true);
    return () => {
      if (abortControllerRef.current) {
        abortControllerRef.current.abort();
      }
    };
  }, [debouncedSearchTerm]); // Only reload when debounced search changes

  const handleDelete = async (e: React.MouseEvent, id: string) => {
    e.stopPropagation();
    if (confirm('Are you sure you want to permanently delete this chat log?')) {
      air4.deleteSession(id);
      // Refresh from backend
      await loadRecallSessions(true);
    }
  };

  const handleRenameStart = (e: React.MouseEvent, session: RecallSession) => {
    e.stopPropagation();
    setEditingId(session.session_id);
    setEditTitle(session.title);
  };

  const handleRenameSave = async (e: React.MouseEvent) => {
    e.stopPropagation();
    if (editingId && editTitle.trim()) {
      air4.renameSession(editingId, editTitle.trim());
      setEditingId(null);
      // Refresh from backend
      await loadRecallSessions(true);
    }
  };

  const handleRenameCancel = (e: React.MouseEvent) => {
    e.stopPropagation();
    setEditingId(null);
  };

  // Handle opening session (navigates to Chat/Think)
  const handleOpenSession = useCallback((sessionId: string) => {
    if (editingId !== sessionId) {
      onSelectSession(sessionId);
      onForceOpenSession?.(sessionId);
      onUserSelectSession?.();
    }
  }, [editingId, onSelectSession, onForceOpenSession, onUserSelectSession]);

  // Filter out empty sessions (no preview and no counts)
  const nonEmptySessions = sessions.filter(session => {
    const hasPreview = session.preview && session.preview.trim().length > 0;
    const hasCounts = (session.counts.chat + session.counts.note) > 0;
    return hasPreview || hasCounts;
  });

  return (
    <div className="h-full flex flex-col p-8">
      <div className="mb-8">
        <h2 className="text-2xl font-bold text-white mb-2">Recall</h2>
        <p className="text-slate-400 text-sm">Return to past context.</p>
        {/* P2.3.3: Hint about closed sessions */}
        <p className="text-slate-600 text-[11px] mt-2">
          Shows only closed sessions. Create a New Chat to close the current one.
        </p>
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
        {loading && nonEmptySessions.length === 0 ? (
          // P2.3.2: Skeleton loading state for Recall
          <div className="space-y-4">
            {[...Array(4)].map((_, i) => (
              <div key={i} className="glass-card p-5 rounded-xl border border-white/5 animate-pulse">
                <div className="flex items-start justify-between mb-2">
                  <div className="flex items-center gap-2">
                    <div className="w-8 h-8 rounded-lg bg-white/10" />
                    <div className="h-5 w-40 bg-white/10 rounded" />
                  </div>
                  <div className="flex items-center gap-2">
                    <div className="h-5 w-16 bg-white/5 rounded" />
                    <div className="h-5 w-20 bg-white/5 rounded" />
                  </div>
                </div>
                <div className="pl-10 space-y-2">
                  <div className="h-3 bg-white/5 rounded w-full" />
                  <div className="h-3 bg-white/5 rounded w-2/3" />
                </div>
              </div>
            ))}
          </div>
        ) : nonEmptySessions.length === 0 ? (
          // P2.3.2: Empty state for Recall
          <div className="h-full flex flex-col items-center justify-center text-slate-600 space-y-4 py-20">
            <div className="w-16 h-16 rounded-full bg-white/5 flex items-center justify-center">
              <Archive className="w-8 h-8 opacity-20" />
            </div>
            <span className="text-sm font-medium text-slate-500">
              {debouncedSearchTerm ? 'No matches found' : 'No closed sessions yet'}
            </span>
            {!debouncedSearchTerm && (
              <span className="text-xs text-slate-600 max-w-xs text-center">
                Create a new chat to close the current one and it will appear here.
              </span>
            )}
          </div>
        ) : (
          nonEmptySessions.map((session) => (
            <div 
              key={session.session_id}
              onClick={() => handleOpenSession(session.session_id)}
              className="glass-card p-5 rounded-xl hover:bg-white/5 transition-all cursor-pointer group border border-white/5 relative"
            >
              <div className="flex items-start justify-between mb-2">
                <div className="flex items-center gap-2 flex-1 mr-4">
                   <div className="p-2 rounded-lg bg-air-500/10 text-air-500 flex-shrink-0">
                      <MessageSquare className="w-4 h-4" />
                   </div>
                   
                   {editingId === session.session_id ? (
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
                    {/* P2.3.4: Readable chat/note count badges */}
                    {session.counts.chat > 0 && (
                      <span className="text-[10px] text-blue-400 flex items-center gap-1 bg-blue-500/10 px-2 py-1 rounded border border-blue-500/20" title="Chat messages">
                        <MessageSquare className="w-3 h-3" />
                        {session.counts.chat}
                      </span>
                    )}
                    {session.counts.note > 0 && (
                      <span className="text-[10px] text-amber-400 flex items-center gap-1 bg-amber-500/10 px-2 py-1 rounded border border-amber-500/20" title="Notes">
                        <StickyNote className="w-3 h-3" />
                        {session.counts.note}
                      </span>
                    )}

                    <span className="text-[10px] text-slate-500 flex items-center gap-1 bg-white/5 px-2 py-1 rounded">
                       <Calendar className="w-3 h-3" />
                       {new Date(session.updated_at * 1000).toLocaleDateString()}
                    </span>
                    
                    {editingId !== session.session_id && (
                        <div className="flex items-center gap-1 opacity-0 group-hover:opacity-100 transition-opacity">
                            <button
                                onClick={(e) => {
                                    e.stopPropagation();
                                    handleOpenSession(session.session_id);
                                }}
                                className="px-3 py-1.5 rounded-lg text-xs font-medium text-white bg-air-500/20 border border-air-500/30 hover:bg-air-500/30 hover:border-air-500/50 transition-all flex items-center gap-1.5"
                                title="Open session"
                            >
                                <ArrowRight className="w-3 h-3" />
                                Open
                            </button>
                            <button 
                                onClick={(e) => handleRenameStart(e, session)}
                                className="p-2 hover:bg-white/10 hover:text-air-400 text-slate-600 rounded-lg transition-colors"
                                title="Rename"
                            >
                                <Edit2 className="w-4 h-4" />
                            </button>
                            <button 
                                onClick={(e) => handleDelete(e, session.session_id)}
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
                  {session.preview || 'No content...'}
              </p>
            </div>
          ))
        )}
        {hasMore && (
          <div className="flex justify-center pt-4">
            <button
              onClick={() => loadRecallSessions(false)}
              disabled={loading}
              className="px-6 py-3 rounded-lg text-sm font-medium text-white bg-air-500/20 border border-air-500/30 hover:bg-air-500/30 hover:border-air-500/50 transition-all flex items-center gap-2 disabled:opacity-50 disabled:cursor-not-allowed"
            >
              {loading ? 'Loading...' : 'Load More'}
            </button>
          </div>
        )}
      </div>
    </div>
  );
};

export default History;
