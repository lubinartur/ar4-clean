import React, { useState, useEffect, useMemo } from 'react';
import Sidebar from './components/Sidebar';
import Welcome from './pages/Welcome';
import Chat from './pages/Chat';
import Dashboard from './pages/Dashboard';
import Memory from './pages/Memory';
import Ingest from './pages/Ingest';
import History from './pages/History';
import Settings from './pages/Settings';
import { useSettings } from './hooks/useSettings';
import { Air4Provider, useAir4 } from './contexts/Air4Context';

type TabId = 'dashboard' | 'chat' | 'memory' | 'ingest' | 'history' | 'settings';

const AppContent: React.FC = () => {
  const air4 = useAir4();
  const [activeTab, setActiveTab] = useState<TabId>('dashboard');
  const [initialQuery, setInitialQuery] = useState('');
  const [activeSessionId, setActiveSessionId] = useState<string | null>(null);
  
  // Проверка query параметра setup=1 для форсирования Welcome
  const forceSetup = new URLSearchParams(window.location.search).get('setup') === '1';

  // Startup: force-remove any session URL parameter
  // We do not support deep-linking to sessions before v1.0
  // App always starts with activeSessionId = null
  useEffect(() => {
    const url = new URL(window.location.href);
    if (url.searchParams.has('session')) {
      url.searchParams.delete('session');
      window.history.replaceState({}, '', url.toString());
    }
  }, []); // Запускается только на mount

  // Слушатель изменений URL (браузерная навигация назад/вперёд)
  useEffect(() => {
    const handlePopState = () => {
      const urlSessionId = new URLSearchParams(window.location.search).get('session');
      if (urlSessionId && urlSessionId !== activeSessionId) {
        // Only use URL session ID if it's valid
        if (air4.isValidSessionId(urlSessionId)) {
          setActiveSessionId(urlSessionId);
        } else {
          console.debug('[App] Invalid session ID in popstate, ignoring:', urlSessionId);
          
          // Clean up invalid session ID from URL
          const url = new URL(window.location.href);
          url.searchParams.delete('session');
          window.history.replaceState({}, '', url.toString());
          
          // Also check and remove from localStorage
          const STORAGE_KEY_ACTIVE_SESSION = 'air4.activeSessionId';
          const storedSessionId = localStorage.getItem(STORAGE_KEY_ACTIVE_SESSION);
          if (storedSessionId === urlSessionId) {
            localStorage.removeItem(STORAGE_KEY_ACTIVE_SESSION);
          }
        }
      }
    };
    window.addEventListener('popstate', handlePopState);
    return () => window.removeEventListener('popstate', handlePopState);
  }, [activeSessionId, air4]);

  // Синхронизация activeSessionId с URL
  useEffect(() => {
    const url = new URL(window.location.href);
    const urlSessionId = url.searchParams.get('session');
    
    if (activeSessionId) {
      // Only set URL param if session ID is valid
      if (air4.isValidSessionId(activeSessionId)) {
        url.searchParams.set('session', activeSessionId);
        window.history.replaceState({}, '', url.toString());
      }
    } else {
      // If no active session, remove session param from URL
      if (urlSessionId) {
        url.searchParams.delete('session');
        window.history.replaceState({}, '', url.toString());
      }
    }
  }, [activeSessionId, air4]);

  const handleDashboardQuery = (query: string) => {
    setInitialQuery(query);
    setActiveTab('chat');
  };

  const handleBrainstorm = async (query: string) => {
    // создаём отдельную сессию под брейншторм
    try {
      const session = await air4.createSession('Brainstorm');
      setActiveSessionId(session.id);
      setInitialQuery(query);
      setActiveTab('chat');
    } catch (err) {
      console.error('[App] handleBrainstorm error:', err);
    }
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
            onSessionChange={(id: string) => {
              // Guard: only set activeSessionId if it's a valid backend session ID
              if (air4.isValidSessionId(id)) {
                setActiveSessionId(id);
              } else {
                console.debug('[App] Invalid session ID from Chat, ignoring:', id);
                
                // Clean up invalid session ID from sources
                const url = new URL(window.location.href);
                const urlSessionId = url.searchParams.get('session');
                if (urlSessionId === id) {
                  url.searchParams.delete('session');
                  window.history.replaceState({}, '', url.toString());
                }
                
                const STORAGE_KEY_ACTIVE_SESSION = 'air4.activeSessionId';
                const storedSessionId = localStorage.getItem(STORAGE_KEY_ACTIVE_SESSION);
                if (storedSessionId === id) {
                  localStorage.removeItem(STORAGE_KEY_ACTIVE_SESSION);
                }
              }
            }}
          />
        );
      case 'memory':
        return <Memory activeSessionId={activeSessionId} />;
      case 'ingest':
        return <Ingest />;
      case 'history':
        return (
          <History
            onSelectSession={(id: string) => {
              // Guard: only set activeSessionId if it's a valid backend session ID
              if (air4.isValidSessionId(id)) {
                setActiveSessionId(id);
                setActiveTab('chat');
              } else {
                console.debug('[App] Invalid session ID from History, ignoring:', id);
                
                // Clean up invalid session ID from sources
                const url = new URL(window.location.href);
                const urlSessionId = url.searchParams.get('session');
                if (urlSessionId === id) {
                  url.searchParams.delete('session');
                  window.history.replaceState({}, '', url.toString());
                }
                
                const STORAGE_KEY_ACTIVE_SESSION = 'air4.activeSessionId';
                const storedSessionId = localStorage.getItem(STORAGE_KEY_ACTIVE_SESSION);
                if (storedSessionId === id) {
                  localStorage.removeItem(STORAGE_KEY_ACTIVE_SESSION);
                }
              }
            }}
          />
        );
      case 'settings':
        return <Settings activeSessionId={activeSessionId} />;
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

  // Если forceSetup === true → всегда рендерить Welcome
  if (forceSetup) {
    return <Welcome onComplete={() => {
      // После завершения setup параметр будет очищен в Welcome.handleFinish
      window.location.href = '/';
    }} />;
  }

  return (
    <>
      <div className="flex h-screen w-full text-slate-200 font-sans p-4 gap-4">
        <Sidebar
          activeTab={activeTab}
          onTabChange={(tab) => setActiveTab(tab as TabId)}
          currentSessionId={activeSessionId}
          onSessionChange={(id: string) => {
            // Guard: only set activeSessionId if it's a valid backend session ID
            if (air4.isValidSessionId(id)) {
              setActiveSessionId(id);
              setActiveTab('chat');
            } else {
              console.debug('[App] Invalid session ID from Sidebar, ignoring:', id);
              
              // Clean up invalid session ID from sources
              // 1. Check and remove from URL query param
              const url = new URL(window.location.href);
              const urlSessionId = url.searchParams.get('session');
              if (urlSessionId === id) {
                url.searchParams.delete('session');
                window.history.replaceState({}, '', url.toString());
              }
              
              // 2. Check and remove from localStorage
              const STORAGE_KEY_ACTIVE_SESSION = 'air4.activeSessionId';
              const storedSessionId = localStorage.getItem(STORAGE_KEY_ACTIVE_SESSION);
              if (storedSessionId === id) {
                localStorage.removeItem(STORAGE_KEY_ACTIVE_SESSION);
              }
            }
          }}
        />
        <main className="flex-1 h-full relative glass-panel rounded-[2rem] overflow-hidden shadow-2xl">
          {renderContent()}
        </main>
      </div>
    </>
  );
};

const App: React.FC = () => {
  const { settings } = useSettings();
  const apiBaseUrl = useMemo(() => settings.apiBaseUrl, [settings.apiBaseUrl]);

  return (
    <Air4Provider apiBaseUrl={apiBaseUrl}>
      <AppContent />
    </Air4Provider>
  );
};

export default App;
