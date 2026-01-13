import React from 'react';
import ReactDOM from 'react-dom/client';
import App from './App';

console.debug('[BOOT] index.tsx loaded', window.location.href);

// Временный перехват для отладки: кто очищает URL
const _rs = history.replaceState;
history.replaceState = function(...args){
  console.debug('[TRACE replaceState args]', args);
  console.debug('[TRACE replaceState stack]', new Error().stack);
  return _rs.apply(this, args as any);
};

const _ps = history.pushState;
history.pushState = function(...args){
  console.debug('[TRACE pushState args]', args);
  console.debug('[TRACE pushState stack]', new Error().stack);
  return _ps.apply(this, args as any);
};

// Тестовая функция для проверки перехвата
(window as any).__testHistory = () => {
  history.pushState({}, '', '/?zzz=1');
  history.replaceState({}, '', '/?zzz=2');
  console.debug('[TEST] after history ops', window.location.href);
};

const rootElement = document.getElementById('root');
if (!rootElement) {
  throw new Error("Could not find root element to mount to");
}

const root = ReactDOM.createRoot(rootElement);
root.render(
  <React.StrictMode>
    <App />
  </React.StrictMode>
);