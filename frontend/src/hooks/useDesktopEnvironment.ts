import {
  createContext,
  createElement,
  type ReactNode,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useRef,
  useState,
} from 'react';
import {
  checkForDesktopUpdate,
  checkDesktopLocalStack,
  checkDesktopBackendHealth,
  chooseDesktopProjectRoot,
  collectDesktopCrashReport,
  getDesktopEnvironment,
  getDesktopPreferences,
  getDesktopReleaseInfo,
  getStoredDesktopBackendUrl,
  installDesktopUpdate,
  isDesktopRuntime,
  normalizeDesktopError,
  openDesktopReleasePage,
  restartDesktopBackend,
  setDesktopPreferences,
  setStoredDesktopBackendUrl,
  startDesktopLocalStack,
  stopDesktopLocalStack,
  type DesktopBackendHealth,
  type DesktopBridgeError,
  type DesktopCrashReport,
  type DesktopEnvironment,
  type DesktopLocalStackStatus,
  type DesktopPreferences,
  type DesktopPreferencesPatch,
  type DesktopReleaseInfo,
  type DesktopStackProgress,
  type DesktopUpdateCheckResult,
  type DesktopUpdateInstallResult,
} from '@/lib/desktopBridge';
import { getApiBaseUrl, setRuntimeApiBaseUrl, subscribeApiBaseUrl } from '@/lib/env';

export type DesktopCheckState = 'idle' | 'checking' | 'ready' | 'unreachable';
export type DesktopUpdateState =
  | 'idle'
  | 'checking'
  | 'current'
  | 'available'
  | 'installing'
  | 'restart_required'
  | 'error';

export interface DesktopEnvironmentState {
  isDesktop: boolean;
  backendUrl: string;
  runtimeApiBaseUrl: string;
  health: DesktopBackendHealth | null;
  checkState: DesktopCheckState;
  environment: DesktopEnvironment | null;
  preferences: DesktopPreferences | null;
  releaseInfo: DesktopReleaseInfo | null;
  updateCheck: DesktopUpdateCheckResult | null;
  updateState: DesktopUpdateState;
  updateError: DesktopBridgeError | null;
  stackStatus: DesktopLocalStackStatus | null;
  stackProgress: DesktopStackProgress | null;
  desktopError: DesktopBridgeError | null;
  operationPending: boolean;
  setBackendUrl: (url: string) => void;
  checkBackend: (url?: string, signal?: AbortSignal) => Promise<DesktopBackendHealth>;
  refreshLocalStack: () => Promise<DesktopLocalStackStatus | null>;
  chooseProjectRoot: () => Promise<void>;
  startLocalStack: (rebuild?: boolean) => Promise<boolean>;
  stopLocalStack: () => Promise<boolean>;
  restartBackend: () => Promise<boolean>;
  updatePreferences: (patch: DesktopPreferencesPatch) => Promise<void>;
  refreshReleaseInfo: () => Promise<DesktopReleaseInfo | null>;
  checkForUpdate: () => Promise<DesktopUpdateCheckResult | null>;
  installUpdate: () => Promise<DesktopUpdateInstallResult | null>;
  openReleasePage: () => Promise<void>;
  collectCrashReport: () => Promise<DesktopCrashReport | null>;
}

const DesktopEnvironmentContext = createContext<DesktopEnvironmentState | null>(null);

export function DesktopEnvironmentProvider({ children }: { children: ReactNode }) {
  const value = useDesktopEnvironmentState();
  return createElement(DesktopEnvironmentContext.Provider, { value }, children);
}

export function useDesktopEnvironment(): DesktopEnvironmentState {
  const value = useContext(DesktopEnvironmentContext);
  return value ?? createWebDesktopEnvironmentState();
}

