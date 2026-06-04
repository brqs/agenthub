import { fireEvent, render, screen } from '@testing-library/react';
import { MessageList } from './MessageList';
import type { DemoMessage } from '@/lib/mockData';

const message: DemoMessage = {
  id: '00000000-0000-4000-8000-000000000001',
  conversation_id: 'conv-1',
  role: 'user',
  agent_id: null,
  reply_to_id: null,
  status: 'done',
  is_pinned: false,
  created_at: '2026-05-31T00:00:00.000Z',
  content: [{ type: 'text', text: 'hello' }],
};

describe('MessageList', () => {
  it('shows a load older messages control when more history exists', () => {
    const onLoadMore = vi.fn();

    render(<MessageList messages={[message]} hasMore onLoadMore={onLoadMore} />);

    fireEvent.click(screen.getByRole('button', { name: '加载更早消息' }));

    expect(onLoadMore).toHaveBeenCalledOnce();
  });
});
