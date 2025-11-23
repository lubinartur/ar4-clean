
import React, { useState } from 'react';
import { air4, AVAILABLE_AGENTS } from '../services/air4Service';
import { Agent } from '../types';
import * as Icons from 'lucide-react';
import { ArrowRight, CheckCircle2, Circle, Cpu, Power } from 'lucide-react';

interface WelcomeProps {
  onComplete: () => void;
}

const Welcome: React.FC<WelcomeProps> = ({ onComplete }) => {
  const [step, setStep] = useState(1);
  const [name, setName] = useState('');
  const [selectedAgents, setSelectedAgents] = useState<Agent[]>(AVAILABLE_AGENTS);
  const [isBooting, setIsBooting] = useState(false);

  const toggleAgent = (id: string) => {
    setSelectedAgents(prev => 
      prev.map(a => a.id === id ? { ...a, enabled: !a.enabled } : a)
    );
  };

  const handleFinish = () => {
    setIsBooting(true);
    setTimeout(() => {
        air4.saveConfig(selectedAgents, name);
        onComplete();
    }, 2000);
  };

  // Dynamically render icon based on string name
  const renderIcon = (iconName: string) => {
    const Icon = (Icons as any)[iconName] || Icons.HelpCircle;
    return <Icon className="w-6 h-6" />;
  };

  if (isBooting) {
      return (
        <div className="min-h-screen bg-black flex flex-col items-center justify-center font-mono">
             <div className="relative w-16 h-16 mb-8">
                 <img src="/logo.png" className="w-full h-full object-contain animate-pulse" alt="Loading..." onError={(e) => {e.currentTarget.style.display='none'}} />
                 <Cpu className="w-16 h-16 text-air-500 animate-spin-slow absolute top-0 left-0 -z-10" />
             </div>
             <div className="w-64 h-1 bg-slate-900 rounded overflow-hidden">
                 <div className="h-full bg-air-500 animate-[width_2s_ease-in-out_forwards]" style={{width: '0%'}}></div>
             </div>
             <p className="text-air-500 mt-4 animate-pulse">BOOT SEQUENCE INITIATED...</p>
        </div>
      )
  }

  return (
    <div className="min-h-screen bg-obsidian-950 text-slate-200 flex flex-col items-center justify-center relative overflow-hidden font-mono">
      {/* Background Grids */}
      <div className="absolute inset-0 bg-[linear-gradient(to_right,#ea580c10_1px,transparent_1px),linear-gradient(to_bottom,#ea580c10_1px,transparent_1px)] bg-[size:4rem_4rem] [mask-image:radial-gradient(ellipse_60%_50%_at_50%_50%,#000_70%,transparent_100%)] pointer-events-none"></div>

      <div className="w-full max-w-2xl z-10 p-8">
        <div className="mb-10 text-center animate-in slide-in-from-top-10 duration-700">
          <div className="inline-flex items-center justify-center w-24 h-24 rounded-full bg-slate-900 border border-air-500/30 mb-6 shadow-[0_0_30px_rgba(249,115,22,0.2)] relative overflow-hidden">
             <div className="absolute inset-0 border border-air-500 rounded-full animate-ping opacity-20"></div>
             
             {/* Logo Image */}
             <img 
                src="/logo.png" 
                alt="AIr4 Logo" 
                className="w-14 h-14 object-contain drop-shadow-[0_0_10px_rgba(249,115,22,0.5)] z-10"
                onError={(e) => {
                    e.currentTarget.style.display = 'none';
                    e.currentTarget.parentElement?.classList.add('fallback-icon-welcome');
                }}
             />
             <Cpu className="w-12 h-12 text-air-500 hidden fallback-icon-welcome:block" />
          </div>
          <h1 className="text-4xl font-bold mb-2 tracking-tight text-white glitch-text" data-text="INITIALIZE AIr4">INITIALIZE AIr4</h1>
          <p className="text-air-400/70 text-lg uppercase tracking-widest">External Local Intelligence</p>
        </div>

        {/* Stepper */}
        <div className="flex items-center justify-center gap-4 mb-12">
          {[1, 2, 3].map((i) => (
            <div key={i} className="flex items-center">
              <div className={`w-3 h-3 rounded-full transition-all duration-300 ${step >= i ? 'bg-air-500 shadow-[0_0_10px_rgba(249,115,22,1)]' : 'bg-slate-800'}`} />
              {i < 3 && <div className={`w-12 h-0.5 mx-2 ${step > i ? 'bg-air-900' : 'bg-slate-800'}`} />}
            </div>
          ))}
        </div>

        {/* Step 1: Identity */}
        {step === 1 && (
          <div className="space-y-6 animate-in fade-in slide-in-from-bottom-4 duration-500">
            <div className="bg-slate-900/50 border border-air-500/20 rounded-sm p-8 backdrop-blur-sm relative">
              <div className="absolute top-0 left-0 w-2 h-2 border-t border-l border-air-500"></div>
              <div className="absolute top-0 right-0 w-2 h-2 border-t border-r border-air-500"></div>
              <div className="absolute bottom-0 left-0 w-2 h-2 border-b border-l border-air-500"></div>
              <div className="absolute bottom-0 right-0 w-2 h-2 border-b border-r border-air-500"></div>

              <label className="block text-xs font-bold text-air-500 mb-2 uppercase tracking-widest">User Designation</label>
              <input
                type="text"
                value={name}
                onChange={(e) => setName(e.target.value)}
                placeholder="ENTER NAME..."
                className="w-full bg-slate-950 border border-slate-700 rounded-none px-4 py-4 text-white placeholder-slate-600 focus:outline-none focus:border-air-500 focus:ring-1 focus:ring-air-500 transition-all font-mono uppercase"
                autoFocus
              />
              <p className="mt-3 text-xs text-slate-500">
                Identity required for memory graph tagging.
              </p>
            </div>
            <button
              onClick={() => setStep(2)}
              disabled={!name.trim()}
              className="w-full py-4 bg-air-600 hover:bg-air-500 disabled:opacity-50 disabled:cursor-not-allowed text-black font-bold rounded-sm transition-all flex items-center justify-center gap-2 uppercase tracking-widest"
            >
              Proceed <ArrowRight className="w-5 h-5" />
            </button>
          </div>
        )}

        {/* Step 2: Modules */}
        {step === 2 && (
          <div className="space-y-6 animate-in fade-in slide-in-from-bottom-4 duration-500">
            <div className="bg-slate-900/50 border border-air-500/20 rounded-sm p-6 backdrop-blur-sm max-h-[400px] overflow-y-auto custom-scrollbar">
              <h3 className="text-sm font-bold text-air-500 mb-4 uppercase tracking-widest">Active Modules</h3>
              <div className="space-y-3">
                {selectedAgents.map((agent) => (
                  <div 
                    key={agent.id}
                    onClick={() => toggleAgent(agent.id)}
                    className={`flex items-center gap-4 p-4 rounded-sm border cursor-pointer transition-all group ${
                      agent.enabled 
                        ? 'bg-air-950/40 border-air-500' 
                        : 'bg-slate-950 border-slate-800 hover:border-air-500/50'
                    }`}
                  >
                    <div className={`p-2 rounded-none ${agent.enabled ? 'bg-air-900 text-air-400' : 'bg-slate-900 text-slate-600'}`}>
                      {renderIcon(agent.icon)}
                    </div>
                    <div className="flex-1">
                      <h4 className={`font-medium font-mono uppercase ${agent.enabled ? 'text-white' : 'text-slate-400'}`}>{agent.name}</h4>
                      <p className="text-xs text-slate-500">{agent.description}</p>
                    </div>
                    {agent.enabled ? <CheckCircle2 className="w-5 h-5 text-air-500" /> : <Circle className="w-5 h-5 text-slate-700 group-hover:text-air-500/50" />}
                  </div>
                ))}
              </div>
            </div>
            <div className="flex gap-4">
              <button
                onClick={() => setStep(1)}
                className="flex-1 py-4 border border-slate-700 text-slate-400 hover:text-white rounded-sm transition-colors uppercase font-mono text-xs"
              >
                Back
              </button>
              <button
                onClick={() => setStep(3)}
                className="flex-1 py-4 bg-air-600 hover:bg-air-500 text-black font-bold rounded-sm transition-all uppercase tracking-widest"
              >
                Confirm Configuration
              </button>
            </div>
          </div>
        )}

        {/* Step 3: Finalize */}
        {step === 3 && (
          <div className="space-y-6 animate-in fade-in slide-in-from-bottom-4 duration-500 text-center">
            <div className="bg-slate-900/50 border border-air-500/20 rounded-sm p-10 backdrop-blur-sm flex flex-col items-center relative overflow-hidden">
               {/* Scanning line */}
               <div className="absolute top-0 left-0 w-full h-1 bg-air-500/50 shadow-[0_0_15px_rgba(249,115,22,0.8)] animate-[scan_2s_linear_infinite]"></div>

              <div className="relative w-24 h-24 mb-6">
                <div className="absolute inset-0 border-2 border-slate-800 rounded-full border-dashed animate-spin-slow"></div>
                <div className="absolute inset-0 border-2 border-t-air-500 border-r-transparent border-b-transparent border-l-transparent rounded-full animate-spin"></div>
                
                <img 
                    src="/logo.png" 
                    alt="AIr4"
                    className="absolute inset-0 m-auto w-12 h-12 object-contain"
                    onError={(e) => {
                        e.currentTarget.style.display = 'none';
                        e.currentTarget.parentElement?.classList.add('fallback-spin-icon');
                    }}
                />
                <Cpu className="absolute inset-0 m-auto w-10 h-10 text-air-500 hidden fallback-spin-icon:block" />
              </div>
              <h3 className="text-xl font-bold text-white mb-2 font-mono uppercase">Generating Keys...</h3>
              <div className="text-left w-full max-w-xs space-y-1 font-mono text-xs text-air-400/80 mt-4">
                  <p className="animate-pulse">{'>'} Indexing memory vector space...</p>
                  <p className="animate-pulse delay-100">{'>'} Connecting to Mistral-7B...</p>
                  <p className="animate-pulse delay-200">{'>'} Establishing secure handshake...</p>
              </div>
            </div>
            <button
              onClick={handleFinish}
              className="w-full py-4 bg-gradient-to-r from-air-600 to-amber-600 hover:from-air-500 hover:to-amber-500 text-black font-bold rounded-sm transition-all shadow-[0_0_20px_rgba(249,115,22,0.4)] uppercase tracking-widest flex items-center justify-center gap-3"
            >
              <Power className="w-5 h-5" />
              Engage System
            </button>
          </div>
        )}
      </div>
    </div>
  );
};

export default Welcome;