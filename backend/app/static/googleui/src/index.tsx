import React from 'react';
import ReactDOM from 'react-dom/client';
import App from './App';
import { Air4Provider } from './contexts/Air4Context';
import './global.css';

// B3.1 lifecycle: ensure Air4Provider wraps the whole app to prevent useAir4 crash
const apiBaseUrl = import.meta.env.VITE_API_BASE_URL ?? 'http://127.0.0.1:8000';

const rootElement = document.getElementById('root');
if (!rootElement) {
  throw new Error("Could not find root element to mount to");
}

const root = ReactDOM.createRoot(rootElement);
root.render(
  <React.StrictMode>
    <Air4Provider apiBaseUrl={apiBaseUrl}>
      <App />
    </Air4Provider>
  </React.StrictMode>
);
