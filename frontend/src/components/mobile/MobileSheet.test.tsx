import { fireEvent, render, screen } from '@testing-library/react';
import { MobileSheet } from './MobileSheet';

describe('MobileSheet', () => {
  it('closes a drawer from its backdrop', () => {
    const onClose = vi.fn();
    render(
      <MobileSheet open variant="drawer" onClose={onClose}>
        <div>会话列表</div>
      </MobileSheet>,
    );

    fireEvent.click(screen.getByRole('button', { name: '关闭浮层' }));

    expect(onClose).toHaveBeenCalledOnce();
  });

  it('closes from the escape key', () => {
    const onClose = vi.fn();
    render(
      <MobileSheet open onClose={onClose}>
        <div>工作台</div>
      </MobileSheet>,
    );

    fireEvent.keyDown(window, { key: 'Escape' });

    expect(onClose).toHaveBeenCalledOnce();
  });

  it('does not render closed content', () => {
    render(
      <MobileSheet open={false} onClose={vi.fn()}>
        <div>隐藏内容</div>
      </MobileSheet>,
    );

    expect(screen.queryByText('隐藏内容')).not.toBeInTheDocument();
  });
});
