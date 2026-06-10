import { fireEvent, render, screen } from '@testing-library/react';
import type { DesktopEnvironmentState } from '@/hooks/useDesktopEnvironment';
import { DesktopLocalStackPanel } from './DesktopLocalStackPanel';

function createState(overrides: Partial<DesktopEnvironmentState> = {}): DesktopEnvironmentState {
  return {
    isDesktop: true,
    backendUrl: 'http://localhost:8000',
    runtimeApiBaseUrl: 'http://localhost:8000',
    health: null,
    checkState: 'unreachable',
    environment: null,
    preferences: {
      backendUrl: 'http://localhost:8000',
      autoStartLocalStack: false,
      notificationsEnabled: false,
      autoCheckUpdates: true,
      updateChannel: 'stable',
    },
    releaseInfo: null,
    updateCheck: null,
    updateState: 'idle',
    updateError: null,
    stackStatus: null,
    stackProgress: null,
    desktopError: null,
    operationPending: false,
    setBackendUrl: vi.fn(),
    checkBackend: vi.fn(),
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
  };
}

describe('DesktopLocalStackPanel', () => {
  it('hides local Docker operations for a remote backend', () => {
    render(
      <DesktopLocalStackPanel
        desktop={createState({
          backendUrl: 'https://agenthub.example.com',
          runtimeApiBaseUrl: 'https://agenthub.example.com',
        })}
      />,
    );

    expect(screen.getByText('当前连接的是远程后端，本地 Docker 控制已隐藏。')).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: '启动' })).not.toBeInTheDocument();
  });

  it('persists the opt-in auto-start preference', () => {
    const updatePreferences = vi.fn(async () => undefined);
    render(
      <DesktopLocalStackPanel desktop={createState({ updatePreferences })} />,
    );

    fireEvent.click(screen.getByRole('checkbox'));

    expect(updatePreferences).toHaveBeenCalledWith({ autoStartLocalStack: true });
  });
});
