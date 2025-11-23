import React, { useState, useRef, useEffect } from 'react';
import { air4 } from '../services/air4Service';
import { Message, MemoryItem, RouterDecision } from '../types';
import { Send, Mic, Paperclip, BrainCircuit, Cpu, Sparkles } from 'lucide-react';

interface ChatProps {
    initialQuery?: string;
    clearInitialQuery?: () => void;
}

const Chat: React.FC<ChatProps> = ({ initialQuery, clearInitialQuery }) => {
  const [messages, setMessages] = useState<Message[]>([
    {
      id: 'init',
      role: 'assistant',
      content: 'Local Core Online. How can I assist you today?',
      timestamp: Date.now(),
      modelUsed: 'Mistral-7B',
      domain: 'general'
    }
  ]);
  const [input, setInput] = useState('');
  const [isThinking, setIsThinking] = useState(false);
  const [routerState, setRouterState] = useState<RouterDecision | null>(null);
  const messagesEndRef = useRef<HTMLDivElement>(null);

  const scrollToBottom = () => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  };

  useEffect(() => {
    scrollToBottom();
  }, [messages, routerState]);

  useEffect(() => {
      if (initialQuery) {
          setInput(initialQuery);
          // Auto submit logic if desired, or just pre-fill
          // handleSubmit(new Event('submit') as any); 
          // For now just prefill
          if (clearInitialQuery) clearInitialQuery();
      }
  }, [initialQuery]);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!input.trim() || isThinking) return;

    const userMsg: Message = {
      id: Date.now().toString(),
      role: 'user',
      content: input,
      timestamp: Date.now()
    };

    setMessages(prev => [...prev, userMsg]);
    setInput('');
    setIsThinking(true);
    setRouterState(null);

    try {
      const stream = air4.streamChat([...messages, userMsg]);
      
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

  return (
    <div className="flex flex-col h-full relative">
      {/* Header */}
      <div className="h-16 flex items-center justify-between px-6 border-b border-white/5 bg-white/[0.02]">
        <div className="flex items-center gap-2">
            <span className="text-sm font-medium text-slate-200">Neural Link</span>
            <span className="text-xs text-slate-500 bg-white/5 px-2 py-0.5 rounded-full">{messages.length} msgs</span>
        </div>
        <div className="flex items-center gap-3">
          {routerState && (
             <div className="flex items-center gap-2 px-3 py-1 rounded-full bg-air-500/10 border border-air-500/20 text-[10px] text-air-400 font-mono">
                <Cpu className="w-3 h-3" />
                {routerState.model}
             </div>
          )}
        </div>
      </div>

      {/* Messages Area */}
      <div className="flex-1 overflow-y-auto p-4 md:p-8 space-y-6 custom-scrollbar">
        {messages.map((msg) => (
          <div key={msg.id} className={`flex flex-col ${msg.role === 'user' ? 'items-end' : 'items-start'}`}>
            
            {/* Metadata (Avatar name) */}
            <div className="text-[10px] text-slate-500 mb-1 px-1">
                {msg.role === 'user' ? 'You' : 'AIr4'}
            </div>

            {/* Bubble */}
            <div className={`max-w-[85%] md:max-w-[70%] p-4 rounded-2xl text-sm leading-relaxed whitespace-pre-wrap relative shadow-sm ${
                msg.role === 'user' 
                  ? 'bg-air-600 text-white rounded-br-sm' 
                  : 'glass-card text-slate-200 rounded-bl-sm border-white/5'
            }`}>
                
                {/* RAG Context */}
                {msg.role === 'assistant' && msg.contextUsed && msg.contextUsed.length > 0 && (
                    <div className="mb-3 flex flex-col gap-1 pb-3 border-b border-white/5">
                        <div className="flex items-center gap-1 text-[10px] font-bold text-air-400 uppercase tracking-wider">
                            <BrainCircuit className="w-3 h-3" /> Used Context
                        </div>
                        {msg.contextUsed.map((m, idx) => (
                            <div key={idx} className="text-[10px] text-slate-400 truncate bg-white/5 px-2 py-1 rounded">
                                {m.content}
                            </div>
                        ))}
                    </div>
                )}
                
                {msg.content}
            </div>
          </div>
        ))}

        {isThinking && (
           <div className="flex justify-start">
             <div className="glass-card px-4 py-3 rounded-2xl rounded-bl-sm flex items-center gap-3">
                <div className="flex gap-1">
                    <span className="w-1.5 h-1.5 bg-air-500 rounded-full animate-bounce"></span>
                    <span className="w-1.5 h-1.5 bg-air-500 rounded-full animate-bounce delay-75"></span>
                    <span className="w-1.5 h-1.5 bg-air-500 rounded-full animate-bounce delay-150"></span>
                </div>
                <span className="text-xs text-slate-500 font-mono">Thinking...</span>
             </div>
           </div>
        )}
        <div ref={messagesEndRef} />
      </div>

      {/* Input Area */}
      <div className="p-4 md:p-6 bg-gradient-to-t from-obsidian-950/80 to-transparent">
        <form onSubmit={handleSubmit} className="max-w-4xl mx-auto glass-input rounded-2xl p-2 flex items-end gap-2 shadow-2xl">
          <button type="button" className="p-3 text-slate-400 hover:text-white hover:bg-white/10 rounded-xl transition-colors">
              <Paperclip className="w-5 h-5" />
          </button>
          
          <div className="flex-1 py-3">
            <input
                type="text"
                value={input}
                onChange={(e) => setInput(e.target.value)}
                placeholder="Ask anything..."
                className="w-full bg-transparent border-none outline-none text-white placeholder-slate-500 resize-none max-h-32"
            />
          </div>
          
          <button 
            type="submit" 
            disabled={!input.trim()}
            className="p-3 bg-air-600 text-white rounded-xl hover:bg-air-500 transition-all disabled:opacity-50 disabled:cursor-not-allowed shadow-lg shadow-air-600/20"
          >
              <Send className="w-5 h-5" />
          </button>
        </form>
        <div className="text-center mt-3 text-[10px] text-slate-600">
            AI can make mistakes. Verify important information.
        </div>
      </div>
    </div>
  );
};

export default Chat;