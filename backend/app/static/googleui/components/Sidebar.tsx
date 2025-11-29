import React, { useState, useEffect } from 'react';
import {
  LayoutDashboard,
  MessageSquare,
  Database,
  Settings,
  UploadCloud,
  PlusCircle,
  Clock,
  History as HistoryIcon,
  Lock,
  Trash2,
  AlertTriangle,
  Zap,
  ChevronDown,
  ChevronRight,
  Archive,
} from 'lucide-react';
import { air4 } from '../services/air4Service';
import { ChatSession } from '../types';
import Logo from '../assets/air4.svg';

interface SidebarProps {
  activeTab: string;
  onTabChange: (tab: string) => void;
  currentSessionId: string | null;
  onSessionChange: (sessionId: string | null) => void;
}

const Sidebar: React.FC<SidebarProps> = ({
  activeTab,
  onTabChange,
  currentSessionId,
  onSessionChange,
}) => {
  const [panicActive, setPanicActive] = useState(false);
  const [history, setHistory] = useState<ChatSession[]>([]);
  // Manage collapsed state for groups. Default main groups to open.
  const [openGroups, setOpenGroups] = useState<Record<string, boolean>>({
    Today: true,
    Yesterday: true,
    'Previous 7 Days': true,
    'Previous 30 Days': true,
  });

  const refreshHistory = () => {
    try {
      const sessions = air4.getSessions();
      setHistory(Array.isArray(sessions) ? sessions : []);
    } catch (err) {
      console.error('[Sidebar] refreshHistory error', err);
      setHistory([]);
    }
  };

  useEffect(() => {
    refreshHistory();
    // Poll for title updates or new chats
    const interval = setInterval(refreshHistory, 2000);
    return () => clearInterval(interval);
  }, []);

  const handlePanic = () => {
    if (window.confirm('ENGAGE DURESS PROTOCOL?')) {
      air4.triggerPanic();
      setPanicActive(true);
    }
  };

  const handleNewChat = () => {
    console.log('[Sidebar] New Session click');
    try {
      // Keep explicit title like в старой версии
      const newSession = air4.createSession('New Session');
      console.log('[Sidebar] created session', newSession);
      refreshHistory();
      onSessionChange(newSession.id);
      onTabChange('chat');
    } catch (err) {
      console.error('[Sidebar] handleNewChat error', err);
    }
  };

  const handleDeleteSession = (
    e: React.MouseEvent,
    id: string,
  ) => {
    e.stopPropagation();
    if (!window.confirm('Delete this memory thread?')) return;

    try {
      air4.deleteSession(id);
      refreshHistory();
      if (currentSessionId === id) {
        const remaining = air4.getSessions();
        if (remaining.length > 0) {
          onSessionChange(remaining[0].id);
        } else {
          onSessionChange(null);
          onTabChange('dashboard');
        }
      }
    } catch (err) {
      console.error('[Sidebar] deleteSession error', err);
    }
  };

  const toggleGroup = (group: string) => {
    setOpenGroups(prev => ({
      ...prev,
      [group]: !prev[group],
    }));
  };

  if (panicActive) {
    return (
      <div className="h-full w-20 md:w-64 bg-red-950/20 glass-panel rounded-[2rem] flex flex-col items-center justify-center animate-pulse border border-red-500/50">
        <Lock className="w-12 h-12 text-red-500 mb-4" />
        <h2 className="text-red-500 font-bold tracking-widest">LOCKED</h2>
      </div>
    );
  }

  // Advanced Grouping Logic for Recent Chats
  const groupedHistory = history.reduce(
    (groups, session) => {
      const date = new Date((session as any).timestamp ?? (session as any).created_at ?? Date.now());
      const now = new Date();
      const diffTime = Math.abs(now.getTime() - date.getTime());
      const diffDays = Math.ceil(diffTime / (1000 * 60 * 60 * 24));

      let key = 'Older'; // Default

      if (date.toDateString() === now.toDateString()) {
        key = 'Today';
      } else if (diffDays <= 1) {
        key = 'Yesterday';
      } else if (diffDays <= 7) {
        key = 'Previous 7 Days';
      } else if (diffDays <= 30) {
        key = 'Previous 30 Days';
      } else {
        // Group by Month Year for older items, e.g., "September 2024"
        key = date.toLocaleDateString('en-US', {
          month: 'long',
          year: 'numeric',
        });
      }

      if (!groups[key]) groups[key] = [];
      groups[key].push(session);
      return groups;
    },
    {} as Record<string, ChatSession[]>,
  );

  // Define sort order for known keys, allow dynamic keys (Months) to follow
  const fixedOrder = ['Today', 'Yesterday', 'Previous 7 Days', 'Previous 30 Days'];
  const allKeys = Object.keys(groupedHistory);
  const dynamicKeys = allKeys
    .filter(k => !fixedOrder.includes(k))
    .sort((a, b) => new Date(b).getTime() - new Date(a).getTime()); // newest months first

  const finalGroupOrder = [...fixedOrder, ...dynamicKeys];

  return (
    <div className="h-full w-20 md:w-[280px] flex flex-col z-50">
      {/* Header */}
      <div className="flex-shrink-0 px-6 py-5 flex items-center gap-3 mb-2">
        <div className="w-8 h-8 rounded-lg bg-air-500/10 flex items-center justify-center border border-air-500/20 text-air-500 shadow-[0_0_15px_rgba(249,115,22,0.15)] relative overflow-hidden group">
          <div className="absolute inset-0 bg-air-500/10 blur-md opacity-0 group-hover:opacity-100 transition-opacity" />
          <img
            src={Logo}
            alt="AiR4 logo"
            className="w-5 h-5 object-contain relative z-10"
          />
        </div>
        <div className="hidden md:block">
          <h1 className="font-bold text-lg text-slate-100 tracking-tight">
            AiR4 Core
          </h1>
        </div>
      </div>

      {/* New Session */}
      <div className="flex-shrink-0 px-4 mb-6">
        <button
          onClick={handleNewChat}
          className="w-full flex items-center gap-3 bg-white/5 hover:bg-air-600 hover:text-white border border-white/10 hover:border-air-500/50 text-slate-300 p-3 rounded-2xl transition-all duration-300 group shadow-lg shadow-transparent hover:shadow-[0_0_15px_rgba(249,115,22,0.3)] hover:scale-[1.02]"
        >
          <PlusCircle className="w-5 h-5 text-air-500 group-hover:text-white group-hover:rotate-90 transition-all" />
          <span className="hidden md:block font-medium">New Session</span>
        </button>
      </div>

      {/* Nav + History */}
      <div className="flex-1 overflow-y-auto px-4 space-y-6 custom-scrollbar pb-4">
        {/* Workspaces */}
        <div>
          <h3 className="text-[10px] font-bold text-slate-500 mb-3 px-2 hidden md:block tracking-widest uppercase opacity-70">
            Workspaces
          </h3>
          <div className="space-y-1">
            <NavItem
              id="dashboard"
              icon={LayoutDashboard}
              label="System Overview"
              active={activeTab === 'dashboard'}
              onClick={() => onTabChange('dashboard')}
            />
            <NavItem
              id="memory"
              icon={Database}
              label="Memory Bank"
              active={activeTab === 'memory'}
              onClick={() => onTabChange('memory')}
            />
            <NavItem
              id="ingest"
              icon={UploadCloud}
              label="Ingest Data"
              active={activeTab === 'ingest'}
              onClick={() => onTabChange('ingest')}
            />
            <NavItem
              id="history"
              icon={HistoryIcon}
              label="History"
              active={activeTab === 'history'}
              onClick={() => onTabChange('history')}
            />
            <NavItem
              id="settings"
              icon={Settings}
              label="Settings"
              active={activeTab === 'settings'}
              onClick={() => onTabChange('settings')}
            />
          </div>
        </div>

        {/* Recent Chats */}
        <div className="hidden md:block">
          <div className="flex items-center justify-between mb-3 px-2">
            <h3 className="text-[10px] font-bold text-slate-500 tracking-widest uppercase opacity-70">
              Recent Chats
            </h3>
            <Clock className="w-3 h-3 text-slate-600" />
          </div>

          <div className="space-y-1">
            {finalGroupOrder.map(group => {
              const sessions = groupedHistory[group];
              if (!sessions || sessions.length === 0) return null;

              const isOpen = openGroups[group] ?? true;
              const count = sessions.length;

              return (
                <div key={group} className="mb-2">
                  {/* Group header (collapsible) */}
                  <button
                    onClick={() => toggleGroup(group)}
                    className="w-full flex items-center justify-between px-2 py-1.5 text-[10px] font-bold text-slate-500 hover:text-slate-300 uppercase tracking-wider transition-colors group/header"
                  >
                    <div className="flex items-center gap-1">
                      {isOpen ? (
                        <ChevronDown className="w-3 h-3" />
                      ) : (
                        <ChevronRight className="w-3 h-3" />
                      )}
                      <span>{group}</span>
                    </div>
                    <span className="bg-white/5 px-1.5 rounded-md text-[9px] group-hover/header:bg-white/10">
                      {count}
                    </span>
                  </button>

                  {/* Session list */}
                  <div
                    className={`space-y-0.5 overflow-hidden transition-all duration-300 ${
                      isOpen ? 'max-h-[500px] opacity-100' : 'max-h-0 opacity-0'
                    }`}
                  >
                    {sessions.map(session => {
                      const isActive =
                        currentSessionId === session.id && activeTab === 'chat';
                      return (
                        <div
                          key={session.id}
                          onClick={() => {
                            onSessionChange(session.id);
                            onTabChange('chat');
                          }}
                          className={`group relative flex items-center gap-3 px-3 py-2 rounded-lg cursor-pointer transition-all border-l-2 ${
                            isActive
                              ? 'bg-white/10 text-white border-l-air-500'
                              : 'text-slate-400 hover:text-slate-200 hover:bg-white/5 border-l-transparent'
                          }`}
                        >
                          <span className="truncate text-xs font-medium flex-1">
                            {session.title || 'Untitled Session'}
                          </span>
                          <button
                            onClick={e => handleDeleteSession(e, session.id)}
                            className="opacity-0 group-hover:opacity-100 p-1 hover:text-red-400 transition-opacity"
                            title="Delete"
                          >
                            <Trash2 className="w-3 h-3" />
                          </button>
                        </div>
                      );
                    })}
                  </div>
                </div>
              );
            })}

            {history.length === 0 && (
              <div className="px-3 py-8 text-center border border-dashed border-white/5 rounded-xl flex flex-col items-center gap-2">
                <Archive className="w-5 h-5 text-slate-700" />
                <span className="text-xs text-slate-600">No active sessions</span>
              </div>
            )}
          </div>
        </div>
      </div>

      {/* Footer / Status card with Panic */}
      <div className="flex-shrink-0 p-4 hidden md:block">
        <div className="glass-card rounded-2xl p-4 relative overflow-hidden group border border-white/5">
          <div className="absolute top-0 right-0 w-20 h-20 bg-air-500/20 blur-2xl -translate-y-1/2 translate-x-1/2 rounded-full" />
          <div className="relative z-10 text-center md:text-left">
            <div className="mx-auto md:mx-0 w-8 h-8 rounded-full bg-air-500/20 flex items-center justify-center mb-2">
              <Zap className="w-4 h-4 text-air-500" />
            </div>
            <h4 className="hidden md:block text-sm font-bold text-white mb-1">
              System Online
            </h4>
            <p className="hidden md:block text-[10px] text-slate-400 leading-tight mb-3">
              Local core active.
              <br />
              AES-256 Enabled.
            </p>
            <button
              onClick={handlePanic}
              className="w-full py-2 bg-white/5 hover:bg-red-500/20 hover:text-red-200 border border-white/5 rounded-xl text-xs font-medium transition-colors text-slate-300 flex items-center justify-center gap-2"
            >
              <AlertTriangle className="w-3 h-3" />
              <span className="hidden md:inline">PANIC</span>
            </button>
          </div>
        </div>
      </div>
    </div>
  );
};

interface NavItemProps {
  id: string;
  icon: React.ComponentType<{ className?: string }>;
  label: string;
  active: boolean;
  onClick: () => void;
}

const NavItem: React.FC<NavItemProps> = ({
  icon: Icon,
  label,
  active,
  onClick,
}) => {
  return (
    <button
      onClick={onClick}
      className={`w-full flex items-center gap-3 px-3 py-2.5 rounded-xl transition-all duration-200 group ${
        active
          ? 'bg-air-500/10 text-air-500 border border-air-500/20 shadow-[0_0_20px_rgba(249,115,22,0.1)]'
          : 'text-slate-400 hover:text-slate-200 hover:bg-white/5 border border-transparent'
      }`}
    >
      <Icon
        className={`w-4 h-4 transition-colors ${
          active ? 'text-air-500' : 'group-hover:text-air-400'
        }`}
      />
      <span className="hidden md:block font-medium text-sm">{label}</span>
    </button>
  );
};

export default Sidebar;
