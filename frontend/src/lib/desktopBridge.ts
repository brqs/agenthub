import { Channel, invoke } from '@tauri-apps/api/core';
import { listen, type UnlistenFn } from '@tauri-apps/api/event';
import { getCurrent, onOpenUrl } from '@tauri-apps/plugin-deep-link';
import { open, save } from '@tauri-apps/plugin-dialog';
import { readFile, stat, writeFile } from '@tauri-apps/plugin-fs';

export const DEFAULT_DESKTOP_BACKEND_URL = 'http://localhost:8000';

const DESKTOP_BACKEND_URL_STORAGE_KEY = 'agenthub.desktop.backendUrl';
const DESKTOP_BACKEND_CHECK_TIMEOUT_MS = 10_000;

export type DesktopBackendHealthStatus = 'ready' | 'starting' | 'unreachable';
export type DesktopBackendProfileMode = 'local' | 'remote';
export type DesktopBackendProfileHealth = 'ready' | 'unreachable' | 'incompatible';

export interface DesktopBackendProfile {
  id: string;
  name: string;
  url: string;
  mode: DesktopBackendProfileMode;
  serverId?: string;
  lastConnectedAt?: string;
  lastHealth?: DesktopBackendProfileHealth;
}

export interface AgentHubServerInfo {
  server_id: string;
  version: string;
  deployment_mode: 'local' | 'hosted';
  features: {
    uploads: boolean;
    workspace: boolean;
    orchestrator: boolean;
    desktop_local_stack: boolean;
  };
  auth: { type: 'jwt' };
  limits: { max_upload_mb: number };
}

export interface DesktopBackendHealth {
  url: string;
  reachable: boolean;
  status: DesktopBackendHealthStatus;
  version?: string;
  environment?: string;
  dependencies?: Record<string, string>;
  serverInfo?: AgentHubServerInfo;
  error?: string;
}

export function isDesktopBackendIdentityCompatible(
  profile: DesktopBackendProfile,
  health: DesktopBackendHealth,
): boolean {
  const currentServerId = health.serverInfo?.server_id;
  return !profile.serverId || profile.serverId === currentServerId;
}

export interface DesktopEnvironment {
  platform: string;
  appVersion: string;
  appDataDir: string;
}

export type DesktopStackProfile = 'source' | 'windows_image';
export type DesktopDockerStatus = 'ready' | 'not_installed' | 'not_running';
export type DesktopBackendHealthState = 'ready' | 'starting' | 'unreachable';
export type DesktopServiceStatus =
  | 'healthy'
  | 'running'
  | 'starting'
  | 'stopped'
  | 'error'
  | 'unknown';
export type DesktopServiceName = 'backend' | 'postgres' | 'redis';

export interface DesktopStackBinding {
  projectRoot: string;
  projectName: string;
  profile: DesktopStackProfile;
  source: string;
}

export interface DesktopServiceState {
  name: DesktopServiceName;
  status: DesktopServiceStatus;
  detail?: string;
}

export interface DesktopLocalStackStatus {
  projectRoot?: string;
  projectName?: string;
  profile?: DesktopStackProfile;
  docker: DesktopDockerStatus;
  composeAvailable: boolean;
  backendHealth: DesktopBackendHealthState;
  services: DesktopServiceState[];
  error?: string;
}

export interface DesktopStackProgress {
  stage: string;
  message: string;
  detail?: string;
}

export interface DesktopStackOperation {
  action: string;
  success: boolean;
  status: DesktopLocalStackStatus;
}

export interface DesktopServiceLogTail {
  service: DesktopServiceName;
  lines: string[];
  truncated: boolean;
  sanitized: boolean;
}

export interface DesktopPreferences {
  backendUrl: string;
  backendProfiles: DesktopBackendProfile[];
  activeBackendProfileId?: string;
  autoStartLocalStack: boolean;
  notificationsEnabled: boolean;
  autoCheckUpdates: boolean;
  lastUpdateCheckAt?: string;
  updateChannel: 'stable';
  projectRoot?: string;
  projectName?: string;
  profile?: DesktopStackProfile;
}

