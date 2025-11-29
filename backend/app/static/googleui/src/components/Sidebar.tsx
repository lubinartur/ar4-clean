
import React, { useState, useEffect } from 'react';
import { 
  LayoutDashboard, 
  MessageSquare, 
  Database, 
  Settings, 
  AlertTriangle,
  Lock,
  UploadCloud,
  PlusCircle,
  Zap,
  Trash2,
  Clock,
  History
} from 'lucide-react';
import { air4 } from '../services/air4Service';
import { ChatSession } from '../types';
import { Logo } from './Logo';

interface SidebarProps {
  activeTab: string;
  onTabChange: (tab: string) => void;
  currentSessionId: string | null;
  onSessionChange: (sessionId: string) => void;
}

const Sidebar: React.FC<SidebarProps> = ({ activeTab, onTabChange, currentSessionId, onSessionChange }) => {
  const [panicActive, setPanicActive] = useState(false);
  const [history, setHistory] = useState<ChatSession[]>([]);

  const refreshHistory = () => {
      setHistory(air4.getSessions());
  };

  useEffect(() => {
    refreshHistory();
    // Poll for title updates or new chats
    const interval = setInterval(refreshHistory, 2000);
    return () => clearInterval(interval);
  }, []);

  const handlePanic = () => {
    if (window.confirm("ENGAGE DURESS PROTOCOL?")) {
        air4.triggerPanic();
        setPanicActive(true);
    }
  };

  const handleNewChat = () => {
      const newSession = air4.createSession();
      refreshHistory();
      onSessionChange(newSession.id);
      onTabChange('chat');
  };

  const handleDeleteSession = (e: React.MouseEvent, id: string) => {
      e.stopPropagation();
      if (confirm('Delete this memory thread?')) {
          air4.deleteSession(id);
          refreshHistory();
          if (currentSessionId === id) {
              // If deleted active session, go to dashboard or first available
              const remaining = air4.getSessions();
              if (remaining.length > 0) onSessionChange(remaining[0].id);
              else onTabChange('dashboard');
          }
      }
  };

  if (panicActive) {
      return (
          <div className="h-full w-20 md:w-64 bg-red-950/20 glass-panel rounded-[2rem] flex flex-col items-center justify-center animate-pulse border-red-500/50 border">
              <Lock className="w-12 h-12 text-red-500 mb-4" />
              <h2 className="text-red-500 font-bold tracking-widest">LOCKED</h2>
          </div>
      )
  }

  // Group history by date
  const safeHistory = Array.isArray(history) ? history : [];
  const groupedHistory = safeHistory.reduce((groups, session) => {
      const date = new Date(session.timestamp);
      const today = new Date();
      let key = 'Previous';
      
      if (date.toDateString() === today.toDateString()) key = 'Today';
      else if (date.getDate() === today.getDate() - 1 && date.getMonth() === today.getMonth() && date.getFullYear() === today.getFullYear()) key = 'Yesterday';
      else if (date > new Date(Date.now() - 7 * 24 * 60 * 60 * 1000)) key = 'Previous 7 Days';

      if (!groups[key]) groups[key] = [];
      groups[key].push(session);
      return groups;
  }, {} as Record<string, ChatSession[]>);

  const groupOrder = ['Today', 'Yesterday', 'Previous 7 Days', 'Previous'];

  return (
    <div className="h-full w-20 md:w-[280px] flex flex-col z-50">
      
      {/* Header Area */}
      <div className="flex-shrink-0 px-6 py-5 flex items-center gap-3 mb-2">
             <div className="w-8 h-8 rounded-lg bg-air-500/10 flex items-center justify-center border border-air-500/20 text-air-500 shadow-[0_0_15px_rgba(249,115,22,0.15)] relative overflow-hidden group">
                 <div className="absolute inset-0 bg-air-500/10 blur-md opacity-0 group-hover:opacity-100 transition-opacity"></div>
                 <Logo className="w-5 h-5 text-air-500 relative z-10" />
             </div>
             <div className="hidden md:block">
                 <h1 className="font-bold text-lg text-slate-100 tracking-tight">AIr4 Core</h1>
             </div>
      </div>

      {/* New Chat Button */}
      <div className="flex-shrink-0 px-4 mb-6">
            <button 
                onClick={handleNewChat}
                className="w-full flex items-center gap-3 bg-white/5 hover:bg-air-600 hover:text-white border border-white/10 hover:border-air-500/50 text-slate-300 p-3 rounded-2xl transition-all duration-300 group shadow-lg shadow-transparent hover:shadow-[0_0_15px_rgba(249,115,22,0.3)] hover:scale-[1.02]"
            >
                <PlusCircle className="w-5 h-5 text-air-500 group-hover:text-white group-hover:rotate-90 transition-all" />
                <span className="hidden md:block font-medium">New Session</span>
            </button>
      </div>

      {/* Main Navigation + History Scroll Area */}
      <div className="flex-1 overflow-y-auto px-4 space-y-8 custom-scrollbar pb-4">
            
            {/* Core Workspaces */}
            <div>
                <h3 className="text-[10px] font-bold text-slate-500 mb-3 px-2 hidden md:block tracking-widest uppercase">Workspaces</h3>
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
                        icon={History} 
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

            {/* Chat History Section */}
            <div className="hidden md:block">
                <h3 className="text-[10px] font-bold text-slate-500 mb-3 px-2 tracking-widest uppercase flex items-center justify-between">
                    <span>Recent Chats</span>
                    <Clock className="w-3 h-3" />
                </h3>
                
                <div className="space-y-4">
                    {groupOrder.map(group => {
                        if (!groupedHistory[group]) return null;
                        return (
                            <div key={group}>
                                <div className="px-2 text-[10px] text-slate-600 font-semibold mb-2">{group}</div>
                                <div className="space-y-1">
                                    {groupedHistory[group].map(session => (
                                        <div 
                                            key={session.id}
                                            onClick={() => { onSessionChange(session.id); onTabChange('chat'); }}
                                            className={`group relative flex items-center gap-3 px-3 py-2 rounded-xl cursor-pointer transition-all ${
                                                currentSessionId === session.id && activeTab === 'chat'
                                                ? 'bg-white/10 text-white border border-white/5' 
                                                : 'text-slate-400 hover:text-slate-200 hover:bg-white/5 border border-transparent'
                                            }`}
                                        >
                                            <MessageSquare className={`w-3 h-3 flex-shrink-0 ${currentSessionId === session.id && activeTab === 'chat' ? 'text-air-500' : 'text-slate-600'}`} />
                                            <span className="truncate text-xs font-medium flex-1">
                                                {session.title || 'Untitled Session'}
                                            </span>
                                            
                                            {/* Delete Action (visible on hover) */}
                                            <button 
                                                onClick={(e) => handleDeleteSession(e, session.id)}
                                                className="opacity-0 group-hover:opacity-100 p-1 hover:text-red-400 transition-opacity"
                                            >
                                                <Trash2 className="w-3 h-3" />
                                            </button>
                                        </div>
                                    ))}
                                </div>
                            </div>
                        )
                    })}
                    
                    {history.length === 0 && (
                        <div className="px-3 py-4 text-center border border-dashed border-white/5 rounded-xl">
                            <span className="text-xs text-slate-600">No active sessions</span>
                        </div>
                    )}
                </div>
            </div>
      </div>

      {/* Footer / Status Card */}
      <div className="flex-shrink-0 p-4">
        <div className="glass-card rounded-2xl p-4 relative overflow-hidden group border border-white/5">
            <div className="absolute top-0 right-0 w-20 h-20 bg-air-500/20 blur-2xl -translate-y-1/2 translate-x-1/2 rounded-full"></div>
            
            <div className="relative z-10 text-center md:text-left">
                <div className="mx-auto md:mx-0 w-8 h-8 rounded-full bg-air-500/20 flex items-center justify-center mb-2">
                    <Zap className="w-4 h-4 text-air-500" />
                </div>
                <h4 className="hidden md:block text-sm font-bold text-white mb-1">System Online</h4>
                <p className="hidden md:block text-[10px] text-slate-400 leading-tight mb-3">
                    Local core active. <br/>AES-256 Enabled.
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

const NavItem = ({ id, icon: Icon, label, active, onClick }: any) => (
    <button
        onClick={onClick}
        className={`w-full flex items-center gap-3 px-3 py-2.5 rounded-xl transition-all duration-200 group ${
            active 
            ? 'bg-air-500/10 text-air-500 border border-air-500/20 shadow-[0_0_20px_rgba(249,115,22,0.1)]' 
            : 'text-slate-400 hover:text-slate-200 hover:bg-white/5 border border-transparent'
        }`}
    >
        <Icon className={`w-4 h-4 transition-colors ${active ? 'text-air-500' : 'group-hover:text-air-400'}`} />
        <span className="hidden md:block font-medium text-sm">{label}</span>
    </button>
);

export default Sidebar;
