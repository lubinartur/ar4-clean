import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';
import path from 'path';

export default defineConfig({
  plugins: [react()],
  base: './',
  server: {
    proxy: {
      "/qb": "http://127.0.0.1:8000",
      "/chat": "http://127.0.0.1:8000",
      "/sessions": "http://127.0.0.1:8000",
    },
  },
  resolve: {
    alias: {
      '@': path.resolve(__dirname, './src'),
    },
  },
});