export interface DesktopPreferencesPatch {
  backendUrl?: string;
  backendProfiles?: DesktopBackendProfile[];
  activeBackendProfileId?: string;
  autoStartLocalStack?: boolean;
  notificationsEnabled?: boolean;
  autoCheckUpdates?: boolean;
  lastUpdateCheckAt?: string;
  updateChannel?: 'stable';
}

export interface DesktopDiagnosticsExport {
  fileToken: string;
  suggestedName: string;
}

export interface DesktopSaveResult {
  saved: boolean;
  fileName?: string;
}

export interface DesktopNotificationInput {
  notificationId: string;
  conversationId: string;
  kind: 'done' | 'error' | 'attention';
  agentLabel: string;
}

export interface DesktopNotificationActivation {
  notificationId: string;
  conversationId: string;
}

export type DesktopDeepLinkActivation =
  | { kind: 'chat'; conversationId: string }
  | { kind: 'notification'; notificationId: string; conversationId: string };

export interface DesktopReleaseInfo {
  appVersion: string;
  updateChannel: 'stable';
  updateEndpoint: string;
  releasePageUrl: string;
  installerKind: string;
  autoCheckUpdates: boolean;
  lastUpdateCheckAt?: string;
}

export interface DesktopUpdateCheckResult {
  checkedAt: string;
  available: boolean;
  currentVersion: string;
  version?: string;
  date?: string;
  body?: string;
  releasePageUrl: string;
}

export interface DesktopUpdateInstallResult {
  installed: boolean;
  restartRequired: boolean;
  version?: string;
}

export interface DesktopCrashReport {
  exists: boolean;
  lines: string[];
  truncated: boolean;
}

export interface LocalRuntimeConnectorProbe {
  available: boolean;
  reason?: string;
}

export interface LocalRuntimeConnectorState {
  running: boolean;
  endpointUrl?: string;
  runtimeIds: string[];
}

export interface DesktopFilePickerOptions {
  maxFiles?: number;
  maxBytes?: number;
}

export interface DesktopSaveFilter {
  name: string;
  extensions: string[];
}

export interface DesktopBridgeError {
  code: string;
  message: string;
  detail?: string;
}

type TauriWindow = Window & {
  __TAURI__?: unknown;
  __TAURI_INTERNALS__?: unknown;
};

export function isDesktopRuntime(): boolean {
  if (typeof window === 'undefined') return false;
  const forced = (import.meta.env.VITE_DESKTOP_MODE as string | undefined) === 'true';
  if (forced) return true;
  const tauriWindow = window as TauriWindow;
  if (tauriWindow.__TAURI__ || tauriWindow.__TAURI_INTERNALS__) return true;
  return (
    window.location.origin === 'http://tauri.localhost' ||
    window.location.origin === 'https://tauri.localhost'
  );
}

export function normalizeBackendUrl(input: string): string {
  const raw = input.trim();
  if (!raw) return DEFAULT_DESKTOP_BACKEND_URL;
  const withProtocol = /^[a-z][a-z\d+\-.]*:\/\//i.test(raw) ? raw : `http://${raw}`;
  const parsed = new URL(withProtocol);
  if (parsed.protocol !== 'http:' && parsed.protocol !== 'https:') {
    throw new Error('后端地址必须以 http:// 或 https:// 开头。');
  }
  parsed.hash = '';
  parsed.search = '';
  const normalized = parsed.toString().replace(/\/$/, '');
  return normalized;
}

export function isLocalBackendUrl(input: string): boolean {
  try {
    const url = new URL(normalizeBackendUrl(input));
    return url.hostname === 'localhost' || url.hostname === '127.0.0.1' || url.hostname === '::1';
  } catch {
    return false;
  }
}

