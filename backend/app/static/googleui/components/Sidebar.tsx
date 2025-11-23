
import React, { useState } from 'react';
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
  BrainCircuit
} from 'lucide-react';
import { air4 } from '../services/air4Service';

interface SidebarProps {
  activeTab: string;
  onTabChange: (tab: string) => void;
}

const Sidebar: React.FC<SidebarProps> = ({ activeTab, onTabChange }) => {
  const [panicActive, setPanicActive] = useState(false);

  const handlePanic = () => {
    if (window.confirm("ENGAGE DURESS PROTOCOL?")) {
        air4.triggerPanic();
        setPanicActive(true);
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

  return (
    <div className="h-full w-20 md:w-[280px] flex flex-col justify-between z-50">
      
      <div className="flex-1 flex flex-col gap-6">
        {/* Header */}
        <div className="px-6 py-5 flex items-center gap-3 mb-2">
             <div className="w-8 h-8 rounded-lg bg-air-500/10 flex items-center justify-center border border-air-500/20 text-air-500 shadow-[0_0_15px_rgba(249,115,22,0.15)] relative overflow-hidden group">
                 <div className="absolute inset-0 bg-air-500/10 blur-md opacity-0 group-hover:opacity-100 transition-opacity"></div>
                 <img 
                    src="/logo.png" 
                    alt="AIr4" 
                    className="w-5 h-5 object-contain relative z-10"
                    onError={(e) => { e.currentTarget.style.display = 'none'; e.currentTarget.parentElement?.querySelector('.fallback-icon')?.classList.remove('hidden'); }}
                 />
                 <BrainCircuit className="fallback-icon hidden w-5 h-5 relative z-10" />
             </div>
             <div className="hidden md:block">
                 <h1 className="font-bold text-lg text-slate-100 tracking-tight">AIr4 Core</h1>
             </div>
        </div>

        {/* New Chat Button */}
        <div className="px-4">
            <button 
                onClick={() => onTabChange('chat')}
                className="w-full flex items-center gap-3 bg-white/5 hover:bg-white/10 border border-white/5 hover:border-white/10 text-white p-3 rounded-2xl transition-all group"
            >
                <PlusCircle className="w-5 h-5 text-air-500 group-hover:rotate-90 transition-transform" />
                <span className="hidden md:block font-medium">New Session</span>
            </button>
        </div>

        {/* Navigation Groups */}
        <div className="flex-1 overflow-y-auto px-4 space-y-8 custom-scrollbar">
            
            {/* Features Group */}
            <div>
                <h3 className="text-[10px] font-bold text-slate-500 mb-3 px-2 hidden md:block tracking-widest uppercase">Features</h3>
                <div className="space-y-1">
                    <NavItem 
                        id="chat" 
                        icon={MessageSquare} 
                        label="Neural Chat" 
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
                </div>
            </div>

            {/* Workspaces Group */}
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
                        id="ingest" 
                        icon={UploadCloud} 
                        label="Ingest Data" 
                        active={activeTab === 'ingest'} 
                        onClick={() => onTabChange('ingest')} 
                    />
                    <NavItem 
                        id="settings" 
                        icon={Settings} 
                        label="Configuration" 
                        active={activeTab === 'settings'} 
                        onClick={() => onTabChange('settings')} 
                    />
                </div>
            </div>
        </div>
      </div>

      {/* Footer / Status Card */}
      <div className="p-4">
        <div className="glass-card rounded-2xl p-4 relative overflow-hidden group">
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
