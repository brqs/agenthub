import { render, screen, waitFor } from '@testing-library/react';
import { DesktopBootstrapGate } from './DesktopBootstrapGate';
import { useDesktopEnvironment, type DesktopEnvironmentState } from '@/hooks/useDesktopEnvironment';

vi.mock('@/hooks/useDesktopEnvironment', () => ({
  useDesktopEnvironment: vi.fn(),
}));

const useDesktopEnvironmentMock = vi.mocked(useDesktopEnvironment);

describe('DesktopBootstrapGate', () => {
  const createDesktopState = (
    overrides: Partial<DesktopEnvironmentState> = {},
  ): DesktopEnvironmentState => ({
    isDesktop: false,
    backendUrl: '',
    runtimeApiBaseUrl: '',
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
    setBackendUrl: vi.fn(),
    saveBackendProfile: vi.fn(async () => null),
    activateBackendProfile: vi.fn(async () => false),
    deleteBackendProfile: vi.fn(async () => false),
    checkBackend: vi.fn(async () => ({
      url: 'http://localhost:8000',
      reachable: false,
      status: 'unreachable' as const,
    })),
    refreshLocalStack: vi.fn(async () => null),
    chooseProjectRoot: vi.fn(async () => undefined),
    startLocalStack: vi.fn(async () => false),
    stopLocalStack: vi.fn(async () => false),
    restartBackend: vi.fn(async () => false),
    updatePreferences: vi.fn(async () => undefined),
    refreshReleaseInfo: vi.fn(async () => null),
    checkForUpdate: vi.fn(async () => null),
    installUpdate: vi.fn(async () => null),
    openReleasePage: vi.fn(async () => undefined),
    collectCrashReport: vi.fn(async () => null),
    ...overrides,
  });

  beforeEach(() => {
    useDesktopEnvironmentMock.mockReset();
  });

  it('renders children immediately in web mode', () => {
    useDesktopEnvironmentMock.mockReturnValue(createDesktopState());

    render(
      <DesktopBootstrapGate>
        <div>AgentHub Web</div>
      </DesktopBootstrapGate>,
    );

    expect(screen.getByText('AgentHub Web')).toBeInTheDocument();
  });

  it('shows the desktop startup screen before backend is reachable', () => {
    useDesktopEnvironmentMock.mockReturnValue(createDesktopState({
      isDesktop: true,
      backendUrl: 'http://localhost:8000',
      runtimeApiBaseUrl: 'http://localhost:8000',
      health: { url: 'http://localhost:8000', reachable: false, status: 'unreachable' },
      checkState: 'unreachable',
      checkBackend: vi.fn(async () => ({
        url: 'http://localhost:8000',
        reachable: false,
        status: 'unreachable' as const,
      })),
    }));

    render(
      <DesktopBootstrapGate>
        <div>AgentHub Web</div>
      </DesktopBootstrapGate>,
    );

    expect(screen.getByText('连接 AgentHub 后端')).toBeInTheDocument();
    expect(screen.queryByText('AgentHub Web')).not.toBeInTheDocument();
  });

  it('does not expose local stack controls for a remote backend', () => {
    useDesktopEnvironmentMock.mockReturnValue(createDesktopState({
      isDesktop: true,
      backendUrl: 'https://agenthub.example.com',
      runtimeApiBaseUrl: 'https://agenthub.example.com',
      health: {
        url: 'https://agenthub.example.com',
        reachable: false,
        status: 'unreachable',
      },
      checkState: 'unreachable',
    }));

    render(
      <DesktopBootstrapGate>
        <div>AgentHub Web</div>
      </DesktopBootstrapGate>,
    );

    expect(screen.queryByRole('button', { name: '启动本地 AgentHub' })).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: '选择项目目录' })).not.toBeInTheDocument();
  });

  it('auto-starts the local stack only after the preference was enabled', async () => {
    const startLocalStack = vi.fn(async () => false);
    useDesktopEnvironmentMock.mockReturnValue(createDesktopState({
      isDesktop: true,
      backendUrl: 'http://localhost:8000',
      runtimeApiBaseUrl: 'http://localhost:8000',
      health: { url: 'http://localhost:8000', reachable: false, status: 'unreachable' },
      checkState: 'unreachable',
      preferences: {
        backendUrl: 'http://localhost:8000',
        backendProfiles: [
          {
            id: 'default',
            name: '本地 AgentHub',
            url: 'http://localhost:8000',
            mode: 'local',
          },
        ],
        activeBackendProfileId: 'default',
        autoStartLocalStack: true,
        notificationsEnabled: false,
        autoCheckUpdates: true,
        updateChannel: 'stable',
      },
      startLocalStack,
    }));

    render(
      <DesktopBootstrapGate>
        <div>AgentHub Web</div>
      </DesktopBootstrapGate>,
    );

    await waitFor(() => expect(startLocalStack).toHaveBeenCalledTimes(1));
  });
});
