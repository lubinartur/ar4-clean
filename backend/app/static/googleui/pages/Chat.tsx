
import React, { useState, useEffect, useRef } from "react";
import { useSettings } from "../hooks/useSettings";
import { air4 } from '../services/air4Service';
import { Message, MemoryItem, RouterDecision, SystemStats, ResponseStyle } from '../types';
import { Send, Mic, Paperclip, BrainCircuit, Cpu, Sparkles, Activity, Database, Circle, ChevronDown, Check, Star, Copy, ClipboardCheck } from 'lucide-react';

interface ChatProps {
    sessionId: string | null;
    initialQuery?: string;
    clearInitialQuery?: () => void;
}

const Chat: React.FC<ChatProps> = ({ sessionId, initialQuery, clearInitialQuery }) => {
  const { settings } = useSettings();

  const [messages, setMessages] = useState<Message[]>([]);
  const [input, setInput] = useState('');
  const [isThinking, setIsThinking] = useState(false);
  const [routerState, setRouterState] = useState<RouterDecision | null>(null);
  const [stats, setStats] = useState<SystemStats | null>(null);
  const [lastStatsTime, setLastStatsTime] = useState<number>(Date.now());
  const [timeAgo, setTimeAgo] = useState(0);
  const [responseStyle, setResponseStyle] = useState<ResponseStyle>(air4.getResponseStyle());
  const [showStyleMenu, setShowStyleMenu] = useState(false);
  const [inputError, setInputError] = useState(false);
  const [savedMessageIds, setSavedMessageIds] = useState<Set<string>>(new Set());
  const [copiedId, setCopiedId] = useState<string | null>(null);
  const styleMenuRef = useRef<HTMLDivElement>(null);
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLInputElement | null>(null);
  const autoBrainstormRef = useRef(false);

  // Load session messages when ID changes
  useEffect(() => {
      if (sessionId) {
          const session = air4.getSession(sessionId);
          if (session) {
              setMessages(session.messages);
          } else {
              setMessages([]);
          }
      }
      setSavedMessageIds(new Set()); // Reset local saved state on session change
  }, [sessionId]);

  // Handle outside click for style menu
  useEffect(() => {
      const handleClickOutside = (event: MouseEvent) => {
          if (styleMenuRef.current && !styleMenuRef.current.contains(event.target as Node)) {
              setShowStyleMenu(false);
          }
      };
      document.addEventListener('mousedown', handleClickOutside);
      return () => document.removeEventListener('mousedown', handleClickOutside);
  }, []);

  // Poll for system stats to update header
  useEffect(() => {
    const fetchStats = async () => {
        try {
            const s = await air4.getStats();
            setStats(s);
            setLastStatsTime(Date.now());
            setTimeAgo(0);
        } catch (e) {
            // Silently fail or set offline in service
        }
    };
    fetchStats();
    const interval = setInterval(fetchStats, 5000); // Update every 5 seconds
    return () => clearInterval(interval);
  }, []);

  // Update time ago counter
  useEffect(() => {
      const timer = setInterval(() => {
          setTimeAgo(Math.floor((Date.now() - lastStatsTime) / 1000));
      }, 1000);
      return () => clearInterval(timer);
  }, [lastStatsTime]);

  const scrollToBottom = () => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  };

  useEffect(() => {
    scrollToBottom();
  }, [messages, routerState, isThinking]);

  useEffect(() => {
      if (initialQuery) {
          setInput(initialQuery);
          if (clearInitialQuery) clearInitialQuery();
          if (inputRef.current) {
              const len = initialQuery.length;
              inputRef.current.focus();
              try {
                  inputRef.current.setSelectionRange(len, len);
              } catch (e) {
                  // ignore selection errors
              }
          }
      }
  }, [initialQuery, clearInitialQuery]);


  useEffect(() => {
      if (initialQuery) {
          setInput(initialQuery);
          if (inputRef.current) {
              const len = initialQuery.length;
              inputRef.current.focus();
              try {
                  inputRef.current.setSelectionRange(len, len);
              } catch (e) {
                  // ignore selection errors
              }
          }
          if (clearInitialQuery) clearInitialQuery();
      }
  }, [initialQuery]);

  const handleStyleChange = (style: ResponseStyle) => {
      setResponseStyle(style);
      air4.setResponseStyle(style);
      setShowStyleMenu(false);
  };

  const handleSaveMemory = async (msg: Message) => {
      if (savedMessageIds.has(msg.id)) return;
      const success = await air4.addManualMemory(msg.content, 'chat-selection');
      if (success) {
          setSavedMessageIds(prev => new Set(prev).add(msg.id));
      }
  };

  const handleCopy = (text: string, id: string) => {
      navigator.clipboard.writeText(text);
      setCopiedId(id);
      setTimeout(() => setCopiedId(null), 2000);
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    
    // Input Validation
    if (!input.trim()) {
        setInputError(true);
        setTimeout(() => setInputError(false), 3000);
        return;
    }

    if (isThinking || !sessionId) return;
    
    setInputError(false);

    const userMsg: Message = {
      id: Date.now().toString(),
      role: 'user',
      content: input,
      timestamp: Date.now()
    };

    const newMessages = [...messages, userMsg];
    setMessages(newMessages);
    setInput('');
    setIsThinking(true);
    setRouterState(null);

    try {
      const stream = air4.streamChat(newMessages, sessionId, settings);
      
      const botMsgId = (Date.now() + 1).toString();
      // Placeholder for bot message
      setMessages(prev => [...prev, {
        id: botMsgId,
        role: 'assistant',
        content: '',
        timestamp: Date.now()
      }]);

      let fullContent = '';
      let context: MemoryItem[] | undefined = undefined;
      let decision: RouterDecision | undefined = undefined;

      for await (const part of stream) {
        if (part.decision) {
            decision = part.decision;
            setRouterState(decision);
             setMessages(prev => prev.map(m => 
                m.id === botMsgId 
                    ? { ...m, modelUsed: decision?.model, domain: decision?.domain } 
                    : m
            ));
        }

        if (part.context) {
          context = part.context;
          setMessages(prev => prev.map(m => 
            m.id === botMsgId 
                ? { ...m, contextUsed: context } 
                : m
            ));
        }
        
        if (part.chunk) {
            fullContent += part.chunk;
            setMessages(prev => prev.map(m => 
            m.id === botMsgId 
                ? { ...m, content: fullContent } 
                : m
            ));
        }
      }

    } catch (error) {
      console.error("Stream error", error);
    } finally {
      setIsThinking(false);
    }
  };

  if (!sessionId) {
      return (
          <div className="h-full flex items-center justify-center text-slate-500">
              Select or create a session to begin.
          </div>
      )
  }

  // Determine display values for header
  const isOffline = stats?.isOffline ?? false;
  // Use router decision if active, otherwise fallback to stats (backend) or user config preference
  const modelName = routerState?.model || stats?.modelName || air4.getActiveModel() || 'Mistral-7B';
  const memoryStatus = isOffline ? 'Inactive' : 'Active';
  
  const styles: { id: ResponseStyle; label: string }[] = [
      { id: 'short', label: 'Short' },
      { id: 'normal', label: 'Normal' },
      { id: 'detailed', label: 'Detailed' },
  ];

  return (
    <div className="flex flex-col h-full relative">
      {/* Enhanced System Status Header */}
      <div className="h-16 flex items-center justify-between px-6 border-b border-white/5 bg-black/20 backdrop-blur-md">
        
        {/* Left: Title */}
        <div className="flex items-center gap-3">
            <div className={`w-2 h-8 rounded-full shadow-[0_0_10px_rgba(249,115,22,0.4)] ${isOffline ? 'bg-red-500' : 'bg-air-500'}`}></div>
            <div>
                <h2 className="text-sm font-bold text-white tracking-wide uppercase">Core Dialog</h2>
                <div className="flex items-center gap-2 text-[10px] text-slate-500 font-mono">
                    <span>ID: {sessionId.slice(-8)}</span>
                </div>
            </div>
        </div>

        {/* Right: Detailed Status Bar */}
        <div className="flex items-center gap-4 md:gap-6">
            
            {/* Style Selector */}
            <div className="relative" ref={styleMenuRef}>
                 <button 
                    onClick={() => setShowStyleMenu(!showStyleMenu)}
                    className="flex items-center gap-2 px-3 py-1.5 rounded-lg bg-white/5 hover:bg-white/10 transition-colors border border-white/5"
                 >
                     <div className="flex flex-col items-start">
                         <span className="text-[9px] text-slate-500 uppercase font-bold tracking-wider leading-none mb-0.5">Style</span>
                         <span className="text-[10px] text-air-400 font-mono font-bold capitalize">{responseStyle}</span>
                     </div>
                     <ChevronDown className="w-3 h-3 text-slate-500" />
                 </button>

                 {showStyleMenu && (
                     <div className="absolute top-full right-0 mt-2 w-32 bg-[#0a0f1e] border border-white/10 rounded-xl shadow-xl z-50 overflow-hidden animate-in fade-in zoom-in-95 duration-100">
                         {styles.map(s => (
                             <button
                                key={s.id}
                                onClick={() => handleStyleChange(s.id)}
                                className={`w-full flex items-center justify-between px-3 py-2 text-[11px] font-medium hover:bg-white/5 transition-colors ${responseStyle === s.id ? 'text-air-500 bg-air-500/5' : 'text-slate-400'}`}
                             >
                                 {s.label}
                                 {responseStyle === s.id && <Check className="w-3 h-3" />}
                             </button>
                         ))}
                     </div>
                 )}
            </div>

            <div className="h-4 w-[1px] bg-white/10 hidden md:block"></div>

            {/* 1. Core Status */}
            <div className="flex items-center gap-2">
                <div className={`relative flex h-2 w-2`}>
                  <span className={`animate-ping absolute inline-flex h-full w-full rounded-full opacity-75 ${isOffline ? 'bg-red-500' : 'bg-emerald-500'}`}></span>
                  <span className={`relative inline-flex rounded-full h-2 w-2 ${isOffline ? 'bg-red-500' : 'bg-emerald-500'}`}></span>
                </div>
                <div className="flex flex-col">
                    <span className={`text-[10px] font-bold ${isOffline ? 'text-red-400' : 'text-emerald-400'}`}>
                        {isOffline ? 'Offline' : stats ? 'Local Core Online' : 'Loading...'}
                    </span>
                </div>
            </div>

            <div className="h-4 w-[1px] bg-white/10 hidden md:block"></div>

            {/* 2. Model */}
            <div className="hidden md:flex flex-col items-start">
                 <span className="text-[9px] text-slate-500 uppercase font-bold tracking-wider">Model</span>
                 <span className="text-[10px] text-air-400 font-mono flex items-center gap-1">
                    <Cpu className="w-3 h-3" /> {modelName}
                 </span>
            </div>

            <div className="h-4 w-[1px] bg-white/10 hidden md:block"></div>

            {/* 3. Memory Status */}
            <div className="hidden md:flex flex-col items-start">
                 <span className="text-[9px] text-slate-500 uppercase font-bold tracking-wider">Memory</span>
                 <span className={`text-[10px] font-mono flex items-center gap-1 ${isOffline ? 'text-red-400' : 'text-indigo-400'}`}>
                    <Database className="w-3 h-3" /> ChromaDB: {memoryStatus}
                 </span>
            </div>

            <div className="h-4 w-[1px] bg-white/10 hidden md:block"></div>

             {/* 4. Index Update */}
             <div className="hidden md:flex flex-col items-start min-w-[80px]">
                 <span className="text-[9px] text-slate-500 uppercase font-bold tracking-wider">Index Update</span>
                 <span className="text-[10px] text-slate-400 font-mono flex items-center gap-1">
                    <Activity className="w-3 h-3" /> {stats ? `${timeAgo} sec ago` : '...'}
                 </span>
            </div>
        </div>
      </div>

      {/* Messages Area */}
      <div className="flex-1 overflow-y-auto p-4 md:p-8 space-y-6 custom-scrollbar scroll-smooth">
        {messages.map((msg) => (
          <div 
            key={msg.id} 
            className={`flex flex-col ${msg.role === 'user' ? 'items-end' : 'items-start'} animate-message-in`}
            style={{ animationFillMode: 'both' }}
          >
            
            {/* Metadata (Avatar name + Timestamp) */}
            <div className="text-[10px] text-slate-500 mb-1 px-1 flex items-center gap-2">
                <span className="font-medium">{msg.role === 'user' ? 'You' : 'AIr4 Core'}</span>
                <span className="opacity-50 text-[9px] font-mono">
                    {new Date(msg.timestamp).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}
                </span>
            </div>

            {/* Bubble */}
            <div className={`max-w-[85%] md:max-w-[70%] p-4 rounded-2xl text-sm leading-relaxed whitespace-pre-wrap relative shadow-sm ${
                msg.role === 'user' 
                  ? 'bg-air-600 text-white rounded-br-sm shadow-[0_4px_20px_rgba(234,88,12,0.2)]' 
                  : 'glass-card text-slate-200 rounded-bl-sm border-white/5 shadow-[0_4px_20px_rgba(0,0,0,0.2)]'
            }`}>
                
                {/* RAG Context */}
                {msg.role === 'assistant' && msg.contextUsed && msg.contextUsed.length > 0 && (
                    <div className="mb-3 flex flex-col gap-1 pb-3 border-b border-white/5">
                        <div className="flex items-center gap-1 text-[10px] font-bold text-air-400 uppercase tracking-wider">
                            <BrainCircuit className="w-3 h-3" /> Memory Retrieval
                        </div>
                        {msg.contextUsed.map((m, idx) => (
                            <div key={idx} className="text-[10px] text-slate-400 truncate bg-white/5 px-2 py-1.5 rounded flex items-center gap-2 border border-white/5">
                                <span className="w-1 h-1 bg-air-500 rounded-full"></span>
                                {m.content}
                            </div>
                        ))}
                    </div>
                )}
                
                {msg.content}

                {/* AI Actions Footer */}
                {msg.role === 'assistant' && !isThinking && (
                    <div className="mt-3 pt-2 border-t border-white/5 flex items-center gap-2 opacity-60 hover:opacity-100 transition-opacity">
                        <button 
                            onClick={() => handleSaveMemory(msg)}
                            className={`p-1.5 rounded-lg transition-all ${
                                savedMessageIds.has(msg.id) 
                                ? 'bg-air-500/10 text-air-500' 
                                : 'hover:bg-white/10 text-slate-500 hover:text-air-400'
                            }`}
                            title="Send to Memory Bank"
                        >
                            <Star className={`w-3.5 h-3.5 ${savedMessageIds.has(msg.id) ? 'fill-air-500' : ''}`} />
                        </button>
                        <button 
                            onClick={() => handleCopy(msg.content, msg.id)}
                            className="p-1.5 hover:bg-white/10 rounded-lg text-slate-500 hover:text-white transition-colors"
                            title="Copy to Clipboard"
                        >
                            {copiedId === msg.id ? <ClipboardCheck className="w-3.5 h-3.5 text-emerald-500" /> : <Copy className="w-3.5 h-3.5" />}
                        </button>
                    </div>
                )}
            </div>
          </div>
        ))}

        {isThinking && (
           <div className="flex justify-start animate-message-in">
             <div className="glass-card px-4 py-3 rounded-2xl rounded-bl-sm flex items-center gap-3 border border-air-500/20">
                <div className="flex gap-1">
                    <span className="w-1.5 h-1.5 bg-air-500 rounded-full animate-bounce"></span>
                    <span className="w-1.5 h-1.5 bg-air-500 rounded-full animate-bounce delay-75"></span>
                    <span className="w-1.5 h-1.5 bg-air-500 rounded-full animate-bounce delay-150"></span>
                </div>
                <span className="text-xs text-air-400 font-mono tracking-wide">Processing...</span>
             </div>
           </div>
        )}
        <div ref={messagesEndRef} />
      </div>

      {/* Input Area */}
      <div className="p-4 md:p-6 bg-gradient-to-t from-obsidian-950/90 via-obsidian-950/50 to-transparent">
        <form 
            onSubmit={handleSubmit} 
            className={`max-w-4xl mx-auto glass-input rounded-2xl p-2 flex items-end gap-2 shadow-2xl border transition-all duration-300 ${
                inputError 
                ? 'border-red-500/50 shadow-[0_0_20px_rgba(239,68,68,0.25)] animate-shake' 
                : 'border-white/10 focus-within:border-air-500/30'
            }`}
        >
          <button type="button" className="p-3 text-slate-400 hover:text-white hover:bg-white/10 rounded-xl transition-colors">
              <Paperclip className="w-5 h-5" />
          </button>
          
          <div className="flex-1 py-3">
            <input
                type="text"
                    ref={inputRef}
                value={input}
                onChange={(e) => {
                    setInput(e.target.value);
                    if(inputError) setInputError(false);
                }}
                placeholder={inputError ? "Message cannot be empty..." : "Send a message to the Core..."}
                className={`w-full bg-transparent border-none outline-none text-white placeholder-slate-500 resize-none ${inputError ? 'placeholder-red-400/50' : ''}`}
            />
          </div>
          
          <button 
            type="submit" 
            disabled={isThinking}
            className={`p-3 rounded-xl transition-all shadow-lg ${
                isThinking 
                ? 'bg-slate-800 text-slate-500 cursor-not-allowed' 
                : 'bg-gradient-to-tr from-air-600 to-amber-600 text-white hover:brightness-110 shadow-air-600/20'
            }`}
          >
              <Send className="w-5 h-5" />
          </button>
        </form>
        <div className="text-center mt-3 flex items-center justify-center gap-2">
            <span className="w-1.5 h-1.5 rounded-full bg-emerald-500 shadow-[0_0_5px_rgba(16,185,129,0.5)]"></span>
            <span className="text-[10px] text-slate-600 font-mono uppercase tracking-widest">
                System Secure • AES-256 Encrypted
            </span>
        </div>
      </div>
    </div>
  );
};

export default Chat;