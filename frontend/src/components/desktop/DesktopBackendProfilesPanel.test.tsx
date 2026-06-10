import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { useDesktopEnvironment, type DesktopEnvironmentState } from '@/hooks/useDesktopEnvironment';
import { DesktopBackendProfilesPanel } from './DesktopBackendProfilesPanel';

vi.mock('@/hooks/useDesktopEnvironment', () => ({
  useDesktopEnvironment: vi.fn(),
}));

const useDesktopEnvironmentMock = vi.mocked(useDesktopEnvironment);

describe('DesktopBackendProfilesPanel', () => {
  it('adds and connects a public backend without a native select menu', async () => {
    const saveBackendProfile = vi.fn(async () => ({
      id: 'public',
      name: '公网 AgentHub',
      url: 'https://agenthub.example.com',
      mode: 'remote' as const,
    }));
    const activateBackendProfile = vi.fn(async () => true);
    useDesktopEnvironmentMock.mockReturnValue({
      backendProfiles: [
        {
          id: 'default',
          name: '本地 AgentHub',
          url: 'http://localhost:8000',
          mode: 'local',
        },
      ],
      activeBackendProfileId: 'default',
      checkBackend: vi.fn(),
      saveBackendProfile,
      activateBackendProfile,
      deleteBackendProfile: vi.fn(async () => false),
    } as unknown as DesktopEnvironmentState);

    render(<DesktopBackendProfilesPanel />);
    fireEvent.click(screen.getByRole('button', { name: '添加' }));
    fireEvent.change(screen.getByPlaceholderText(/连接名称/), {
      target: { value: '公网 AgentHub' },
    });
    fireEvent.change(screen.getByPlaceholderText(/agenthub\.example\.com/), {
      target: { value: 'https://agenthub.example.com' },
    });
    fireEvent.click(screen.getByRole('button', { name: '保存并连接' }));

    await waitFor(() => {
      expect(saveBackendProfile).toHaveBeenCalledWith({
        name: '公网 AgentHub',
        url: 'https://agenthub.example.com',
      });
      expect(activateBackendProfile).toHaveBeenCalledWith('public');
    });
  });

  it('shows a clear warning for plain HTTP remote backend profiles', () => {
    useDesktopEnvironmentMock.mockReturnValue({
      backendProfiles: [
        {
          id: 'public-http',
          name: '测试后端',
          url: 'http://111.229.151.159:8000',
          mode: 'remote',
        },
      ],
      activeBackendProfileId: 'default',
      checkBackend: vi.fn(),
      saveBackendProfile: vi.fn(),
      activateBackendProfile: vi.fn(),
      deleteBackendProfile: vi.fn(),
    } as unknown as DesktopEnvironmentState);

    render(<DesktopBackendProfilesPanel />);

    expect(screen.getByText(/HTTP 明文连接/)).toBeInTheDocument();
  });

  it('can test the active backend profile from the profile list', async () => {
    const checkBackend = vi.fn(async () => ({
      url: 'http://localhost:8000',
      reachable: true,
      status: 'ready' as const,
    }));
    useDesktopEnvironmentMock.mockReturnValue({
      backendProfiles: [
        {
          id: 'default',
          name: '本地 AgentHub',
          url: 'http://localhost:8000',
          mode: 'local',
        },
      ],
      activeBackendProfileId: 'default',
      checkBackend,
      saveBackendProfile: vi.fn(),
      activateBackendProfile: vi.fn(),
      deleteBackendProfile: vi.fn(),
    } as unknown as DesktopEnvironmentState);

    render(<DesktopBackendProfilesPanel />);
    fireEvent.click(screen.getByRole('button', { name: '测试' }));

    await waitFor(() => {
      expect(checkBackend).toHaveBeenCalledWith('http://localhost:8000');
    });
  });

  it('shows the latest connection error for the matching backend profile', () => {
    useDesktopEnvironmentMock.mockReturnValue({
      backendProfiles: [
        {
          id: 'public-http',
          name: '小易',
          url: 'http://111.229.151.159:8000',
          mode: 'remote',
          lastHealth: 'unreachable',
        },
      ],
      activeBackendProfileId: 'default',
      health: {
        url: 'http://111.229.151.159:8000',
        reachable: false,
        status: 'unreachable',
        error: '连接 AgentHub 后端超时，请检查服务器地址和网络。',
      },
      checkBackend: vi.fn(),
      saveBackendProfile: vi.fn(),
      activateBackendProfile: vi.fn(),
      deleteBackendProfile: vi.fn(),
    } as unknown as DesktopEnvironmentState);

    render(<DesktopBackendProfilesPanel />);

    expect(screen.getByText('连接 AgentHub 后端超时，请检查服务器地址和网络。')).toBeInTheDocument();
    expect(screen.queryByText('暂时无法连接')).not.toBeInTheDocument();
  });
});