function useDesktopEnvironmentState(): DesktopEnvironmentState {
  const desktop = useMemo(() => isDesktopRuntime(), []);
  const [backendUrl, setBackendUrlState] = useState(() =>
    desktop ? getStoredDesktopBackendUrl() : getApiBaseUrl(),
  );
  const [runtimeApiBaseUrl, setRuntimeApiBaseUrlState] = useState(() => getApiBaseUrl());
  const [health, setHealth] = useState<DesktopBackendHealth | null>(null);
  const [checkState, setCheckState] = useState<DesktopCheckState>('idle');
  const [environment, setEnvironment] = useState<DesktopEnvironment | null>(null);
  const [preferences, setPreferencesState] = useState<DesktopPreferences | null>(null);
  const [releaseInfo, setReleaseInfo] = useState<DesktopReleaseInfo | null>(null);
  const [updateCheck, setUpdateCheck] = useState<DesktopUpdateCheckResult | null>(null);
  const [updateState, setUpdateState] = useState<DesktopUpdateState>('idle');
  const [updateError, setUpdateError] = useState<DesktopBridgeError | null>(null);
  const [stackStatus, setStackStatus] = useState<DesktopLocalStackStatus | null>(null);
  const [stackProgress, setStackProgress] = useState<DesktopStackProgress | null>(null);
  const [desktopError, setDesktopError] = useState<DesktopBridgeError | null>(null);
  const [operationPending, setOperationPending] = useState(false);
  const autoUpdateCheckAttempted = useRef(false);

  useEffect(
    () =>
      subscribeApiBaseUrl((url) => {
        setRuntimeApiBaseUrlState(url);
      }),
    [],
  );

  useEffect(() => {
    if (!desktop) return;
    let cancelled = false;
    Promise.all([
      getDesktopEnvironment(),
      getDesktopPreferences(),
      checkDesktopLocalStack(),
      getDesktopReleaseInfo(),
    ])
      .then(([nextEnvironment, nextPreferences, nextStack, nextReleaseInfo]) => {
        if (cancelled) return;
        setEnvironment(nextEnvironment);
        setPreferencesState(nextPreferences);
        setStackStatus(nextStack);
        setReleaseInfo(nextReleaseInfo);
      })
      .catch((error) => {
        if (!cancelled) setDesktopError(normalizeDesktopError(error));
      });
    return () => {
      cancelled = true;
    };
  }, [desktop]);

  const refreshReleaseInfo = useCallback(async () => {
    if (!desktop) return null;
    try {
      const next = await getDesktopReleaseInfo();
      setReleaseInfo(next);
      setUpdateError(null);
      return next;
    } catch (error) {
      setUpdateError(normalizeDesktopError(error));
      return null;
    }
  }, [desktop]);

  const setBackendUrl = useCallback(
    (url: string) => {
      setBackendUrlState(url);
      if (desktop) {
        try {
          setStoredDesktopBackendUrl(url);
        } catch {
          // The user can still retry and see the validation error from health check.
        }
      }
    },
    [desktop],
  );

  const checkBackend = useCallback(
    async (url = backendUrl, signal?: AbortSignal) => {
      setCheckState('checking');
      const result = await checkDesktopBackendHealth(url, signal);
      setHealth(result);
      setCheckState(result.status === 'ready' ? 'ready' : 'unreachable');
      if (result.status === 'ready') {
        setRuntimeApiBaseUrl(result.url, { persistDesktop: desktop });
        setBackendUrlState(result.url);
        if (desktop) {
          try {
            const next = await setDesktopPreferences({ backendUrl: result.url });
            setPreferencesState(next);
          } catch {
            // A healthy backend remains usable even if desktop preferences cannot be persisted.
          }
        }
      }
      return result;
    },
    [backendUrl, desktop],
  );

  const refreshLocalStack = useCallback(async () => {
    if (!desktop) return null;
    try {
      const status = await checkDesktopLocalStack();
      setStackStatus(status);
      setDesktopError(null);
      return status;
    } catch (error) {
      setDesktopError(normalizeDesktopError(error));
      return null;
    }
  }, [desktop]);

  const chooseProjectRoot = useCallback(async () => {
    if (!desktop) return;
    try {
      const binding = await chooseDesktopProjectRoot();
      if (!binding) return;
      const [nextPreferences, nextStack] = await Promise.all([
        getDesktopPreferences(),
        checkDesktopLocalStack(),
      ]);
      setPreferencesState(nextPreferences);
      setStackStatus(nextStack);
      setDesktopError(null);
    } catch (error) {
      setDesktopError(normalizeDesktopError(error));
    }
  }, [desktop]);

  const runStackOperation = useCallback(
    async (
      operation: (
        onProgress: (progress: DesktopStackProgress) => void,
      ) => Promise<{ status: DesktopLocalStackStatus }>,
    ) => {
      if (!desktop || operationPending) return false;
      setOperationPending(true);
      setDesktopError(null);
      setStackProgress(null);
      try {
        const result = await operation(setStackProgress);
        setStackStatus(result.status);
        if (result.status.backendHealth === 'ready') {
          await checkBackend();
        }
        return true;
      } catch (error) {
        const normalized = normalizeDesktopError(error);
        setDesktopError(normalized);
        try {
          setStackStatus(await checkDesktopLocalStack());
        } catch {
          // Keep the operation error as the primary explanation.
        }
        setDesktopError(normalized);
        return false;
      } finally {
        setOperationPending(false);
      }
    },
    [checkBackend, desktop, operationPending],
  );

  const startLocalStack = useCallback(
    (rebuild = false) =>
      runStackOperation((onProgress) => startDesktopLocalStack({ rebuild }, onProgress)),
    [runStackOperation],
  );

  const stopLocalStack = useCallback(
    () => runStackOperation((onProgress) => stopDesktopLocalStack(onProgress)),
    [runStackOperation],
  );

  const restartBackend = useCallback(
    () => runStackOperation((onProgress) => restartDesktopBackend(onProgress)),
    [runStackOperation],
  );

  const updatePreferences = useCallback(
    async (patch: DesktopPreferencesPatch) => {
      if (!desktop) return;
      try {
        const next = await setDesktopPreferences(patch);
        setPreferencesState(next);
        setDesktopError(null);
        if (
          patch.autoCheckUpdates !== undefined ||
          patch.lastUpdateCheckAt !== undefined ||
          patch.updateChannel !== undefined
        ) {
          await refreshReleaseInfo();
        }
      } catch (error) {
        setDesktopError(normalizeDesktopError(error));
      }
    },
    [desktop, refreshReleaseInfo],
  );

  const checkForUpdate = useCallback(async () => {
    if (!desktop) return null;
    setUpdateState('checking');
    setUpdateError(null);
    try {
      const result = await checkForDesktopUpdate();
      setUpdateCheck(result);
      setUpdateState(result.available ? 'available' : 'current');
      setPreferencesState((current) =>
        current ? { ...current, lastUpdateCheckAt: result.checkedAt } : current,
      );
      setReleaseInfo((current) =>
        current ? { ...current, lastUpdateCheckAt: result.checkedAt } : current,
      );
      return result;
    } catch (error) {
      setUpdateError(normalizeDesktopError(error));
      setUpdateState('error');
      return null;
    }
  }, [desktop]);

  const installUpdate = useCallback(async () => {
    if (!desktop) return null;
    setUpdateState('installing');
    setUpdateError(null);
    try {
      const result = await installDesktopUpdate();
      setUpdateState(result.restartRequired ? 'restart_required' : 'current');
      return result;
    } catch (error) {
      setUpdateError(normalizeDesktopError(error));
      setUpdateState('error');
      return null;
    }
  }, [desktop]);

  const openReleasePage = useCallback(async () => {
    if (!desktop) return;
    try {
      await openDesktopReleasePage();
      setUpdateError(null);
    } catch (error) {
      setUpdateError(normalizeDesktopError(error));
    }
  }, [desktop]);

  const collectCrashReport = useCallback(async () => {
    if (!desktop) return null;
    try {
      const result = await collectDesktopCrashReport();
      setUpdateError(null);
      return result;
    } catch (error) {
      setUpdateError(normalizeDesktopError(error));
      return null;
    }
  }, [desktop]);

  useEffect(() => {
    if (
      !desktop ||
      autoUpdateCheckAttempted.current ||
      preferences?.autoCheckUpdates !== true ||
      !releaseInfo
    ) {
      return;
    }
    autoUpdateCheckAttempted.current = true;
    checkForUpdate().catch(() => undefined);
  }, [checkForUpdate, desktop, preferences?.autoCheckUpdates, releaseInfo]);

  return {
    isDesktop: desktop,
    backendUrl,
    runtimeApiBaseUrl,
    health,
    checkState,
    environment,
    preferences,
    releaseInfo,
    updateCheck,
    updateState,
    updateError,
    stackStatus,
    stackProgress,
    desktopError,
    operationPending,
    setBackendUrl,
    checkBackend,
    refreshLocalStack,
    chooseProjectRoot,
    startLocalStack,
    stopLocalStack,
    restartBackend,
    updatePreferences,
    refreshReleaseInfo,
    checkForUpdate,
    installUpdate,
    openReleasePage,
    collectCrashReport,
  };
}

function createWebDesktopEnvironmentState(): DesktopEnvironmentState {
  const backendUrl = getApiBaseUrl();
  return {
    isDesktop: false,
    backendUrl,
    runtimeApiBaseUrl: backendUrl,
    health: null,
    checkState: 'idle',
    environment: null,
    preferences: null,
    releaseInfo: null,
    updateCheck: null,
    updateState: 'idle',
    updateError: null,
    stackStatus: null,
    stackProgress: null,
    desktopError: null,
    operationPending: false,
    setBackendUrl: () => undefined,
    checkBackend: async (url = backendUrl, signal) => checkDesktopBackendHealth(url, signal),
    refreshLocalStack: async () => null,
    chooseProjectRoot: async () => undefined,
    startLocalStack: async () => false,
    stopLocalStack: async () => false,
    restartBackend: async () => false,
    updatePreferences: async () => undefined,
    refreshReleaseInfo: async () => null,
    checkForUpdate: async () => null,
    installUpdate: async () => null,
    openReleasePage: async () => undefined,
    collectCrashReport: async () => null,
  };
}
