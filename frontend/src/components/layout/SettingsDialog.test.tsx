import { fireEvent, render, screen } from '@testing-library/react';
import { SettingsDialog } from './SettingsDialog';
import { env } from '@/lib/env';

describe('SettingsDialog', () => {
  it('shows runtime modes and closes', () => {
    const onClose = vi.fn();
    render(<SettingsDialog open onClose={onClose} />);

    expect(screen.getByText('API 模式')).toBeInTheDocument();
    expect(screen.getByText('SSE 模式')).toBeInTheDocument();
    expect(screen.getByText('Base URL')).toBeInTheDocument();
    expect(screen.getByText(env.apiBaseUrl || 'Vite /api proxy')).toBeInTheDocument();

    fireEvent.click(screen.getByRole('button', { name: '关闭' }));

    expect(onClose).toHaveBeenCalled();
  });
});
