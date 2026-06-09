import { resolveConversation, resolveMessageConversationId } from './chatPageUtils';
import type { Conversation } from '@/lib/types';

const remoteConversation: Conversation = {
  id: 'ef869a86-e4b2-459f-a5c2-03a0c34e4384',
  title: 'Remote conversation',
  mode: 'group',
  agent_ids: ['orchestrator'],
  is_pinned: false,
  is_archived: false,
  last_message_at: '2026-05-31T00:00:00.000Z',
  last_message_preview: null,
  created_at: '2026-05-31T00:00:00.000Z',
};

const mockConversation: Conversation = {
  ...remoteConversation,
  id: 'conv-discord-shell',
  title: 'Mock conversation',
};

describe('resolveConversation', () => {
  it('does not replace an unresolved deep link with the first mock conversation', () => {
    expect(
      resolveConversation(
        [mockConversation],
        remoteConversation.id,
        mockConversation.id,
      ),
    ).toBeUndefined();
  });

  it('resolves the deep link after the remote conversation list hydrates', () => {
    expect(
      resolveConversation(
        [remoteConversation],
        remoteConversation.id,
        mockConversation.id,
      ),
    ).toEqual(remoteConversation);
  });

  it('falls back to the first visible conversation when opening the chat root', () => {
    expect(resolveConversation([remoteConversation], undefined, '')).toEqual(remoteConversation);
  });
});

describe('resolveMessageConversationId', () => {
  it('uses the deep link id instead of a previously selected conversation id', () => {
    expect(resolveMessageConversationId(remoteConversation.id, mockConversation.id)).toBe(
      remoteConversation.id,
    );
  });

  it('uses the resolved conversation id when opening the chat root', () => {
    expect(resolveMessageConversationId(undefined, remoteConversation.id)).toBe(
      remoteConversation.id,
    );
  });
});
