
import React, { useState } from 'react';
import { air4, AVAILABLE_AGENTS } from '../services/air4Service';
import { Agent } from '../types';
import { ArrowRight, Check, Cpu, Sparkles, Activity, DollarSign, Terminal } from 'lucide-react';
import { Logo } from '../components/Logo';

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
    }, 2500);
  };

  const renderIcon = (iconName: string) => {
    switch (iconName) {
        case 'Cpu': return <Cpu className="w-5 h-5" />;
        case 'Activity': return <Activity className="w-5 h-5" />;
        case 'DollarSign': return <DollarSign className="w-5 h-5" />;
        case 'Terminal': return <Terminal className="w-5 h-5" />;
        default: return <Sparkles className="w-5 h-5" />;
    }
  };

  if (isBooting) {
      return (
        <div className="min-h-screen flex flex-col items-center justify-center relative overflow-hidden bg-[#020617] text-slate-200 font-sans">
             <div className="absolute inset-0 bg-[radial-gradient(circle_at_center,_var(--tw-gradient-stops))] from-air-900/10 via-[#020617] to-[#020617]"></div>
             
             <div className="relative z-10 flex flex-col items-center">
                 <div className="relative w-32 h-32 mb-8">
                     <div className="absolute inset-0 border-4 border-slate-800/30 rounded-full"></div>
                     <div className="absolute inset-0 border-4 border-t-air-500 border-r-transparent border-b-transparent border-l-transparent rounded-full animate-spin"></div>
                     <div className="absolute inset-0 flex items-center justify-center">
                        <Logo className="w-12 h-12 text-air-500 animate-pulse" />
                     </div>
                 </div>
                 
                 <h2 className="text-3xl font-bold text-white mb-2 tracking-tight">System Initializing</h2>
                 <p className="text-slate-500 text-sm">Configuring local neural pathways...</p>
             </div>
        </div>
      )
  }

  return (
    <div className="min-h-screen w-full flex items-center justify-center p-4 md:p-8 bg-obsidian-950/20 relative font-sans text-slate-200">
       <div className="absolute inset-0 bg-[radial-gradient(circle_at_15%_50%,rgba(234,88,12,0.08),transparent_25%),radial-gradient(circle_at_85%_30%,rgba(124,45,18,0.1),transparent_25%)] pointer-events-none"></div>

       <div className="w-full max-w-5xl h-[650px] glass-panel rounded-[2rem] border border-white/5 shadow-2xl flex overflow-hidden relative z-10 animate-in fade-in zoom-in-95 duration-500">
           
           {/* Left Panel */}
           <div className="hidden md:flex w-[40%] bg-slate-900/40 relative flex-col justify-between p-10 border-r border-white/5">
                <div className="absolute inset-0 bg-gradient-to-b from-transparent to-black/60"></div>
                
                <div className="relative z-10 flex items-center gap-3">
                    <div className="w-10 h-10 rounded-xl bg-air-500/10 flex items-center justify-center border border-air-500/20 shadow-[0_0_15px_rgba(249,115,22,0.15)]">
                        <Logo className="w-5 h-5 text-air-500" />
                    </div>
                    <span className="font-bold text-lg text-white tracking-tight">AIr4 Core</span>
                </div>

                <div className="relative z-10">
                    <h1 className="text-4xl font-bold text-white mb-4 leading-tight">
                        Your External <br/>
                        <span className="text-transparent bg-clip-text bg-gradient-to-r from-air-400 to-amber-200">Local Mind.</span>
                    </h1>
                    <p className="text-slate-400 text-sm leading-relaxed max-w-xs">
                        Private, offline-first intelligence that remembers your context and helps you analyze complex data securely.
                    </p>
                </div>

                <div className="relative z-10 flex gap-2">
                    {[1, 2, 3].map(i => (
                        <div key={i} className={`h-1 rounded-full transition-all duration-500 ${step === i ? 'w-8 bg-air-500' : step > i ? 'w-1 bg-air-900' : 'w-1 bg-slate-800'}`}></div>
                    ))}
                </div>
           </div>

           {/* Right Panel */}
           <div className="flex-1 bg-slate-950/20 p-8 md:p-12 flex flex-col justify-center relative">
               
               <div className="md:hidden mb-8 flex items-center gap-3">
                    <div className="w-10 h-10 rounded-xl bg-air-500/10 flex items-center justify-center border border-air-500/20">
                        <Logo className="w-5 h-5 text-air-500" />
                    </div>
                    <span className="font-bold text-xl text-white">AIr4 Core</span>
               </div>

               {step === 1 && (
                   <div className="space-y-8 animate-in slide-in-from-right-8 duration-500">
                       <div>
                           <h2 className="text-2xl font-bold text-white mb-2">Welcome, Operator.</h2>
                           <p className="text-slate-400">How should the system address you?</p>
                       </div>

                       <div className="space-y-6">
                           <div className="group">
                               <label className="block text-xs font-bold text-slate-500 mb-2 ml-1 uppercase tracking-wider">User Designation</label>
                               <input 
                                    type="text" 
                                    value={name}
                                    onChange={(e) => setName(e.target.value)}
                                    placeholder="Enter your name..."
                                    className="w-full bg-white/5 border border-white/10 rounded-2xl px-5 py-4 text-lg text-white placeholder-slate-600 focus:outline-none focus:border-air-500/50 focus:bg-white/10 transition-all"
                                    autoFocus
                               />
                           </div>
                           <button 
                                onClick={() => setStep(2)}
                                disabled={!name.trim()}
                                className="w-full py-4 bg-air-600 hover:bg-air-500 text-white font-semibold rounded-2xl shadow-lg shadow-air-600/20 transition-all disabled:opacity-50 disabled:shadow-none flex items-center justify-center gap-2 group"
                           >
                               Continue <ArrowRight className="w-5 h-5 group-hover:translate-x-1 transition-transform" />
                           </button>
                       </div>
                   </div>
               )}

               {step === 2 && (
                   <div className="h-full flex flex-col animate-in slide-in-from-right-8 duration-500">
                       <div className="mb-6">
                           <h2 className="text-2xl font-bold text-white mb-2">Select Modules</h2>
                           <p className="text-slate-400 text-sm">Enable specialized agents for your workflow.</p>
                       </div>

                       <div className="flex-1 overflow-y-auto custom-scrollbar -mr-4 pr-4 space-y-3 pb-6">
                           {selectedAgents.map(agent => (
                               <div 
                                    key={agent.id}
                                    onClick={() => toggleAgent(agent.id)}
                                    className={`p-4 rounded-2xl border cursor-pointer transition-all flex items-center gap-4 group ${
                                        agent.enabled 
                                        ? 'bg-air-500/10 border-air-500/30 shadow-[0_0_20px_rgba(249,115,22,0.05)]' 
                                        : 'bg-white/5 border-white/5 hover:bg-white/10 hover:border-white/10'
                                    }`}
                               >
                                   <div className={`p-3 rounded-xl transition-colors ${agent.enabled ? 'bg-air-500 text-white shadow-lg shadow-air-500/30' : 'bg-slate-800 text-slate-500'}`}>
                                       {renderIcon(agent.icon)}
                                   </div>
                                   <div className="flex-1">
                                       <h4 className={`font-semibold transition-colors ${agent.enabled ? 'text-white' : 'text-slate-400'}`}>{agent.name}</h4>
                                       <p className="text-xs text-slate-500">{agent.description}</p>
                                   </div>
                                   <div className={`w-6 h-6 rounded-full border-2 flex items-center justify-center transition-colors ${agent.enabled ? 'border-air-500 bg-air-500' : 'border-slate-700'}`}>
                                       {agent.enabled && <Check className="w-3 h-3 text-white" />}
                                   </div>
                               </div>
                           ))}
                       </div>

                       <div className="pt-4 flex gap-3 mt-auto">
                           <button 
                                onClick={() => setStep(1)}
                                className="px-6 py-4 rounded-2xl text-slate-400 hover:text-white hover:bg-white/5 transition-colors font-medium border border-transparent hover:border-white/10"
                           >
                               Back
                           </button>
                           <button 
                                onClick={() => setStep(3)}
                                className="flex-1 py-4 bg-white text-black hover:bg-slate-200 font-bold rounded-2xl transition-all shadow-lg flex items-center justify-center gap-2"
                           >
                               Finalize Setup
                           </button>
                       </div>
                   </div>
               )}

               {step === 3 && (
                   <div className="flex-1 flex flex-col justify-center items-center text-center animate-in slide-in-from-right-8 duration-500">
                       <div className="w-24 h-24 bg-air-500/10 rounded-full flex items-center justify-center mb-6 ring-1 ring-air-500/30 relative orb-glow">
                           <div className="absolute inset-0 bg-air-500/20 blur-xl rounded-full"></div>
                           <Logo className="w-10 h-10 text-air-500 relative z-10" />
                       </div>
                       
                       <h2 className="text-3xl font-bold text-white mb-3">You're All Set!</h2>
                       <p className="text-slate-400 max-w-sm mb-10 leading-relaxed">
                           AIr4 is ready to run locally. Your data is encrypted and stored on this device.
                       </p>

                       <button 
                            onClick={handleFinish}
                            className="w-full max-w-sm py-4 bg-gradient-to-r from-air-600 to-amber-600 hover:from-air-500 hover:to-amber-500 text-white font-bold rounded-2xl shadow-xl shadow-air-600/20 transition-all transform hover:scale-[1.02]"
                       >
                           Launch Interface
                       </button>
                   </div>
               )}
           </div>
       </div>
       
       <div className="absolute bottom-6 text-center text-[10px] text-slate-600 font-medium tracking-wide">
           SECURE OFFLINE ENVIRONMENT • v0.12.1
       </div>
    </div>
  );
};

export default Welcome;
