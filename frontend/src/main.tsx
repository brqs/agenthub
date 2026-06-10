import React from 'react';
import ReactDOM from 'react-dom/client';
import { QueryClientProvider } from '@tanstack/react-query';
import { AppRouter } from './AppRouter';
import { initializeShell } from '@/lib/nativeShell';
import { registerPwa } from '@/lib/pwa';
import { queryClient } from '@/lib/queryClient';
import 'katex/dist/katex.min.css';
import './styles/globals.css';

registerPwa();
initializeShell();

ReactDOM.createRoot(document.getElementById('root')!).render(
  <React.StrictMode>
    <QueryClientProvider client={queryClient}>
      <AppRouter />
    </QueryClientProvider>
  </React.StrictMode>,
);
