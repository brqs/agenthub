import { type ReactNode, useCallback, useEffect, useRef, useState } from 'react';
import { useDesktopEnvironment } from '@/hooks/useDesktopEnvironment';
import { isLocalBackendUrl } from '@/lib/desktopBridge';
import { DesktopStartupScreen } from './DesktopStartupScreen';

export function DesktopBootstrapGate({ children }: { children: ReactNode }) {
  const desktop = useDesktopEnvironment();
  const {
    isDesktop,
    backendUrl,
    health,
    checkState,
    preferences,
    stackStatus,
    stackProgress,
    desktopError,
    operationPending,
    setBackendUrl,
    checkBackend,
    refreshLocalStack,
    chooseProjectRoot,
    startLocalStack,
  } = desktop;
  const [bootstrapped, setBootstrapped] = useState(!isDesktop);
  const autoStartAttempted = useRef(false);
  const localMode = isLocalBackendUrl(backendUrl);

  const runCheck = useCallback(
    async (signal?: AbortSignal) => {
      const result = await checkBackend(undefined, signal);
      if (result.status === 'ready') {
        setBootstrapped(true);
      }
    },
    [checkBackend],
  );

  useEffect(() => {
    if (!isDesktop || bootstrapped) return;
    const ctrl = new AbortController();
    runCheck(ctrl.signal).catch((error) => {
      if (error instanceof DOMException && error.name === 'AbortError') return;
      // checkBackend owns user-visible health state.
    });
    return () => {
      ctrl.abort();
    };
  }, [bootstrapped, isDesktop, runCheck]);

  useEffect(() => {
    if (
      !isDesktop ||
      bootstrapped ||
      !localMode ||
      checkState !== 'unreachable' ||
      !preferences?.autoStartLocalStack ||
      operationPending ||
      autoStartAttempted.current
    ) {
      return;
    }
    autoStartAttempted.current = true;
    startLocalStack()
      .then((started) => {
        if (started) setBootstrapped(true);
      })
      .catch(() => undefined);
  }, [
    bootstrapped,
    checkState,
    isDesktop,
    localMode,
    operationPending,
    preferences?.autoStartLocalStack,
    startLocalStack,
  ]);

  if (!isDesktop || bootstrapped) {
    return <>{children}</>;
  }

  return (
    <DesktopStartupScreen
      backendUrl={backendUrl}
      checkState={checkState}
      health={health}
      stackStatus={stackStatus}
      stackProgress={stackProgress}
      desktopError={desktopError}
      operationPending={operationPending}
      localMode={localMode}
      onBackendUrlChange={setBackendUrl}
      onRetry={() => {
        Promise.all([runCheck(), localMode ? refreshLocalStack() : Promise.resolve(null)]).catch(
          () => undefined,
        );
      }}
      onChooseProjectRoot={() => {
        chooseProjectRoot().catch(() => undefined);
      }}
      onStart={() => {
        if (!window.confirm('启动当前项目目录中的 AgentHub 本地服务？此操作不会删除数据卷。')) {
          return;
        }
        startLocalStack()
          .then((started) => {
            if (started) setBootstrapped(true);
          })
          .catch(() => undefined);
      }}
      onRebuild={() => {
        if (
          !window.confirm(
            '当前缺少 Backend 镜像。确认联网重新构建镜像并启动吗？已有数据库和运行时数据卷不会被删除。',
          )
        ) {
          return;
        }
        startLocalStack(true)
          .then((started) => {
            if (started) setBootstrapped(true);
          })
          .catch(() => undefined);
      }}
    />
  );
}
