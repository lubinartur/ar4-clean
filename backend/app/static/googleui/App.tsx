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

  useEffect(() => {
    setIsSetup(air4.isSetupComplete());

    // если сессии уже есть — выбираем первую как активную
    const sessions = air4.getSessions();
    if (sessions.length > 0 && !activeSessionId) {
      setActiveSessionId(sessions[0].id);
    }
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
    </div>
  );
};

export default App;