export function getStoredDesktopBackendUrl(): string {
  if (typeof window === 'undefined') return DEFAULT_DESKTOP_BACKEND_URL;
  try {
    const stored = window.localStorage.getItem(DESKTOP_BACKEND_URL_STORAGE_KEY);
    return stored ? normalizeBackendUrl(stored) : DEFAULT_DESKTOP_BACKEND_URL;
  } catch {
    return DEFAULT_DESKTOP_BACKEND_URL;
  }
}

export function setStoredDesktopBackendUrl(url: string): string {
  const normalized = normalizeBackendUrl(url);
  if (typeof window !== 'undefined') {
    try {
      window.localStorage.setItem(DESKTOP_BACKEND_URL_STORAGE_KEY, normalized);
    } catch {
      // Ignore storage failures; the runtime URL still applies for this session.
    }
  }
  return normalized;
}

export async function checkDesktopBackendHealth(
  url: string,
  signal?: AbortSignal,
): Promise<DesktopBackendHealth> {
  let normalized: string;
  try {
    normalized = normalizeBackendUrl(url);
    const parsed = new URL(normalized);
    if (!isLocalBackendUrl(normalized) && parsed.protocol !== 'https:') {
      return {
        url: normalized,
        reachable: false,
        status: 'unreachable',
        error: '公网后端必须使用 HTTPS。',
      };
    }
  } catch (error) {
    return {
      url,
      reachable: false,
      status: 'unreachable',
      error: error instanceof Error ? error.message : String(error),
    };
  }

  const controller = new AbortController();
  let timedOut = false;
  const abortFromCaller = () => controller.abort(signal?.reason);
  if (signal?.aborted) {
    controller.abort(signal.reason);
  } else {
    signal?.addEventListener('abort', abortFromCaller, { once: true });
  }
  const timeout = window.setTimeout(() => {
    timedOut = true;
    controller.abort();
  }, DESKTOP_BACKEND_CHECK_TIMEOUT_MS);

  try {
    const response = await fetch(`${normalized}/health`, {
      method: 'GET',
      headers: { Accept: 'application/json' },
      cache: 'no-store',
      signal: controller.signal,
    });

    if (!response.ok) {
      return {
        url: normalized,
        reachable: false,
        status: 'unreachable',
        error: `后端返回 HTTP ${response.status}`,
      };
    }

    const body = await response.json().catch(() => ({}));
    const status = body?.status === 'ok' ? 'ready' : 'starting';
    const serverInfo =
      status === 'ready'
        ? await fetchAgentHubServerInfo(normalized, controller.signal)
        : undefined;
    return {
      url: normalized,
      reachable: true,
      status,
      version: typeof body?.version === 'string' ? body.version : undefined,
      environment: typeof body?.environment === 'string' ? body.environment : undefined,
      dependencies: isStringRecord(body?.dependencies) ? body.dependencies : undefined,
      serverInfo,
      error: status === 'ready' ? undefined : '后端正在启动，请稍后重试。',
    };
  } catch (error) {
    if (signal?.aborted && error instanceof DOMException && error.name === 'AbortError') {
      throw error;
    }
    return {
      url: normalized,
      reachable: false,
      status: 'unreachable',
      error: timedOut
        ? '连接 AgentHub 后端超时，请检查服务器地址和网络。'
        : error instanceof Error
          ? error.message
          : '无法连接到 AgentHub 后端。',
    };
  } finally {
    window.clearTimeout(timeout);
    signal?.removeEventListener('abort', abortFromCaller);
  }
}

async function fetchAgentHubServerInfo(
  url: string,
  signal?: AbortSignal,
): Promise<AgentHubServerInfo | undefined> {
  try {
    const response = await fetch(`${url}/api/v1/server-info`, {
      method: 'GET',
      headers: { Accept: 'application/json' },
      cache: 'no-store',
      signal,
    });
    if (!response.ok) return undefined;
    const body: unknown = await response.json();
    return isAgentHubServerInfo(body) ? body : undefined;
  } catch (error) {
    if (error instanceof DOMException && error.name === 'AbortError') throw error;
    return undefined;
  }
}

