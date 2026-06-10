import { render, screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { useDesktopEnvironment, type DesktopEnvironmentState } from '@/hooks/useDesktopEnvironment';
import { LoginPage } from './LoginPage';

vi.mock('@/components/desktop/DesktopBackendProfilesPanel', () => ({
  DesktopBackendProfilesPanel: ({ compact }: { compact?: boolean }) => (
    <div data-compact={compact ? 'true' : 'false'} data-testid="backend-profiles-panel" />
  ),
}));

vi.mock('@/hooks/useDesktopEnvironment', () => ({
  useDesktopEnvironment: vi.fn(),
}));

const useDesktopEnvironmentMock = vi.mocked(useDesktopEnvironment);

function renderLogin() {
  render(
    <MemoryRouter>
      <LoginPage />
    </MemoryRouter>,
  );
}

function desktopState(overrides: Partial<DesktopEnvironmentState> = {}) {
  return {
    isDesktop: true,
    runtimeApiBaseUrl: 'http://111.229.151.159:8000',
    checkState: 'ready',
    ...overrides,
  } as DesktopEnvironmentState;
}

describe('LoginPage desktop backend selector', () => {
  it('shows backend profile controls before login in desktop mode', () => {
    useDesktopEnvironmentMock.mockReturnValue(desktopState());

    renderLogin();

    expect(screen.getByText('后端连接')).toBeInTheDocument();
    expect(screen.getByText('当前：http://111.229.151.159:8000')).toBeInTheDocument();
    expect(screen.getByText('已连接')).toBeInTheDocument();
    expect(screen.getByTestId('backend-profiles-panel')).toHaveAttribute('data-compact', 'true');
  });

  it('keeps the web login page free of desktop backend controls', () => {
    useDesktopEnvironmentMock.mockReturnValue(desktopState({ isDesktop: false }));

    renderLogin();

    expect(screen.queryByText('后端连接')).not.toBeInTheDocument();
    expect(screen.queryByTestId('backend-profiles-panel')).not.toBeInTheDocument();
  });
});
