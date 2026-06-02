import { fireEvent, render, screen } from '@testing-library/react';
import { UserMenu } from './UserMenu';

describe('UserMenu', () => {
  it('shows current user and logs out', () => {
    const onLogout = vi.fn();
    const onClose = vi.fn();

    render(
      <UserMenu
        user={{ id: 'u1', username: 'frontend-demo', avatar_url: null, created_at: new Date().toISOString() }}
        onLogout={onLogout}
        onClose={onClose}
      />,
    );

    expect(screen.getByText('frontend-demo')).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: '退出登录' }));

    expect(onClose).toHaveBeenCalled();
    expect(onLogout).toHaveBeenCalled();
  });

  it('closes from the mobile close action', () => {
    const onClose = vi.fn();
    render(<UserMenu user={null} onLogout={vi.fn()} onClose={onClose} />);

    fireEvent.click(screen.getByRole('button', { name: '关闭账号菜单' }));

    expect(onClose).toHaveBeenCalledOnce();
  });
});