function isAgentHubServerInfo(value: unknown): value is AgentHubServerInfo {
  if (!value || typeof value !== 'object') return false;
  const info = value as Record<string, unknown>;
  return (
    typeof info.server_id === 'string' &&
    typeof info.version === 'string' &&
    (info.deployment_mode === 'local' || info.deployment_mode === 'hosted') &&
    Boolean(info.features && typeof info.features === 'object') &&
    Boolean(info.auth && typeof info.auth === 'object') &&
    Boolean(info.limits && typeof info.limits === 'object')
  );
}

export async function getDesktopEnvironment(): Promise<DesktopEnvironment> {
  return invokeDesktop('desktop_get_environment');
}

export async function getDesktopPreferences(): Promise<DesktopPreferences> {
  return invokeDesktop('desktop_get_preferences');
}

export async function setDesktopPreferences(
  patch: DesktopPreferencesPatch,
): Promise<DesktopPreferences> {
  return invokeDesktop('desktop_set_preferences', { patch });
}

export async function chooseDesktopProjectRoot(): Promise<DesktopStackBinding | null> {
  return invokeDesktop('desktop_choose_project_root');
}

export async function getDesktopStackBinding(): Promise<DesktopStackBinding> {
  return invokeDesktop('desktop_get_stack_binding');
}

export async function checkDesktopLocalStack(): Promise<DesktopLocalStackStatus> {
  return invokeDesktop('desktop_check_local_stack');
}

export async function startDesktopLocalStack(
  options: { rebuild?: boolean } = {},
  onProgress?: (progress: DesktopStackProgress) => void,
): Promise<DesktopStackOperation> {
  return invokeStackOperation('desktop_start_local_stack', { options }, onProgress);
}

export async function stopDesktopLocalStack(
  onProgress?: (progress: DesktopStackProgress) => void,
): Promise<DesktopStackOperation> {
  return invokeStackOperation('desktop_stop_local_stack', {}, onProgress);
}

export async function restartDesktopBackend(
  onProgress?: (progress: DesktopStackProgress) => void,
): Promise<DesktopStackOperation> {
  return invokeStackOperation('desktop_restart_backend', {}, onProgress);
}

export async function tailDesktopServiceLogs(
  service: DesktopServiceName,
  lines = 300,
): Promise<DesktopServiceLogTail> {
  return invokeDesktop('desktop_tail_service_logs', { service, lines });
}

export async function exportDesktopDiagnostics(): Promise<DesktopDiagnosticsExport> {
  return invokeDesktop('desktop_export_diagnostics');
}

export async function saveDesktopDiagnostics(fileToken: string): Promise<DesktopSaveResult> {
  return invokeDesktop('desktop_save_diagnostics', { fileToken });
}

export async function openDesktopWorkspaceFolder(
  conversationId: string,
): Promise<{ opened: boolean }> {
  return invokeDesktop('desktop_open_workspace_folder', { conversationId });
}

export async function openDesktopExternalUrl(url: string): Promise<{ opened: boolean }> {
  return invokeDesktop('desktop_open_external_url', { url });
}

export async function showDesktopNotification(
  input: DesktopNotificationInput,
): Promise<{ opened: boolean }> {
  return invokeDesktop('desktop_show_notification', { input });
}

export async function getDesktopReleaseInfo(): Promise<DesktopReleaseInfo> {
  return invokeDesktop('desktop_get_release_info');
}

export async function checkForDesktopUpdate(): Promise<DesktopUpdateCheckResult> {
  return invokeDesktop('desktop_check_for_update');
}

export async function installDesktopUpdate(): Promise<DesktopUpdateInstallResult> {
  return invokeDesktop('desktop_install_update');
}

export async function openDesktopReleasePage(): Promise<{ opened: boolean }> {
  return invokeDesktop('desktop_open_release_page');
}

