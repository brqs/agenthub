import {
  checkDesktopBackendHealth,
  DEFAULT_DESKTOP_BACKEND_URL,
  getStoredDesktopBackendUrl,
  isDesktopBackendIdentityCompatible,
  isDesktopRuntime,
  normalizeBackendUrl,
  parseDesktopDeepLink,
  saveBlobWithDesktopDialog,
  selectDesktopFiles,
  setStoredDesktopBackendUrl,
} from './desktopBridge';
import { open, save } from '@tauri-apps/plugin-dialog';
import { readFile, stat, writeFile } from '@tauri-apps/plugin-fs';

vi.mock('@tauri-apps/plugin-dialog', () => ({
  open: vi.fn(),
  save: vi.fn(),
}));

vi.mock('@tauri-apps/plugin-fs', () => ({
  readFile: vi.fn(),
  stat: vi.fn(),
  writeFile: vi.fn(),
}));

vi.mock('@tauri-apps/plugin-deep-link', () => ({
  getCurrent: vi.fn(async () => []),
  onOpenUrl: vi.fn(async () => vi.fn()),
}));

describe('desktopBridge', () => {
  beforeEach(() => {
    window.localStorage.clear();
    delete (window as Window & { __TAURI_INTERNALS__?: unknown }).__TAURI_INTERNALS__;
    vi.unstubAllGlobals();
    vi.mocked(open).mockReset();
    vi.mocked(save).mockReset();
    vi.mocked(readFile).mockReset();
    vi.mocked(stat).mockReset();
    vi.mocked(writeFile).mockReset();
  });

  it('detects regular web fallback and Tauri runtime', () => {
    expect(isDesktopRuntime()).toBe(false);

    (window as Window & { __TAURI_INTERNALS__?: unknown }).__TAURI_INTERNALS__ = {};

    expect(isDesktopRuntime()).toBe(true);
  });

  it('normalizes and persists backend URLs', () => {
    expect(normalizeBackendUrl('localhost:8000/')).toBe(DEFAULT_DESKTOP_BACKEND_URL);

    setStoredDesktopBackendUrl('http://127.0.0.1:8000/');

    expect(getStoredDesktopBackendUrl()).toBe('http://127.0.0.1:8000');
  });

  it('accepts only AgentHub chat and notification deep links', () => {
    const conversationId = '123e4567-e89b-12d3-a456-426614174000';
    const notificationId = '223e4567-e89b-12d3-a456-426614174000';

    expect(parseDesktopDeepLink(`agenthub://chat/${conversationId}`)).toEqual({
      kind: 'chat',
      conversationId,
    });
    expect(
      parseDesktopDeepLink(
        `agenthub://notification/${notificationId}?conversationId=${conversationId}`,
      ),
    ).toEqual({
      kind: 'notification',
      notificationId,
      conversationId,
    });
    expect(parseDesktopDeepLink(`agenthub://chat/${conversationId}/extra`)).toBeNull();
    expect(parseDesktopDeepLink(`agenthub://user:pass@chat/${conversationId}`)).toBeNull();
    expect(parseDesktopDeepLink(`https://example.com/chat/${conversationId}`)).toBeNull();
  });

  it('maps successful health responses', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(async () => new Response(JSON.stringify({ status: 'ok', version: '0.1.0' }))),
    );

    const health = await checkDesktopBackendHealth('localhost:8000');

    expect(fetch).toHaveBeenCalledWith('http://localhost:8000/health', expect.any(Object));
    expect(health.status).toBe('ready');
    expect(health.version).toBe('0.1.0');
  });

  it('loads AgentHub server identity when the endpoint is available', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(async (input: RequestInfo | URL) => {
        const url = String(input);
        if (url.endsWith('/api/v1/server-info')) {
          return new Response(
            JSON.stringify({
              server_id: 'public-agenthub',
              version: '0.1.0',
              deployment_mode: 'hosted',
              features: {
                uploads: true,
                workspace: true,
                orchestrator: true,
                desktop_local_stack: false,
              },
              auth: { type: 'jwt' },
              limits: { max_upload_mb: 100 },
            }),
          );
        }
        return new Response(JSON.stringify({ status: 'ok', version: '0.1.0' }));
      }),
    );

    const health = await checkDesktopBackendHealth('https://agenthub.example.com');

    expect(health.serverInfo?.server_id).toBe('public-agenthub');
    expect(health.serverInfo?.deployment_mode).toBe('hosted');
  });

  it('allows explicit HTTP backend profiles for remote test deployments', async () => {
    const fetchMock = vi.fn(async () => new Response(JSON.stringify({ status: 'ok' })));
    vi.stubGlobal('fetch', fetchMock);

    const health = await checkDesktopBackendHealth('http://agenthub.example.com');

    expect(fetchMock).toHaveBeenCalledWith('http://agenthub.example.com/health', expect.any(Object));
    expect(health.status).toBe('ready');
  });

  it('rejects a changed server identity for a saved backend profile', () => {
    expect(
      isDesktopBackendIdentityCompatible(
        {
          id: 'public',
          name: 'Public AgentHub',
          url: 'https://agenthub.example.com',
          mode: 'remote',
          serverId: 'server-a',
        },
        {
          url: 'https://agenthub.example.com',
          reachable: true,
          status: 'ready',
          serverInfo: {
            server_id: 'server-b',
            version: '0.1.0',
            deployment_mode: 'hosted',
            features: {
              uploads: true,
              workspace: true,
              orchestrator: true,
              desktop_local_stack: false,
            },
            auth: { type: 'jwt' },
            limits: { max_upload_mb: 100 },
          },
        },
      ),
    ).toBe(false);
  });

  it('requires server identity discovery after a profile has been pinned', () => {
    expect(
      isDesktopBackendIdentityCompatible(
        {
          id: 'public',
          name: 'Public AgentHub',
          url: 'https://agenthub.example.com',
          mode: 'remote',
          serverId: 'server-a',
        },
        {
          url: 'https://agenthub.example.com',
          reachable: true,
          status: 'ready',
        },
      ),
    ).toBe(false);
  });

  it('maps unreachable health responses', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(async () => new Response('missing', { status: 503 })),
    );

    const health = await checkDesktopBackendHealth('http://localhost:8000');

    expect(health.status).toBe('unreachable');
    expect(health.error).toContain('HTTP 503');
  });

  it('bounds remote backend health checks with a timeout', async () => {
    vi.useFakeTimers();
    vi.stubGlobal(
      'fetch',
      vi.fn(
        (_input: RequestInfo | URL, init?: RequestInit) =>
          new Promise<Response>((_resolve, reject) => {
            init?.signal?.addEventListener(
              'abort',
              () => reject(new DOMException('Aborted', 'AbortError')),
              { once: true },
            );
          }),
      ),
    );

    try {
      const pending = checkDesktopBackendHealth('https://agenthub.example.com');
      await vi.advanceTimersByTimeAsync(10_000);
      await expect(pending).resolves.toMatchObject({
        status: 'unreachable',
        error: '连接 AgentHub 后端超时，请检查服务器地址和网络。',
      });
    } finally {
      vi.useRealTimers();
    }
  });

  it('reads only files selected by the desktop dialog', async () => {
    (window as Window & { __TAURI_INTERNALS__?: unknown }).__TAURI_INTERNALS__ = {};
    vi.mocked(open).mockResolvedValue(['C:\\selected\\demo.zip']);
    vi.mocked(stat).mockResolvedValue({
      size: 3,
      mtime: new Date('2026-06-09T00:00:00Z'),
    } as Awaited<ReturnType<typeof stat>>);
    vi.mocked(readFile).mockResolvedValue(new Uint8Array([1, 2, 3]));

    const files = await selectDesktopFiles();

    expect(readFile).toHaveBeenCalledWith('C:\\selected\\demo.zip');
    expect(files).toHaveLength(1);
    expect(files[0]?.name).toBe('demo.zip');
    expect(files[0]?.type).toBe('application/zip');
  });

  it('rejects oversized files before reading their content', async () => {
    (window as Window & { __TAURI_INTERNALS__?: unknown }).__TAURI_INTERNALS__ = {};
    vi.mocked(open).mockResolvedValue(['C:\\selected\\huge.zip']);
    vi.mocked(stat).mockResolvedValue({
      size: 101 * 1024 * 1024,
    } as Awaited<ReturnType<typeof stat>>);

    await expect(selectDesktopFiles()).rejects.toMatchObject({
      code: 'desktop_file_too_large',
    });
    expect(readFile).not.toHaveBeenCalled();
  });

  it('rejects selections that exceed the remaining attachment slots', async () => {
    (window as Window & { __TAURI_INTERNALS__?: unknown }).__TAURI_INTERNALS__ = {};
    vi.mocked(open).mockResolvedValue([
      'C:\\selected\\one.png',
      'C:\\selected\\two.png',
    ]);

    await expect(selectDesktopFiles({ maxFiles: 1 })).rejects.toMatchObject({
      code: 'desktop_file_limit',
    });
    expect(stat).not.toHaveBeenCalled();
    expect(readFile).not.toHaveBeenCalled();
  });

  it('writes downloads only to the system-selected save path', async () => {
    (window as Window & { __TAURI_INTERNALS__?: unknown }).__TAURI_INTERNALS__ = {};
    vi.mocked(save).mockResolvedValue('C:\\selected\\source.zip');
    vi.mocked(writeFile).mockResolvedValue(undefined);

    const result = await saveBlobWithDesktopDialog(
      new Blob(['zip']),
      'source.zip',
      [{ name: 'ZIP', extensions: ['zip'] }],
    );

    expect(result).toEqual({ saved: true, fileName: 'source.zip' });
    expect(writeFile).toHaveBeenCalledWith(
      'C:\\selected\\source.zip',
      expect.any(Uint8Array),
    );
  });
});
