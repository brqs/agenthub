import { reconcileConversationList } from './useUpdateConversation';
import type { Conversation } from '@/lib/types';

const baseConversation: Conversation = {
  id: 'conv-1',
  title: 'Backend Smoke',
  mode: 'single',
  agent_ids: ['claude-code'],
  is_pinned: false,
  is_archived: false,
  last_message_at: '2026-05-29T12:00:00.000Z',
  last_message_preview: 'hello',
  created_at: '2026-05-29T12:00:00.000Z',
};

describe('reconcileConversationList', () => {
  it('removes archived conversations from the active list', () => {
    const archived = { ...baseConversation, is_archived: true };

    expect(reconcileConversationList([baseConversation], archived, { archived: false })).toEqual([]);
  });

  it('adds archived conversations to the archive list', () => {
    const archived = { ...baseConversation, is_archived: true };

    expect(reconcileConversationList([], archived, { archived: true })).toEqual([archived]);
  });

  it('removes restored conversations from the archive list', () => {
    const archived = { ...baseConversation, is_archived: true };

    expect(reconcileConversationList([archived], baseConversation, { archived: true })).toEqual([]);
  });

  it('respects pinned and search filters', () => {
    expect(
      reconcileConversationList([], { ...baseConversation, is_pinned: true }, { pinnedOnly: true }),
    ).toHaveLength(1);
    expect(reconcileConversationList([], baseConversation, { search: 'missing' })).toEqual([]);
  });
});
