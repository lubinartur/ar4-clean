import React, { useState, useEffect } from 'react';
import Sidebar from './components/Sidebar';
import Welcome from './pages/Welcome';
import Chat from './pages/Chat';
import Dashboard from './pages/Dashboard';
import Memory from './pages/Memory';
import Ingest from './pages/Ingest';
import History from './pages/History';
import Settings from './pages/Settings';
import { air4 } from './services/air4Service';

type TabId = 'dashboard' | 'chat' | 'memory' | 'ingest' | 'history' | 'settings';

const App: React.FC = () => {
  const [isSetup, setIsSetup] = useState(false);
  const [activeTab, setActiveTab] = useState<TabId>('dashboard');
  const [initialQuery, setInitialQuery] = useState('');
  const [activeSessionId, setActiveSessionId] = useState<string | null>(null);
  const [debugLogs, setDebugLogs] = useState<any[]>([]);

  useEffect(() => {
    setIsSetup(air4.isSetupComplete());

    // Защита: сохраняем session param из URL при старте
    const urlParams = new URLSearchParams(window.location.search);
    const urlSessionId = urlParams.get('session');
    if (urlSessionId) {
      console.debug('[App.tsx] Found session in URL on mount, preserving:', urlSessionId);
      // Если в URL есть session - используем его
      setActiveSessionId(urlSessionId);
    } else {
      // если сессии уже есть — выбираем первую как активную
      const sessions = air4.getSessions();
      if (sessions.length > 0 && !activeSessionId) {
        const firstSessionId = sessions[0].id;
        setActiveSessionId(firstSessionId);
        // Сохраняем session в URL с сохранением всех существующих query params
        const url = new URL(window.location.href);
        url.searchParams.set('session', firstSessionId);
        // ВАЖНО: сохраняем текущий search перед replaceState
        const currentSearch = window.location.search;
        window.history.replaceState({}, '', url.toString());
        console.debug('[App.tsx] Set first session to URL:', firstSessionId, 'preserved search:', currentSearch);
      }
    }
  }, []);

  // HREF watcher: отслеживает изменения window.location.href
  useEffect(() => {
    let last = window.location.href;
    const t = setInterval(() => {
      const cur = window.location.href;
      if (cur !== last) {
        (window as any).__urlDebug?.push({ t: Date.now(), type: 'HREF_CHANGE', href: cur, from: last });
        last = cur;
      }
    }, 200);
    return () => clearInterval(t);
  }, []);

  // Debug panel: автообновление логов
  useEffect(() => {
    const updateLogs = () => {
      const logs = (window as any).__urlDebug || [];
      setDebugLogs(logs.slice(-25)); // Последние 25 записей
    };
    
    updateLogs();
    const interval = setInterval(updateLogs, 500);
    return () => clearInterval(interval);
  }, []);

const handleDashboardQuery = (query: string) => {
    setInitialQuery(query);
    setActiveTab('chat');
  };

  const handleBrainstorm = (query: string) => {
    // создаём отдельную сессию под брейншторм
    const session = air4.createSession('Brainstorm');
    setActiveSessionId(session.id);
    setInitialQuery(query);
    setActiveTab('chat');
  };

  const clearInitialQuery = () => setInitialQuery('');

  const renderContent = () => {
    switch (activeTab) {
      case 'dashboard':
        return (
          <Dashboard
            onNavigate={(tab) => setActiveTab(tab as TabId)}
            onQuery={handleDashboardQuery}
            onBrainstorm={handleBrainstorm}
          />
        );
      case 'chat':
        return (
          <Chat
            sessionId={activeSessionId}
            initialQuery={initialQuery}
            clearInitialQuery={clearInitialQuery}
          />
        );
      case 'memory':
        return <Memory />;
      case 'ingest':
        return <Ingest />;
      case 'history':
        return <History />;
      case 'settings':
        return <Settings />;
      default:
        return (
          <Dashboard
            onNavigate={(tab) => setActiveTab(tab as TabId)}
            onQuery={handleDashboardQuery}
            onBrainstorm={handleBrainstorm}
          />
        );
    }
  };

  // Проверка query параметра setup=1 для форсирования Welcome
  const forceSetup = new URLSearchParams(window.location.search).get('setup') === '1';
  
  // Если forceSetup === true → всегда рендерить Welcome
  if (forceSetup) {
    return <Welcome onComplete={() => {
      setIsSetup(true);
      // После завершения setup параметр будет очищен в Welcome.handleFinish
      window.location.href = '/';
    }} />;
  }
  
  if (false && !isSetup) {
    return <Welcome onComplete={() => setIsSetup(true)} />;
  }

  return (
    <div className="flex h-screen w-full text-slate-200 font-sans p-4 gap-4">
      <Sidebar
        activeTab={activeTab}
        onTabChange={(tab) => setActiveTab(tab as TabId)}
        currentSessionId={activeSessionId}
        onSessionChange={(id: string) => {
          setActiveSessionId(id);
          setActiveTab('chat');
        }}
      />
      <main className="flex-1 h-full relative glass-panel rounded-[2rem] overflow-hidden shadow-2xl">
        {renderContent()}
      </main>
      
      {/* Debug Panel */}
      <div style={{
        position: 'fixed',
        bottom: '12px',
        right: '12px',
        width: '420px',
        maxHeight: '420px',
        background: 'rgba(0,0,0,0.85)',
        border: '1px solid rgba(255,255,255,0.15)',
        color: '#fff',
        zIndex: 99999,
        fontFamily: 'monospace',
        fontSize: '11px',
        overflow: 'auto',
        padding: '10px',
        borderRadius: '12px'
      }}>
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '8px', paddingBottom: '8px', borderBottom: '1px solid rgba(255,255,255,0.15)' }}>
          <span style={{ fontWeight: 'bold', color: '#f97316' }}>URL Debug</span>
          <div style={{ display: 'flex', gap: '6px' }}>
            <button
              onClick={() => {
                (window as any).__testHistory?.();
              }}
              style={{
                padding: '4px 8px',
                background: '#ea580c',
                color: '#fff',
                border: 'none',
                borderRadius: '4px',
                cursor: 'pointer',
                fontSize: '10px'
              }}
            >
              Run __testHistory
            </button>
            <button
              onClick={() => {
                (window as any).__urlDebug = [];
                setDebugLogs([]);
              }}
              style={{
                padding: '4px 8px',
                background: '#64748b',
                color: '#fff',
                border: 'none',
                borderRadius: '4px',
                cursor: 'pointer',
                fontSize: '10px'
              }}
            >
              Clear
            </button>
          </div>
        </div>
        <div style={{ display: 'flex', flexDirection: 'column', gap: '4px' }}>
          {debugLogs.map((log, idx) => (
            <div key={idx} style={{ padding: '6px', background: 'rgba(255,255,255,0.05)', borderRadius: '4px', border: '1px solid rgba(255,255,255,0.1)' }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: '8px', marginBottom: '4px' }}>
                <span style={{
                  padding: '2px 6px',
                  borderRadius: '3px',
                  fontSize: '9px',
                  fontWeight: 'bold',
                  background: log.type === 'BOOT' ? 'rgba(59, 130, 246, 0.3)' :
                              log.type === 'pushState' ? 'rgba(34, 197, 94, 0.3)' :
                              log.type === 'replaceState' ? 'rgba(234, 179, 8, 0.3)' :
                              log.type === 'HREF_CHANGE' ? 'rgba(239, 68, 68, 0.3)' :
                              log.type === 'TEST_DONE' ? 'rgba(168, 85, 247, 0.3)' :
                              'rgba(100, 116, 139, 0.3)',
                  color: log.type === 'BOOT' ? '#93c5fd' :
                         log.type === 'pushState' ? '#86efac' :
                         log.type === 'replaceState' ? '#fde047' :
                         log.type === 'HREF_CHANGE' ? '#fca5a5' :
                         log.type === 'TEST_DONE' ? '#c4b5fd' :
                         '#cbd5e1'
                }}>
                  {log.type}
                </span>
                <span style={{ color: '#94a3b8', fontSize: '9px' }}>
                  {new Date(log.t).toLocaleTimeString()}
                </span>
              </div>
              {log.type === 'HREF_CHANGE' ? (
                <div style={{ color: '#e2e8f0', wordBreak: 'break-all', fontSize: '10px' }}>
                  {log.from} → {log.href}
                </div>
              ) : (
                <div style={{ color: '#e2e8f0', wordBreak: 'break-all', fontSize: '10px' }}>
                  {log.href}
                </div>
              )}
              {log.args && log.args.length > 0 && (
                <div style={{ color: '#94a3b8', fontSize: '9px', marginTop: '4px' }}>
                  args: {JSON.stringify(log.args).slice(0, 100)}
                </div>
              )}
            </div>
          ))}
        </div>
      </div>
    </div>
  );
};

export default App;
