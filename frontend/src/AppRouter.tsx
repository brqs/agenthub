import { BrowserRouter, HashRouter } from 'react-router-dom';
import App from './App';
import { DesktopBootstrapGate } from '@/components/desktop/DesktopBootstrapGate';
import { DesktopNativeEventBridge } from '@/components/desktop/DesktopNativeEventBridge';
import { DesktopEnvironmentProvider } from '@/hooks/useDesktopEnvironment';
import { isDesktopRuntime } from '@/lib/desktopBridge';

export function AppRouter() {
  const Router = isDesktopRuntime() ? HashRouter : BrowserRouter;

  return (
    <DesktopEnvironmentProvider>
      <Router>
        <DesktopNativeEventBridge />
        <DesktopBootstrapGate>
          <App />
        </DesktopBootstrapGate>
      </Router>
    </DesktopEnvironmentProvider>
  );
}
