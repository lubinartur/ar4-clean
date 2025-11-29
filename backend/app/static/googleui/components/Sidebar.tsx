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
    id: string
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

  if (panicActive) {
    return (
      <div className="h-full w-20 md:w-64 bg-red-950/20 glass-panel rounded-[2rem] flex flex-col items-center justify-center animate-pulse border border-red-500/50">
        <Lock className="w-12 h-12 text-red-500 mb-4" />
        <h2 className="text-red-500 font-bold tracking-widest">
          LOCKED
        </h2>
      </div>
    );
  }

  // Group history by date
  const groupedHistory = history.reduce(
    (groups, session) => {
      const date = new Date(session.timestamp);
      const today = new Date();
      let key = 'Previous';

      if (date.toDateString() === today.toDateString()) {
        key = 'Today';
      } else {
        const yesterday = new Date();
        yesterday.setDate(today.getDate() - 1);
        if (date.toDateString() === yesterday.toDateString()) {
          key = 'Yesterday';
        } else if (
          date >
          new Date(
            Date.now() - 7 * 24 * 60 * 60 * 1000
          )
        ) {
          key = 'Previous 7 Days';
        }
      }

      if (!groups[key]) groups[key] = [];
      groups[key].push(session);
      return groups;
    },
    {} as Record<string, ChatSession[]>
  );

  const groupOrder = [
    'Today',
    'Yesterday',
    'Previous 7 Days',
    'Previous',
  ];

  return (
    <div className="h-full w-20 md:w-[280px] flex flex-col z-50">
      {/* Header */}
      <div className="flex-shrink-0 px-6 py-5 flex items-center gap-3 mb-2">
        <div className="w-9 h-9 rounded-xl bg-air-500/10 flex items-center justify-center shadow-[0_0_18px_rgba(249,115,22,0.35)] overflow-hidden">
          <img
            src={Logo}
            alt="AiR4 logo"
            className="w-7 h-7 object-contain"
          />
        </div>
        <div className="hidden md:block">
          <h1 className="font-bold text-lg text-slate-100 tracking-tight">
            AiR4
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
          <span className="hidden md:block font-medium">
            New Session
          </span>
        </button>
      </div>

      {/* Nav + History */}
      <div className="flex-1 overflow-y-auto px-4 space-y-8 pb-4">
        {/* Workspaces */}
        <div>
          <h3 className="text-[10px] font-bold text-slate-500 mb-3 px-2 hidden md:block tracking-widest uppercase">
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
              id="chat"
              icon={MessageSquare}
              label="Core Dialog"
              active={activeTab === 'chat'}
              onClick={() => onTabChange('chat')}
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
          <h3 className="text-[10px] font-bold text-slate-500 mb-3 px-2 tracking-widest uppercase flex items-center justify-between">
            <span>Recent Chats</span>
            <Clock className="w-3 h-3" />
          </h3>

          <div className="space-y-4">
            {groupOrder.map((group) => {
              const items = groupedHistory[group];
              if (!items || items.length === 0) return null;
              return (
                <div key={group}>
                  <div className="px-2 text-[10px] text-slate-600 font-semibold mb-2">
                    {group}
                  </div>
                  <div className="space-y-1">
                    {items.map((session) => {
                      const isActive =
                        currentSessionId === session.id &&
                        activeTab === 'chat';
                      return (
                        <div
                          key={session.id}
                          onClick={() => {
                            onSessionChange(session.id);
                            onTabChange('chat');
                          }}
                          className={`group relative flex items-center gap-3 px-3 py-2 rounded-xl cursor-pointer transition-all ${
                            isActive
                              ? 'bg-white/10 text-white border border-white/5'
                              : 'text-slate-400 hover:text-slate-200 hover:bg-white/5 border border-transparent'
                          }`}
                        >
                          <MessageSquare
                            className={`w-3 h-3 flex-shrink-0 ${
                              isActive
                                ? 'text-air-500'
                                : 'text-slate-600'
                            }`}
                          />
                          <span className="truncate text-xs font-medium flex-1">
                            {session.title || 'Untitled Session'}
                          </span>
                          <button
                            onClick={(e) =>
                              handleDeleteSession(e, session.id)
                            }
                            className="opacity-0 group-hover:opacity-100 p-1 hover:text-red-400 transition-opacity"
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
              <div className="px-2 text-[11px] text-slate-600">
                No sessions yet. Use “New Session” to start.
              </div>
            )}
          </div>
        </div>

        {/* Panic button (низ сайдбара можно сделать позже) */}
        <div className="hidden md:block pt-2 border-t border-white/5 mt-4">
          <button
            onClick={handlePanic}
            className="w-full flex items-center gap-2 px-3 py-2 rounded-xl text-xs text-red-400 hover:bg-red-950/30 hover:text-red-300 transition-all"
          >
            <span className="flex items-center justify-center w-4 h-4 rounded-full border border-red-500/60">
              !
            </span>
            <span>Duress Protocol</span>
          </button>
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
      className={`w-full flex items-center gap-3 px-3 py-2 rounded-xl text-sm transition ${
        active
          ? 'bg-air-500/10 text-slate-50 border border-air-500/50'
          : 'text-slate-400 hover:text-slate-100 hover:bg-slate-900/60 border border-transparent'
      }`}
    >
      <Icon className="w-4 h-4" />
      <span className="hidden md:inline">{label}</span>
    </button>
  );
};

export default Sidebar;
