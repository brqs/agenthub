import React from 'react';
import ReactDOM from 'react-dom/client';
import { BrowserRouter } from 'react-router-dom';
import { QueryClientProvider } from '@tanstack/react-query';
import App from './App';
import { initializeNativeShell } from '@/lib/nativeShell';
import { registerPwa } from '@/lib/pwa';
import { queryClient } from '@/lib/queryClient';
import 'katex/dist/katex.min.css';
import './styles/globals.css';

registerPwa();
initializeNativeShell();

ReactDOM.createRoot(document.getElementById('root')!).render(
  <React.StrictMode>
    <QueryClientProvider client={queryClient}>
      <BrowserRouter>
        <App />
      </BrowserRouter>
    </QueryClientProvider>
  </React.StrictMode>,
);
