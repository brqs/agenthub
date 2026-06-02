import { fireEvent, render, screen } from '@testing-library/react';
import { OfflineBanner } from './OfflineBanner';

describe('OfflineBanner', () => {
  it('renders nothing while online without an update', () => {
    const { container } = render(
      <OfflineBanner isOnline updateAvailable={false} onApplyUpdate={vi.fn()} />,
    );

    expect(container).toBeEmptyDOMElement();
  });

  it('shows an offline notice', () => {
    render(<OfflineBanner isOnline={false} updateAvailable={false} onApplyUpdate={vi.fn()} />);

    expect(screen.getByRole('status')).toHaveTextContent('当前离线，已加载内容仍可查看。');
  });

  it('applies an available update', () => {
    const onApplyUpdate = vi.fn();
    render(<OfflineBanner isOnline updateAvailable onApplyUpdate={onApplyUpdate} />);

    fireEvent.click(screen.getByRole('button', { name: '刷新更新' }));

    expect(onApplyUpdate).toHaveBeenCalledOnce();
  });
});
