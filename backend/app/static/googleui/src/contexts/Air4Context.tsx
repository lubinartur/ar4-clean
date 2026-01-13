import React, { createContext, useContext, useMemo, ReactNode } from 'react';
import { Air4Service, createAir4Service } from '../services/air4Service';

interface Air4ContextValue {
  service: Air4Service;
}

const Air4Context = createContext<Air4ContextValue | null>(null);

interface Air4ProviderProps {
  apiBaseUrl: string;
  children: ReactNode;
}

export function Air4Provider({ apiBaseUrl, children }: Air4ProviderProps) {
  const service = useMemo(() => createAir4Service(apiBaseUrl), [apiBaseUrl]);

  const value = useMemo(() => ({ service }), [service]);

  return (
    <Air4Context.Provider value={value}>
      {children}
    </Air4Context.Provider>
  );
}

export function useAir4(): Air4Service {
  const context = useContext(Air4Context);
  if (!context) {
    throw new Error('useAir4 must be used within Air4Provider');
  }
  return context.service;
}