export async function collectDesktopCrashReport(): Promise<DesktopCrashReport> {
  return invokeDesktop('desktop_collect_crash_report');
}

export async function probeLocalRuntimeConnector(): Promise<LocalRuntimeConnectorProbe> {
  return invokeDesktop('desktop_probe_local_runtime_connector');
}

export async function startLocalRuntimeConnector(): Promise<LocalRuntimeConnectorState> {
  return invokeDesktop('desktop_start_local_runtime_connector');
}

export async function stopLocalRuntimeConnector(): Promise<LocalRuntimeConnectorState> {
  return invokeDesktop('desktop_stop_local_runtime_connector');
}

export async function listenForDesktopNotificationActivation(
  callback: (activation: DesktopNotificationActivation) => void,
): Promise<UnlistenFn> {
  assertDesktopRuntime();
  return listen<DesktopNotificationActivation>(
    'desktop://notification-activated',
    (event) => callback(event.payload),
  );
}

export async function listenForDesktopDeepLinkActivation(
  callback: (activation: DesktopDeepLinkActivation) => void,
): Promise<UnlistenFn> {
  assertDesktopRuntime();
  const disposers: UnlistenFn[] = [];
  const emit = (urls: string[] | null) => {
    for (const url of urls ?? []) {
      const activation = parseDesktopDeepLink(url);
      if (activation) callback(activation);
    }
  };
  emit(await getCurrent().catch(() => null));
  disposers.push(await onOpenUrl(emit));
  disposers.push(
    await listen<DesktopDeepLinkActivation>('desktop://deep-link', (event) => {
      callback(event.payload);
    }),
  );
  return () => {
    for (const dispose of disposers) dispose();
  };
}

export function parseDesktopDeepLink(input: string): DesktopDeepLinkActivation | null {
  if (input.length > 512) return null;
  let url: URL;
  try {
    url = new URL(input);
  } catch {
    return null;
  }
  if (url.protocol !== 'agenthub:') return null;
  if (url.username || url.password) return null;
  const id = url.pathname.replace(/^\/+|\/+$/g, '');
  const uuidPattern = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;
  if (!uuidPattern.test(id) || id.includes('/') || id.includes('\\')) return null;
  if (url.hostname === 'chat') {
    return { kind: 'chat', conversationId: id };
  }
  if (url.hostname === 'notification') {
    const conversationId = url.searchParams.get('conversationId') ?? '';
    if (!uuidPattern.test(conversationId)) return null;
    return { kind: 'notification', notificationId: id, conversationId };
  }
  return null;
}

export async function selectDesktopFiles(
  options: DesktopFilePickerOptions = {},
): Promise<File[]> {
  assertDesktopRuntime();
  const selected = await open({
    multiple: true,
    directory: false,
    title: '选择要上传到 AgentHub 的文件',
  });
  const paths = Array.isArray(selected) ? selected : selected ? [selected] : [];
  const maxFiles = options.maxFiles ?? 10;
  const maxBytes = options.maxBytes ?? 100 * 1024 * 1024;
  if (paths.length > maxFiles) {
    throw {
      code: 'desktop_file_limit',
      message: `本次最多还能选择 ${maxFiles} 个文件。`,
    } satisfies DesktopBridgeError;
  }
  const files: File[] = [];
  for (const path of paths) {
    const metadata = await stat(path);
    if (metadata.size > maxBytes) {
      throw {
        code: 'desktop_file_too_large',
        message: `文件 ${fileNameFromPath(path)} 超过 ${formatByteLimit(maxBytes)} 限制。`,
      } satisfies DesktopBridgeError;
    }
    const bytes = await readFile(path);
    files.push(
      new File([bytes], fileNameFromPath(path), {
        type: mimeTypeFromFileName(path),
        lastModified: metadata.mtime ? metadata.mtime.getTime() : Date.now(),
      }),
    );
  }
  return files;
}

