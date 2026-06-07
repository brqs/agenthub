import { fireEvent, render, screen, waitFor } from '@testing-library/react';
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

  it('sends queue reorder and merge actions with the current queue order', async () => {
    const onReorderQueuedMessages = vi.fn();
    const onMergeQueuedMessages = vi.fn();
    const queuedA: DemoMessage = {
      ...message,
      id: '00000000-0000-4000-8000-000000000101',
      status: 'queued',
      queue_position: 0,
      content: [{ type: 'text', text: 'first queued' }],
    };
    const queuedB: DemoMessage = {
      ...message,
      id: '00000000-0000-4000-8000-000000000102',
      status: 'queued',
      queue_position: 1,
      created_at: '2026-05-31T00:00:01.000Z',
      content: [{ type: 'text', text: 'second queued' }],
    };

    render(
      <MessageList
        messages={[queuedA, queuedB]}
        onReorderQueuedMessages={onReorderQueuedMessages}
        onMergeQueuedMessages={onMergeQueuedMessages}
      />,
    );

    fireEvent.click(screen.getByRole('button', { name: 'Move queued message down' }));
    await waitFor(() => {
      expect(onReorderQueuedMessages).toHaveBeenCalledWith('conv-1', [queuedB.id, queuedA.id]);
    });

    fireEvent.click(screen.getByRole('button', { name: 'Move queued message up' }));
    await waitFor(() => {
      expect(onReorderQueuedMessages).toHaveBeenCalledWith('conv-1', [queuedB.id, queuedA.id]);
    });

    fireEvent.click(screen.getByRole('button', { name: 'Merge queued message with previous' }));
    await waitFor(() => {
      expect(onMergeQueuedMessages).toHaveBeenCalledWith('conv-1', [queuedA.id, queuedB.id]);
    });
  });
});
