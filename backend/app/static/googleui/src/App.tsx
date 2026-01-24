import React, { useState, useEffect, useMemo, useRef, useCallback } from 'react';
import Sidebar from './components/Sidebar';
import Welcome from './pages/Welcome';
import Chat from './pages/Chat';
import Dashboard from './pages/Dashboard';
import Memory from './pages/Memory';
import Ingest from './pages/Ingest';
import History from './pages/History';
import Settings from './pages/Settings';
import { useSettings } from './hooks/useSettings';
import { useAir4 } from './contexts/Air4Context';
import ErrorBoundary from './components/ErrorBoundary';  // P2.2: Error boundary

type TabId = 'dashboard' | 'chat' | 'memory' | 'ingest' | 'history' | 'settings';

const AppContent: React.FC = () => {
  const air4 = useAir4();
  const [activeTab, setActiveTab] = useState<TabId>('dashboard');
  const [initialQuery, setInitialQuery] = useState('');
  const [activeSessionId, setActiveSessionId] = useState<string | null>(null);
  const [selectedConversationId, setSelectedConversationId] = useState<string | null>(null);
  const [historyLoaded, setHistoryLoaded] = useState(false);
  const [forceReloadTick, setForceReloadTick] = useState(0);
  const [userSelectTick, setUserSelectTick] = useState(0);
  const [sessionOpenTick, setSessionOpenTick] = useState(0);
  
  // Track if session change was initiated by user action (vs auto-restore)
  const userInitiatedSessionChangeRef = useRef(false);
  
  // Store openSession callback from Chat component
  const openSessionRef = useRef<((sid: string) => Promise<void>) | null>(null);
  
  // Force open session handler (always triggers reload)
  const handleForceOpenSession = (id: string) => {
    setActiveSessionId(id); // на всякий
    setSessionOpenTick(t => t + 1);
  };
  
  // Проверка query параметра setup=1 для форсирования Welcome
  const forceSetup = new URLSearchParams(window.location.search).get('setup') === '1';

  // Optional: Strip ?session from URL on Home (dashboard)
  useEffect(() => {
    if (activeTab !== 'chat' && window.location.search.includes('session=')) {
      const url = new URL(window.location.href);
      url.searchParams.delete('session');
      window.history.replaceState({}, '', url.toString());
    }
  }, [activeTab]);

  // Startup: restore activeSessionId from localStorage AFTER history is loaded (single-shot)
  const restoredOnceRef = useRef(false);
  useEffect(() => {
    if (!historyLoaded || restoredOnceRef.current) {
      return;
    }
    
    restoredOnceRef.current = true; // Mark as restored
    
    const STORAGE_KEY_ACTIVE_SESSION = 'air4_active_session_id';
    try {
      const restoredSessionId = localStorage.getItem(STORAGE_KEY_ACTIVE_SESSION);
      
      if (restoredSessionId && air4.isValidSessionId(restoredSessionId)) {
        // Check if session still exists in history (now history is loaded)
        const sessions = air4.getSessions();
        const sessionExists = sessions.some(s => s.id === restoredSessionId);
        if (sessionExists) {
          setActiveSessionId(restoredSessionId);
        } else {
          // Session doesn't exist anymore, remove from localStorage
          localStorage.removeItem(STORAGE_KEY_ACTIVE_SESSION);
        }
      }
      
      // Clean URL after restore (variant A: clean URL)
      if (window.location.search.includes('session=')) {
        window.history.replaceState({}, '', window.location.pathname);
      }
    } catch (err) {
      console.error('[App] Failed to restore activeSessionId:', err);
    }
  }, [air4, historyLoaded]);

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
          const STORAGE_KEY_ACTIVE_SESSION = 'air4_active_session_id';
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

  // C2.3: Listen for navigate-to-memory event from Chat context actions
  useEffect(() => {
    const handleNavigateToMemory = (event: CustomEvent) => {
      const params = event.detail;
      if (params && params.session_id) {
        // Validate session ID
        if (air4.isValidSessionId(params.session_id)) {
          setActiveSessionId(params.session_id);
          const STORAGE_KEY_ACTIVE_SESSION = 'air4_active_session_id';
          localStorage.setItem(STORAGE_KEY_ACTIVE_SESSION, params.session_id);
        }
        // Switch to memory tab (params will be read by Memory component)
        setActiveTab('memory');
      }
    };
    window.addEventListener('air4:navigate-to-memory', handleNavigateToMemory as EventListener);
    return () => window.removeEventListener('air4:navigate-to-memory', handleNavigateToMemory as EventListener);
  }, [air4]);

  // URL behavior: Clean URL (variant A) - no persistent ?session= param
  // ?session= is only used for restore at startup, then cleaned
  // User-initiated session changes do NOT update URL (clean URL policy)

  const handleDashboardQuery = (query: string) => {
    setInitialQuery(query);
    setActiveTab('chat');
  };

  const handleBrainstorm = async (query: string) => {
    // B4 lifecycle: создаём отдельную сессию под брейншторм via POST /sessions/new
    try {
      const session = await air4.createSession('Brainstorm');
      const sessionId = session.id;
      // Mark as user-initiated (from Brainstorm action)
      userInitiatedSessionChangeRef.current = true;
      setActiveSessionId(sessionId);
      const STORAGE_KEY_ACTIVE_SESSION = 'air4_active_session_id';
      localStorage.setItem(STORAGE_KEY_ACTIVE_SESSION, sessionId);
      setInitialQuery(query);
      setActiveTab('chat');
    } catch (err) {
      console.error('[App] handleBrainstorm error:', err);
    }
  };

  const clearInitialQuery = () => setInitialQuery('');

  // P2.2: Go home handler for ErrorBoundary - navigate to safe workspace
  const handleGoHome = useCallback(() => {
    setActiveTab('dashboard');
  }, []);

  const renderContent = () => {
    switch (activeTab) {
      case 'dashboard':
        return (
          <ErrorBoundary onGoHome={handleGoHome} workspaceName="Dashboard">
            <Dashboard
              onNavigate={(tab) => setActiveTab(tab as TabId)}
              onQuery={handleDashboardQuery}
              onBrainstorm={handleBrainstorm}
            />
          </ErrorBoundary>
        );
      case 'chat':
        return (
          <ErrorBoundary onGoHome={handleGoHome} workspaceName="Think">
            <Chat
              sessionId={activeSessionId}
              initialQuery={initialQuery}
              clearInitialQuery={clearInitialQuery}
              forceReloadTick={forceReloadTick}
              userSelectTick={userSelectTick}
              historyLoaded={historyLoaded}
              sessionOpenTick={sessionOpenTick}
              onOpenSessionReady={(openSession) => {
                openSessionRef.current = openSession;
              }}
              onSessionChange={(id: string) => {
                // Guard: only set activeSessionId if it's a valid backend session ID
                if (air4.isValidSessionId(id)) {
                  setActiveSessionId(id);
                  // Save to localStorage for restore after reload
                  const STORAGE_KEY_ACTIVE_SESSION = 'air4_active_session_id';
                  localStorage.setItem(STORAGE_KEY_ACTIVE_SESSION, id);
                  console.debug('[App] Saved activeSessionId to localStorage:', id);
                } else {
                  console.debug('[App] Invalid session ID from Chat, ignoring:', id);
                  
                  // Clean up invalid session ID from sources
                  const url = new URL(window.location.href);
                  const urlSessionId = url.searchParams.get('session');
                  if (urlSessionId === id) {
                    url.searchParams.delete('session');
                    window.history.replaceState({}, '', url.toString());
                  }
                  
                  const STORAGE_KEY_ACTIVE_SESSION = 'air4_active_session_id';
                  const storedSessionId = localStorage.getItem(STORAGE_KEY_ACTIVE_SESSION);
                  if (storedSessionId === id) {
                    localStorage.removeItem(STORAGE_KEY_ACTIVE_SESSION);
                  }
                }
              }}
              selectedConversationId={selectedConversationId}
            onSelectConversation={async (conversationId: string) => {
                setSelectedConversationId(conversationId);
                setActiveTab('chat');
              }}
            />
          </ErrorBoundary>
        );
      case 'memory':
        return (
          <ErrorBoundary onGoHome={handleGoHome} workspaceName="Store">
            <Memory activeSessionId={activeSessionId} />
          </ErrorBoundary>
        );
      case 'ingest':
        return (
          <ErrorBoundary onGoHome={handleGoHome} workspaceName="Ingest">
            <Ingest />
          </ErrorBoundary>
        );
      case 'history':
        return (
          <ErrorBoundary onGoHome={handleGoHome} workspaceName="Recall">
            <History
              onUserSelectSession={() => {
                setUserSelectTick(t => t + 1);
              }}
              onForceOpenSession={handleForceOpenSession}
              onOpenSession={(sid: string) => {
                // Direct load via openSession from Chat
                if (openSessionRef.current) {
                  openSessionRef.current(sid);
                }
              }}
              onSelectSession={(id: string) => {
                // Guard: only set activeSessionId if it's a valid backend session ID
                if (air4.isValidSessionId(id)) {
                  // Mark as user-initiated (from History click)
                  userInitiatedSessionChangeRef.current = true;
                  // Force reload in Chat component
                  setForceReloadTick(t => t + 1);
                  setActiveSessionId(id);
                  const STORAGE_KEY_ACTIVE_SESSION = 'air4_active_session_id';
                  localStorage.setItem(STORAGE_KEY_ACTIVE_SESSION, id);
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
                  
                  const STORAGE_KEY_ACTIVE_SESSION = 'air4_active_session_id';
                  const storedSessionId = localStorage.getItem(STORAGE_KEY_ACTIVE_SESSION);
                  if (storedSessionId === id) {
                    localStorage.removeItem(STORAGE_KEY_ACTIVE_SESSION);
                  }
                }
              }}
            />
          </ErrorBoundary>
        );
      case 'settings':
        return (
          <ErrorBoundary onGoHome={handleGoHome} workspaceName="Settings">
            <Settings activeSessionId={activeSessionId} />
          </ErrorBoundary>
        );
      default:
        return (
          <ErrorBoundary onGoHome={handleGoHome} workspaceName="Dashboard">
            <Dashboard
              onNavigate={(tab) => setActiveTab(tab as TabId)}
              onQuery={handleDashboardQuery}
              onBrainstorm={handleBrainstorm}
            />
          </ErrorBoundary>
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
          onHistoryLoaded={() => {
            setHistoryLoaded(true);
            console.log('[App] History loaded callback received');
          }}
          onSessionChange={(id: string, forceReload: boolean = false) => {
            // Guard: only set activeSessionId if it's a valid backend session ID
            if (air4.isValidSessionId(id)) {
              // Mark as user-initiated (from Sidebar click)
              userInitiatedSessionChangeRef.current = true;
              // Force reload in Chat component ONLY if requested (for existing sessions, not New Chat)
              if (forceReload) {
                setForceReloadTick(t => t + 1);
              }
              setActiveSessionId(id);
              const STORAGE_KEY_ACTIVE_SESSION = 'air4_active_session_id';
              localStorage.setItem(STORAGE_KEY_ACTIVE_SESSION, id);
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
              const STORAGE_KEY_ACTIVE_SESSION = 'air4_active_session_id';
              const storedSessionId = localStorage.getItem(STORAGE_KEY_ACTIVE_SESSION);
              if (storedSessionId === id) {
                localStorage.removeItem(STORAGE_KEY_ACTIVE_SESSION);
              }
            }
          }}
          onSelectConversation={(conversationId: string) => {
            setSelectedConversationId(conversationId);
            setActiveTab('chat');
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
  return <AppContent />;
};

export default App;