export async function saveBlobWithDesktopDialog(
  blob: Blob,
  suggestedName: string,
  filters: DesktopSaveFilter[] = [],
): Promise<DesktopSaveResult> {
  assertDesktopRuntime();
  const destination = await save({
    title: '保存 AgentHub 文件',
    defaultPath: suggestedName,
    filters,
  });
  if (!destination) return { saved: false };
  await writeFile(destination, await blobToUint8Array(blob));
  return {
    saved: true,
    fileName: fileNameFromPath(destination),
  };
}

async function invokeStackOperation(
  command: string,
  args: Record<string, unknown>,
  onProgress?: (progress: DesktopStackProgress) => void,
): Promise<DesktopStackOperation> {
  assertDesktopRuntime();
  const onEvent = new Channel<DesktopStackProgress>();
  onEvent.onmessage = (progress) => onProgress?.(progress);
  try {
    return await invoke<DesktopStackOperation>(command, { ...args, onEvent });
  } catch (error) {
    throw normalizeDesktopError(error);
  }
}

async function invokeDesktop<T>(
  command: string,
  args?: Record<string, unknown>,
): Promise<T> {
  assertDesktopRuntime();
  try {
    return await invoke<T>(command, args);
  } catch (error) {
    throw normalizeDesktopError(error);
  }
}

function assertDesktopRuntime(): void {
  if (!isDesktopRuntime()) {
    throw {
      code: 'desktop_not_available',
      message: '此功能仅在 AgentHub Windows 桌面客户端中可用。',
    } satisfies DesktopBridgeError;
  }
}

export function normalizeDesktopError(error: unknown): DesktopBridgeError {
  if (error && typeof error === 'object') {
    const raw = error as Record<string, unknown>;
    if (typeof raw.code === 'string' && typeof raw.message === 'string') {
      return {
        code: raw.code,
        message: raw.message,
        detail: typeof raw.detail === 'string' ? raw.detail : undefined,
      };
    }
  }
  return {
    code: 'desktop_unknown',
    message: error instanceof Error ? error.message : String(error),
  };
}

function isStringRecord(value: unknown): value is Record<string, string> {
  if (!value || typeof value !== 'object' || Array.isArray(value)) return false;
  return Object.values(value).every((item) => typeof item === 'string');
}

function fileNameFromPath(path: string): string {
  return path.split(/[\\/]/).filter(Boolean).pop() ?? 'agenthub-file';
}

function mimeTypeFromFileName(path: string): string {
  const extension = fileNameFromPath(path).split('.').pop()?.toLowerCase();
  const mimeTypes: Record<string, string> = {
    png: 'image/png',
    jpg: 'image/jpeg',
    jpeg: 'image/jpeg',
    gif: 'image/gif',
    webp: 'image/webp',
    svg: 'image/svg+xml',
    pdf: 'application/pdf',
    zip: 'application/zip',
    json: 'application/json',
    md: 'text/markdown',
    txt: 'text/plain',
    csv: 'text/csv',
  };
  return extension ? mimeTypes[extension] ?? 'application/octet-stream' : 'application/octet-stream';
}

function formatByteLimit(bytes: number): string {
  if (bytes >= 1024 * 1024 && bytes % (1024 * 1024) === 0) {
    return `${bytes / (1024 * 1024)} MB`;
  }
  if (bytes >= 1024 && bytes % 1024 === 0) {
    return `${bytes / 1024} KB`;
  }
  return `${bytes} B`;
}

async function blobToUint8Array(blob: Blob): Promise<Uint8Array> {
  if (typeof blob.arrayBuffer === 'function') {
    return new Uint8Array(await blob.arrayBuffer());
  }
  return new Promise<Uint8Array>((resolve, reject) => {
    const reader = new FileReader();
    reader.onerror = () => reject(reader.error ?? new Error('无法读取待保存文件。'));
    reader.onload = () => resolve(new Uint8Array(reader.result as ArrayBuffer));
    reader.readAsArrayBuffer(blob);
  });
}
