import React, { useState, useEffect } from 'react';
import Sidebar from './components/Sidebar';
import Welcome from './pages/Welcome';
import Chat from './pages/Chat';
import Dashboard from './pages/Dashboard';
import Memory from './pages/Memory';
import Ingest from './pages/Ingest';
import { air4 } from './services/air4Service';

const App: React.FC = () => {
  const [isSetup, setIsSetup] = useState(false);
  const [activeTab, setActiveTab] = useState('dashboard');
  const [initialQuery, setInitialQuery] = useState('');

  useEffect(() => {
    // Check persistent setup state
    setIsSetup(air4.isSetupComplete());
  }, []);

  const handleDashboardQuery = (query: string) => {
      setInitialQuery(query);
      setActiveTab('chat');
  };

  const renderContent = () => {
    switch (activeTab) {
      case 'dashboard': return <Dashboard onNavigate={setActiveTab} onQuery={handleDashboardQuery} />;
      case 'chat': return <Chat initialQuery={initialQuery} clearInitialQuery={() => setInitialQuery('')} />;
      case 'ingest': return <Ingest />;
      case 'memory': return <Memory />;
      case 'settings': return <div className="p-10 text-slate-400 glass-card m-10 rounded-2xl h-full">Settings configuration is locked in demo mode.</div>;
      default: return <Dashboard onNavigate={setActiveTab} />;
    }
  };

  if (!isSetup) {
    return <Welcome onComplete={() => setIsSetup(true)} />;
  }

  return (
    <div className="flex h-screen w-full text-slate-200 font-sans p-4 gap-4">
      <Sidebar activeTab={activeTab} onTabChange={setActiveTab} />
      <main className="flex-1 h-full relative glass-panel rounded-[2rem] overflow-hidden shadow-2xl">
        {renderContent()}
      </main>
    </div>
  );
};

export default App;