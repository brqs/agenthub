import { fireEvent, render, screen } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { SettingsDialog } from './SettingsDialog';
import { env } from '@/lib/env';

describe('SettingsDialog', () => {
  it('shows runtime modes and closes', () => {
    const onClose = vi.fn();
    const queryClient = new QueryClient({
      defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
    });

    render(
      <QueryClientProvider client={queryClient}>
        <SettingsDialog open onClose={onClose} />
      </QueryClientProvider>,
    );

    expect(screen.getByText('API 模式')).toBeInTheDocument();
    expect(screen.getByText('SSE 模式')).toBeInTheDocument();
    expect(screen.getByText('后端地址')).toBeInTheDocument();
    expect(screen.getByText(env.apiBaseUrl || 'Vite /api 代理')).toBeInTheDocument();

    fireEvent.click(screen.getByRole('button', { name: '关闭' }));

    expect(onClose).toHaveBeenCalled();
  });
});
