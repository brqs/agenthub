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
      saveBackendProfile,
      activateBackendProfile,
      deleteBackendProfile: vi.fn(async () => false),
    } as unknown as DesktopEnvironmentState);

    render(<DesktopBackendProfilesPanel />);
    fireEvent.click(screen.getByRole('button', { name: '添加' }));
    fireEvent.change(screen.getByPlaceholderText(/连接名称/), {
      target: { value: '公网 AgentHub' },
    });
    fireEvent.change(screen.getByPlaceholderText('https://agenthub.example.com'), {
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
});
