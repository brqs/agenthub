import { defineConfig } from 'vitest/config';
import react from '@vitejs/plugin-react';
import path from 'node:path';

export default defineConfig({
  plugins: [react()],
  resolve: {
    alias: {
      '@': path.resolve(__dirname, './src'),
    },
  },
  server: {
    port: 5173,
    proxy: {
      // /api 代理到后端；可用 VITE_DEV_PROXY_TARGET 覆盖（默认指向远端 demo 后端）
      '/api': {
        target: process.env.VITE_DEV_PROXY_TARGET || 'http://111.229.151.159:8000',
        changeOrigin: true,
      },
    },
  },
  test: {
    environment: 'jsdom',
    setupFiles: ['./src/test-setup.ts'],
    globals: true,
  },
});
