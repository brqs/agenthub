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
  isDesktopBackendIdentityCompatible,
  isDesktopRuntime,
  normalizeDesktopError,
  openDesktopReleasePage,
  restartDesktopBackend,
  setDesktopPreferences,
  setStoredDesktopBackendUrl,
  startDesktopLocalStack,
  stopDesktopLocalStack,
  type DesktopBackendHealth,
  type DesktopBackendProfile,
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
import { switchClientBackend } from '@/lib/session';

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
  backendProfiles: DesktopBackendProfile[];
  activeBackendProfileId: string | null;
  releaseInfo: DesktopReleaseInfo | null;
  updateCheck: DesktopUpdateCheckResult | null;
  updateState: DesktopUpdateState;
  updateError: DesktopBridgeError | null;
  stackStatus: DesktopLocalStackStatus | null;
  stackProgress: DesktopStackProgress | null;
  desktopError: DesktopBridgeError | null;
  operationPending: boolean;
  setBackendUrl: (url: string) => void;
  saveBackendProfile: (
    profile: Pick<DesktopBackendProfile, 'name' | 'url'> & { id?: string },
  ) => Promise<DesktopBackendProfile | null>;
  activateBackendProfile: (profileId: string) => Promise<boolean>;
  deleteBackendProfile: (profileId: string) => Promise<boolean>;
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
  const [backendProfiles, setBackendProfiles] = useState<DesktopBackendProfile[]>(() => [
    defaultBackendProfile(getStoredDesktopBackendUrl()),
  ]);
  const [activeBackendProfileId, setActiveBackendProfileId] = useState<string | null>('default');
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
        const profiles = normalizePreferenceProfiles(nextPreferences);
        const activeProfile =
          profiles.find((profile) => profile.id === nextPreferences.activeBackendProfileId) ??
          profiles[0];
        setEnvironment(nextEnvironment);
        setPreferencesState(nextPreferences);
        setBackendProfiles(profiles);
        setActiveBackendProfileId(activeProfile?.id ?? null);
        if (activeProfile) setBackendUrlState(activeProfile.url);
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
        const activeProfile = backendProfiles.find(
          (profile) => profile.id === activeBackendProfileId,
        );
        const sameSavedAddress =
          activeProfile?.url.replace(/\/+$/, '') === result.url.replace(/\/+$/, '');
        if (
          activeProfile &&
          sameSavedAddress &&
          !isDesktopBackendIdentityCompatible(activeProfile, result)
        ) {
          const incompatible: DesktopBackendHealth = {
            ...result,
            status: 'unreachable',
            reachable: false,
            error: '该地址返回了不同的 AgentHub 服务器身份。为保护登录态，已拒绝自动连接。',
          };
          setHealth(incompatible);
          setCheckState('unreachable');
          setDesktopError(normalizeDesktopError(new Error(incompatible.error)));
          setBackendProfiles((current) =>
            current.map((profile) =>
              profile.id === activeProfile.id
                ? { ...profile, lastHealth: 'incompatible' }
                : profile,
            ),
          );
          return incompatible;
        }
        if (getApiBaseUrl() !== result.url) {
          switchClientBackend(result.url, desktop);
        } else {
          setRuntimeApiBaseUrl(result.url, { persistDesktop: desktop });
        }
        setBackendUrlState(result.url);
        if (desktop) {
          try {
            const connectedAt = new Date().toISOString();
            const profiles = backendProfiles.map((profile) =>
              profile.id === activeBackendProfileId
                ? {
                    ...profile,
                    url: result.url,
                    mode: isLocalProfileUrl(result.url)
                      ? ('local' as const)
                      : ('remote' as const),
                    serverId:
                      sameSavedAddress && !result.serverInfo?.server_id
                        ? profile.serverId
                        : result.serverInfo?.server_id,
                    lastConnectedAt: connectedAt,
                    lastHealth: 'ready' as const,
                  }
                : profile,
            );
            const next = await setDesktopPreferences({
              backendUrl: result.url,
              backendProfiles: profiles,
              activeBackendProfileId: activeBackendProfileId ?? undefined,
            });
            setPreferencesState(next);
            setBackendProfiles(normalizePreferenceProfiles(next));
            setActiveBackendProfileId(next.activeBackendProfileId ?? activeBackendProfileId);
          } catch {
            // A healthy backend remains usable even if desktop preferences cannot be persisted.
          }
        }
        setDesktopError(null);
      }
      return result;
    },
    [activeBackendProfileId, backendProfiles, backendUrl, desktop],
  );

  const persistProfiles = useCallback(
    async (
      profiles: DesktopBackendProfile[],
      activeId: string | null,
      backendUrlValue?: string,
    ) => {
      if (!desktop) return null;
      const next = await setDesktopPreferences({
        backendProfiles: profiles,
        activeBackendProfileId: activeId ?? undefined,
        backendUrl: backendUrlValue,
      });
      setPreferencesState(next);
      setBackendProfiles(normalizePreferenceProfiles(next));
      setActiveBackendProfileId(next.activeBackendProfileId ?? activeId);
      return next;
    },
    [desktop],
  );

  const saveBackendProfile = useCallback(
    async (
      input: Pick<DesktopBackendProfile, 'name' | 'url'> & { id?: string },
    ): Promise<DesktopBackendProfile | null> => {
      if (!desktop) return null;
      try {
        const normalizedUrl = normalizeBackendProfileUrl(input.url);
        const profile: DesktopBackendProfile = {
          id: input.id ?? crypto.randomUUID(),
          name: input.name.trim(),
          url: normalizedUrl,
          mode: isLocalProfileUrl(normalizedUrl) ? 'local' : 'remote',
        };
        if (!profile.name) throw new Error('请输入连接名称。');
        const profiles = backendProfiles.some((item) => item.id === profile.id)
          ? backendProfiles.map((item) => (item.id === profile.id ? profile : item))
          : [...backendProfiles, profile];
        await persistProfiles(profiles, activeBackendProfileId);
        setDesktopError(null);
        return profile;
      } catch (error) {
        setDesktopError(normalizeDesktopError(error));
        return null;
      }
    },
    [activeBackendProfileId, backendProfiles, desktop, persistProfiles],
  );

  const activateBackendProfile = useCallback(
    async (profileId: string): Promise<boolean> => {
      const profile = backendProfiles.find((item) => item.id === profileId);
      if (!desktop || !profile) return false;
      setCheckState('checking');
      const result = await checkDesktopBackendHealth(profile.url);
      setHealth(result);
      if (result.status !== 'ready') {
        setCheckState('unreachable');
        setBackendProfiles((current) =>
          current.map((item) =>
            item.id === profileId ? { ...item, lastHealth: 'unreachable' } : item,
          ),
        );
        return false;
      }
      if (!isDesktopBackendIdentityCompatible(profile, result)) {
        setCheckState('unreachable');
        setDesktopError(
          normalizeDesktopError(
            new Error('该地址返回了不同的 AgentHub 服务器身份。为保护登录态，已拒绝自动切换。'),
          ),
        );
        setBackendProfiles((current) =>
          current.map((item) =>
            item.id === profileId ? { ...item, lastHealth: 'incompatible' } : item,
          ),
        );
        return false;
      }
      const connectedAt = new Date().toISOString();
      const profiles = backendProfiles.map((item) =>
        item.id === profileId
          ? {
              ...item,
              serverId: result.serverInfo?.server_id,
              lastConnectedAt: connectedAt,
              lastHealth: 'ready' as const,
            }
          : item,
      );
      switchClientBackend(result.url, true);
      setBackendUrlState(result.url);
      setHealth(result);
      setCheckState('ready');
      setActiveBackendProfileId(profileId);
      await persistProfiles(profiles, profileId, result.url);
      setDesktopError(null);
      return true;
    },
    [backendProfiles, desktop, persistProfiles],
  );

  const deleteBackendProfile = useCallback(
    async (profileId: string): Promise<boolean> => {
      if (
        !desktop ||
        profileId === activeBackendProfileId ||
        backendProfiles.length <= 1
      ) {
        return false;
      }
      const profiles = backendProfiles.filter((item) => item.id !== profileId);
      await persistProfiles(profiles, activeBackendProfileId);
      return true;
    },
    [activeBackendProfileId, backendProfiles, desktop, persistProfiles],
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
    backendProfiles,
    activeBackendProfileId,
    releaseInfo,
    updateCheck,
    updateState,
    updateError,
    stackStatus,
    stackProgress,
    desktopError,
    operationPending,
    setBackendUrl,
    saveBackendProfile,
    activateBackendProfile,
    deleteBackendProfile,
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
    backendProfiles: [],
    activeBackendProfileId: null,
    releaseInfo: null,
    updateCheck: null,
    updateState: 'idle',
    updateError: null,
    stackStatus: null,
    stackProgress: null,
    desktopError: null,
    operationPending: false,
    setBackendUrl: () => undefined,
    saveBackendProfile: async () => null,
    activateBackendProfile: async () => false,
    deleteBackendProfile: async () => false,
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

function defaultBackendProfile(url: string): DesktopBackendProfile {
  return {
    id: 'default',
    name: isLocalProfileUrl(url) ? '本地 AgentHub' : 'AgentHub 服务器',
    url,
    mode: isLocalProfileUrl(url) ? 'local' : 'remote',
  };
}

function normalizePreferenceProfiles(preferences: DesktopPreferences): DesktopBackendProfile[] {
  return preferences.backendProfiles?.length
    ? preferences.backendProfiles
    : [defaultBackendProfile(preferences.backendUrl)];
}

function normalizeBackendProfileUrl(url: string): string {
  const raw = url.trim();
  const localWithoutProtocol = /^(localhost|127\.0\.0\.1|\[?::1\]?)(:\d+)?(\/|$)/i.test(raw);
  const remoteHttpWithoutProtocol =
    /^(\d{1,3}\.){3}\d{1,3}(:\d+)?(\/|$)/.test(raw) ||
    /^\[[0-9a-f:]+\](:\d+)?(\/|$)/i.test(raw) ||
    /^[^/:]+:\d+(\/|$)/.test(raw);
  const normalized = new URL(
    raw.match(/^https?:\/\//i)
      ? raw
      : `${localWithoutProtocol || remoteHttpWithoutProtocol ? 'http' : 'https'}://${raw}`,
  );
  normalized.hash = '';
  normalized.search = '';
  const value = normalized.toString().replace(/\/$/, '');
  return value;
}

function isLocalProfileUrl(url: string): boolean {
  try {
    const host = new URL(url).hostname.toLowerCase();
    return host === 'localhost' || host === '127.0.0.1' || host === '::1';
  } catch {
    return false;
  }
}
