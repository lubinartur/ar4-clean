
import React, { useEffect, useState, useRef } from 'react';
import { air4 } from '../services/air4Service';
import { SystemStats } from '../types';
import { BrainCircuit, UploadCloud, Database, Settings, Sparkles, ArrowRight, Command } from 'lucide-react';
import { Logo } from '../components/Logo';

interface DashboardProps {
    onNavigate: (tab: string) => void;
    onQuery?: (query: string) => void;
    onBrainstorm?: (query: string) => void;
}

const Dashboard: React.FC<DashboardProps> = ({ onNavigate, onQuery, onBrainstorm }) => {
  const [stats, setStats] = useState<SystemStats | null>(null);
  const [input, setInput] = useState('');
  const [mousePos, setMousePos] = useState({ x: 0, y: 0 });
  const containerRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    air4.getStats().then(setStats);
  }, []);

  const handleSubmit = (e: React.FormEvent) => {
      e.preventDefault();
      if(input.trim() && onQuery) {
          onQuery(input);
      }
  };

  const handleMouseMove = (e: React.MouseEvent) => {
    const { clientX, clientY } = e;
    const { innerWidth, innerHeight } = window;
    
    // Normalize coordinates (-1 to 1)
    const x = (clientX / innerWidth - 0.5) * 2;
    const y = (clientY / innerHeight - 0.5) * 2;
    
    setMousePos({ x, y });
  };

  return (
    <div 
        ref={containerRef}
        onMouseMove={handleMouseMove}
        className="h-full w-full flex flex-col relative overflow-hidden bg-obsidian-950/20"
    >
      {/* Parallax Background Decor */}
      <div 
          className="absolute top-1/2 left-1/2 w-[600px] h-[600px] bg-air-600/10 rounded-full blur-[120px] pointer-events-none transition-transform duration-100 ease-out will-change-transform"
          style={{ 
              transform: `translate(calc(-50% + ${mousePos.x * -20}px), calc(-50% + ${mousePos.y * -20}px))` 
          }}
      ></div>
      <div 
          className="absolute bottom-0 right-0 w-[400px] h-[400px] bg-indigo-500/5 rounded-full blur-[100px] pointer-events-none transition-transform duration-100 ease-out will-change-transform"
          style={{ 
              transform: `translate(${mousePos.x * 30}px, ${mousePos.y * 30}px)` 
          }}
      ></div>

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
         
         {/* Floating Orb / Logo - Intensified */}
         <div className="mb-10 relative animate-float">
             {/* Core Glow */}
             <div className="w-28 h-28 rounded-full bg-gradient-to-br from-air-500 to-amber-600 neural-core-glow flex items-center justify-center relative z-10 shadow-[0_0_50px_rgba(249,115,22,0.4)]">
                <img
                  src="/static/googleui/assets/air4.svg"
                  className="w-20 h-20 brightness-200 drop-shadow-[0_0_10px_rgba(255,255,255,0.8)]"
                  alt="Air4 Logo"
                />
             </div>
             
             {/* Orbital ring 1 */}
             <div className="absolute inset-0 -m-6 border border-air-500/20 rounded-full animate-spin-slow pointer-events-none"></div>
             
             {/* Orbital ring 2 (Counter rotating) */}
             <div className="absolute inset-0 -m-3 border border-indigo-400/10 rounded-full animate-spin-reverse-slow pointer-events-none"></div>
             
             {/* Particles container (Optional Visual enhancement) */}
             <div className="absolute top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 w-64 h-64 opacity-50 pointer-events-none">
                 <div className="absolute top-0 left-1/2 w-1 h-1 bg-air-400 rounded-full animate-pulse"></div>
                 <div className="absolute bottom-0 left-1/2 w-1 h-1 bg-air-400 rounded-full animate-pulse" style={{ animationDelay: '1s' }}></div>
             </div>
         </div>

         <div className="text-center relative">
             <h1 className="text-4xl md:text-5xl font-bold text-white mb-2 tracking-tight drop-shadow-2xl">
                 Ready to Expand Your Mind?
             </h1>
             <p className="text-slate-400 mb-10 max-w-lg mx-auto leading-relaxed drop-shadow-lg">
                 Your local external brain is ready. Retrieve memories, analyze data, or generate new ideas securely.
             </p>
         </div>

         {/* Quick Actions Chips */}
         <div className="flex flex-wrap gap-3 mb-8 justify-center relative z-20">
             <ActionChip icon={UploadCloud} label="Ingest Files" onClick={() => onNavigate('ingest')} />
             <ActionChip 
             icon={BrainCircuit} 
             label="Brainstorm" 
             onClick={() => {
                 const q = "Let's brainstorm ideas for...";
                 if (onBrainstorm) onBrainstorm(q);
                 else if (onQuery) onQuery(q);
             }} 
             />
             <ActionChip icon={Database} label="Check Memory" onClick={() => onNavigate('memory')} />
         </div>

         {/* Central Input */}
         <form onSubmit={handleSubmit} className="w-full max-w-2xl relative group z-20">
             <div className="absolute inset-0 bg-air-500/20 blur-xl rounded-2xl opacity-0 group-hover:opacity-100 transition-opacity duration-500 pointer-events-none"></div>
             <div className="relative glass-card rounded-2xl p-2 flex items-center gap-2 transition-all group-focus-within:border-air-500/50 group-focus-within:bg-black/40">
                 <div className="p-3 text-air-500">
                     <Sparkles className="w-5 h-5 animate-pulse" />
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
             <div className="mt-3 flex justify-center items-center gap-4 text-xs text-slate-500 font-medium opacity-70">
                 <span className="flex items-center gap-1"><Command className="w-3 h-3" /> Search</span>
                 <span>•</span>
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
    <button onClick={onClick} className="flex items-center gap-2 px-4 py-2 rounded-full glass-panel hover:bg-white/10 hover:scale-105 transition-all duration-300 text-sm text-slate-300 border border-white/5 hover:border-air-500/30">
        <Icon className="w-4 h-4 text-air-400" />
        {label}
    </button>
);

const FeatureCard = ({ icon: Icon, title, desc, onClick }: any) => (
    <button onClick={onClick} className="glass-card p-5 rounded-2xl text-left hover:bg-white/5 transition-all group relative overflow-hidden border border-white/5 hover:border-air-500/30">
        <div className="relative z-10">
            <div className="flex items-center justify-between mb-4">
                <div className="p-3 rounded-2xl bg-white/5 text-slate-300 group-hover:text-air-400 group-hover:bg-air-500/20 group-hover:shadow-[0_0_20px_rgba(249,115,22,0.2)] transition-all duration-300">
                    <Icon className="w-6 h-6" />
                </div>
                <span className="text-[10px] bg-white/5 px-2.5 py-1 rounded-full text-slate-500 group-hover:bg-white/10 group-hover:text-slate-300 transition-colors">Open</span>
            </div>
            <h3 className="font-bold text-slate-200 mb-1 group-hover:text-white transition-colors text-lg">{title}</h3>
            <p className="text-xs text-slate-500 group-hover:text-slate-400 transition-colors leading-relaxed">{desc}</p>
        </div>
    </button>
);

export default Dashboard;
