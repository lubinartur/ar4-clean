import React, { useEffect, useState } from 'react';
import { air4 } from '../services/air4Service';
import { SystemStats } from '../types';
import { BrainCircuit, UploadCloud, Database, Settings, Sparkles, ArrowRight, Command } from 'lucide-react';

interface DashboardProps {
    onNavigate: (tab: string) => void;
    onQuery?: (query: string) => void;
}

const Dashboard: React.FC<DashboardProps> = ({ onNavigate, onQuery }) => {
  const [stats, setStats] = useState<SystemStats | null>(null);
  const [input, setInput] = useState('');

  useEffect(() => {
    air4.getStats().then(setStats);
  }, []);

  const handleSubmit = (e: React.FormEvent) => {
      e.preventDefault();
      if(input.trim() && onQuery) {
          onQuery(input);
      }
  };

  return (
    <div className="h-full w-full flex flex-col relative overflow-hidden bg-obsidian-950/20">
      {/* Background Decor */}
      <div className="absolute top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 w-[600px] h-[600px] bg-air-600/10 rounded-full blur-[120px] pointer-events-none"></div>

      {/* Top Bar */}
      <div className="w-full p-6 flex justify-between items-center z-10">
          <div className="flex items-center gap-2 px-4 py-2 rounded-full glass-card text-xs font-medium text-slate-400">
             <span className={`w-2 h-2 rounded-full ${stats?.isOffline ? 'bg-red-500' : 'bg-emerald-500 animate-pulse'}`}></span>
             {stats?.isOffline ? 'Offline' : 'Core Active'}
          </div>
          <div className="flex gap-2">
             <button className="p-2 rounded-full hover:bg-white/5 transition-colors text-slate-400 hover:text-white">
                 <Settings className="w-5 h-5" onClick={() => onNavigate('settings')} />
             </button>
          </div>
      </div>

      {/* Hero Content */}
      <div className="flex-1 flex flex-col items-center justify-center p-8 z-10">
         
         {/* Floating Orb / Logo */}
         <div className="mb-8 relative animate-float">
             <div className="w-24 h-24 rounded-full bg-gradient-to-br from-air-500 to-amber-600 shadow-[0_0_60px_rgba(249,115,22,0.4)] flex items-center justify-center relative z-10">
                <img 
                    src="/logo.png" 
                    className="w-14 h-14 object-contain brightness-200 drop-shadow-md"
                    onError={(e) => { e.currentTarget.style.display = 'none'; e.currentTarget.parentElement?.querySelector('svg')?.classList.remove('hidden'); }} 
                />
                <BrainCircuit className="hidden w-12 h-12 text-white" />
             </div>
             {/* Orbital ring */}
             <div className="absolute inset-0 -m-4 border border-air-500/20 rounded-full animate-spin-slow"></div>
         </div>

         <h1 className="text-4xl md:text-5xl font-bold text-white text-center mb-2 tracking-tight">
             Ready to Expand Your Mind?
         </h1>
         <p className="text-slate-400 text-center mb-10 max-w-lg">
             Your local external brain is ready. Retrieve memories, analyze data, or generate new ideas securely.
         </p>

         {/* Quick Actions Chips */}
         <div className="flex flex-wrap gap-3 mb-8 justify-center">
             <ActionChip icon={UploadCloud} label="Ingest Files" onClick={() => onNavigate('ingest')} />
             <ActionChip icon={BrainCircuit} label="Brainstorm" onClick={() => onQuery && onQuery("Let's brainstorm ideas for...")} />
             <ActionChip icon={Database} label="Check Memory" onClick={() => onNavigate('memory')} />
         </div>

         {/* Central Input */}
         <form onSubmit={handleSubmit} className="w-full max-w-2xl relative group">
             <div className="absolute inset-0 bg-air-500/20 blur-xl rounded-2xl opacity-0 group-hover:opacity-100 transition-opacity duration-500"></div>
             <div className="relative glass-card rounded-2xl p-2 flex items-center gap-2 transition-all group-focus-within:border-air-500/50">
                 <div className="p-3 text-air-500">
                     <Sparkles className="w-5 h-5" />
                 </div>
                 <input 
                    type="text" 
                    value={input}
                    onChange={(e) => setInput(e.target.value)}
                    placeholder="Ask anything..." 
                    className="flex-1 bg-transparent border-none outline-none text-white placeholder-slate-500 h-12"
                 />
                 <button type="submit" className="p-3 bg-white/10 hover:bg-air-600 rounded-xl transition-colors text-white">
                     <ArrowRight className="w-5 h-5" />
                 </button>
             </div>
             <div className="mt-3 flex justify-center items-center gap-4 text-xs text-slate-500 font-medium">
                 <span className="flex items-center gap-1"><Command className="w-3 h-3" /> Search</span>
                 <span>•</span>
                 <span>Generate</span>
                 <span>•</span>
                 <span>Analyze</span>
             </div>
         </form>
      </div>

      {/* Bottom Cards */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-4 p-8 pt-0 z-10 max-w-5xl mx-auto w-full">
          <FeatureCard 
            icon={UploadCloud} 
            title="Ingest Data" 
            desc="Process PDF, Docs, CSV locally." 
            onClick={() => onNavigate('ingest')}
          />
          <FeatureCard 
            icon={Database} 
            title="Memory Bank" 
            desc="Search vector embeddings." 
            onClick={() => onNavigate('memory')}
          />
          <FeatureCard 
            icon={Settings} 
            title="Protocol Config" 
            desc="Adjust model parameters." 
            onClick={() => onNavigate('settings')}
          />
      </div>
    </div>
  );
};

const ActionChip = ({ icon: Icon, label, onClick }: any) => (
    <button onClick={onClick} className="flex items-center gap-2 px-4 py-2 rounded-full glass-panel hover:bg-white/10 transition-colors text-sm text-slate-300 border border-white/5">
        <Icon className="w-4 h-4 text-air-400" />
        {label}
    </button>
);

const FeatureCard = ({ icon: Icon, title, desc, onClick }: any) => (
    <button onClick={onClick} className="glass-card p-4 rounded-2xl text-left hover:bg-white/5 transition-all group">
        <div className="flex items-center justify-between mb-3">
            <div className="p-2 rounded-lg bg-white/5 text-slate-300 group-hover:text-air-400 group-hover:bg-air-500/10 transition-colors">
                <Icon className="w-5 h-5" />
            </div>
            <span className="text-[10px] bg-white/5 px-2 py-1 rounded text-slate-500">Open</span>
        </div>
        <h3 className="font-bold text-slate-200 mb-1">{title}</h3>
        <p className="text-xs text-slate-500">{desc}</p>
    </button>
);

export default Dashboard;