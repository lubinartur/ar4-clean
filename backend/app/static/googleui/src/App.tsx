
import React, { useState, useEffect } from 'react';
import Sidebar from './components/Sidebar';
import Welcome from './pages/Welcome';
import Chat from './pages/Chat';
import Dashboard from './pages/Dashboard';
import Memory from './pages/Memory';
import Ingest from './pages/Ingest';
import Settings from './pages/Settings';
import HistoryPage from './pages/History';
import { air4 } from './services/air4Service';

const App: React.FC = () => {
  const [isSetup, setIsSetup] = useState(false);
  const [activeTab, setActiveTab] = useState('dashboard');
  const [initialQuery, setInitialQuery] = useState('');
  const [currentSessionId, setCurrentSessionId] = useState<string | null>(null);

  useEffect(() => {
    // Check persistent setup state
    setIsSetup(air4.isSetupComplete());
    
    // Load initial session if exists
    const sessions = air4.getSessions();
    if (sessions.length > 0) {
        setCurrentSessionId(sessions[0].id);
    } else {
        // Create default session if none
        const newSession = air4.createSession();
        setCurrentSessionId(newSession.id);
    }
  }, []);

  const handleDashboardQuery = (query: string) => {
      setInitialQuery(query);
      setActiveTab('chat');
      
      // If no session active, create one
      if (!currentSessionId) {
          const newSess = air4.createSession();
          setCurrentSessionId(newSess.id);
      }
  };

  const handleSessionChange = (id: string) => {
      setCurrentSessionId(id);
  };

  const renderContent = () => {
    switch (activeTab) {
      case 'dashboard': return <Dashboard onNavigate={setActiveTab} onQuery={handleDashboardQuery} />;
      case 'chat': return <Chat sessionId={currentSessionId} initialQuery={initialQuery} clearInitialQuery={() => setInitialQuery('')} />;
      case 'ingest': return <Ingest />;
      case 'memory': return <Memory />;
      case 'history': return <HistoryPage onSelectSession={(id) => { setCurrentSessionId(id); setActiveTab('chat'); }} />;
      case 'settings': return <Settings />;
      default: return <Dashboard onNavigate={setActiveTab} />;
    }
  };

  if (!isSetup) {
    return <Welcome onComplete={() => setIsSetup(true)} />;
  }

  return (
    <div className="flex h-screen w-full text-slate-200 font-sans p-4 gap-4">
      <Sidebar 
        activeTab={activeTab} 
        onTabChange={setActiveTab} 
        currentSessionId={currentSessionId}
        onSessionChange={handleSessionChange}
      />
      <main className="flex-1 h-full relative glass-panel rounded-[2rem] overflow-hidden shadow-2xl">
        {renderContent()}
      </main>
    </div>
  );
};

export default App;
