import { fireEvent, render, screen } from '@testing-library/react';
import { SettingsDialog } from './SettingsDialog';

describe('SettingsDialog', () => {
  it('shows runtime modes and closes', () => {
    const onClose = vi.fn();
    render(<SettingsDialog open onClose={onClose} />);

    expect(screen.getByText('API 模式')).toBeInTheDocument();
    expect(screen.getByText('SSE 模式')).toBeInTheDocument();
    expect(screen.getByText('Vite /api proxy')).toBeInTheDocument();

    fireEvent.click(screen.getByRole('button', { name: '关闭' }));

    expect(onClose).toHaveBeenCalled();
  });
});
