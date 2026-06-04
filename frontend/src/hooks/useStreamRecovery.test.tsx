import { renderHook, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import * as messagesAdapter from '@/lib/adapters/messages';
import { useAuthStore } from '@/stores/authStore';
import { useChatStore } from '@/stores/chatStore';
import { useStreamRecovery } from './useStreamRecovery';

vi.mock('@/lib/adapters/messages', () => ({
  listMessages: vi.fn(),
}));

const listMessagesMock = vi.mocked(messagesAdapter.listMessages);

describe('useStreamRecovery', () => {
  beforeEach(() => {
    useChatStore.getState().clearChat();
    useAuthStore.getState().logout();
    listMessagesMock.mockReset();
  });

  it('scans visible conversations and recovers pending or streaming agent messages', async () => {
    listMessagesMock.mockResolvedValue({
      hasMore: false,
      nextCursor: null,
      items: [
        {
          id: 'msg-stream',
          conversation_id: 'conv-a',
          role: 'agent',
          agent_id: 'claude-code',
          reply_to_id: null,
          status: 'streaming',
          is_pinned: false,
          created_at: '2026-06-04T00:00:00.000Z',
          content: [],
        },
      ],
    });
    useAuthStore.getState().setAuth('token', {
      id: 'user-1',
      username: 'tester',
      created_at: '2026-06-04T00:00:00.000Z',
    });
    useChatStore.getState().hydrateConversations([
      {
        id: 'conv-a',
        title: 'A',
        mode: 'single',
        agent_ids: ['claude-code'],
        created_at: '2026-06-04T00:00:00.000Z',
        last_message_at: '2026-06-04T00:00:00.000Z',
        last_message_preview: null,
        is_pinned: false,
        is_archived: false,
      },
    ]);

    renderHook(() => useStreamRecovery());

    await waitFor(() => {
      expect(useChatStore.getState().activeStreams['msg-stream']).toMatchObject({
        conversationId: 'conv-a',
        agentId: 'claude-code',
      });
    });
    expect(listMessagesMock).toHaveBeenCalledTimes(1);
    expect(listMessagesMock).toHaveBeenCalledWith('conv-a', {
      limit: 30,
      direction: 'before',
    });
  });

  it('does not rescan the same visible conversation after rerender', async () => {
    listMessagesMock.mockResolvedValue({
      hasMore: false,
      nextCursor: null,
      items: [],
    });
    useAuthStore.getState().setAuth('token', {
      id: 'user-1',
      username: 'tester',
      created_at: '2026-06-04T00:00:00.000Z',
    });
    useChatStore.getState().hydrateConversations([
      {
        id: 'conv-a',
        title: 'A',
        mode: 'single',
        agent_ids: ['claude-code'],
        created_at: '2026-06-04T00:00:00.000Z',
        last_message_at: '2026-06-04T00:00:00.000Z',
        last_message_preview: null,
        is_pinned: false,
        is_archived: false,
      },
    ]);

    const { rerender } = renderHook(() => useStreamRecovery());
    rerender();

    await waitFor(() => expect(listMessagesMock).toHaveBeenCalledTimes(1));
  });
});
