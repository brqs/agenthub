import { queryClient } from '@/lib/queryClient';
import { queryKeys } from '@/lib/queryKeys';
import { resetClientSession, startClientSession } from '@/lib/session';
import type { User } from '@/lib/types';
import { useAgentStore } from '@/stores/agentStore';
import { useAuthStore } from '@/stores/authStore';
import { useChatStore } from '@/stores/chatStore';

const userA: User = {
  id: '00000000-0000-4000-8000-0000000000a1',
  username: 'account-a',
  avatar_url: null,
  created_at: '2026-05-27T00:00:00.000Z',
};

const userB: User = {
  id: '00000000-0000-4000-8000-0000000000b1',
  username: 'account-b',
  avatar_url: null,
  created_at: '2026-05-27T00:00:00.000Z',
};

describe('session state reset', () => {
  beforeEach(() => {
    queryClient.clear();
    useAuthStore.setState({ token: null, user: null });
    useAgentStore.getState().clearAgents();
    useChatStore.getState().clearChat();
  });

  it('scopes query keys by session identity', () => {
    expect(queryKeys.authMe('token-a')).not.toEqual(queryKeys.authMe('token-b'));
    expect(queryKeys.agents(userA.id)).not.toEqual(queryKeys.agents(userB.id));
    expect(queryKeys.conversations(userA.id)).not.toEqual(queryKeys.conversations(userB.id));
    expect(queryKeys.messages(userA.id, 'conv-1')).not.toEqual(
      queryKeys.messages(userB.id, 'conv-1'),
    );
  });

  it('clears query cache before starting a new session', () => {
    queryClient.setQueryData(queryKeys.authMe('token-a'), userA);
    queryClient.setQueryData(queryKeys.agents(userA.id), [{ id: 'old-agent' }]);
    queryClient.setQueryData(queryKeys.conversations(userA.id), [{ id: 'old-conv' }]);
    queryClient.setQueryData(queryKeys.messages(userA.id, 'conv-1'), [{ id: 'old-message' }]);

    startClientSession('token-b', userB);

    expect(queryClient.getQueryCache().getAll()).toHaveLength(0);
    expect(useAuthStore.getState()).toMatchObject({ token: 'token-b', user: userB });
  });

  it('clears auth and resets user-facing stores on logout', () => {
    useAuthStore.getState().setAuth('token-a', userA);
    useAgentStore.getState().hydrateAgents([
      {
        id: 'old-agent',
        name: 'Old Agent',
        provider: 'builtin',
        avatar_url: '',
        capabilities: [],
        system_prompt: null,
        config: {},
        is_builtin: false,
        created_at: '2026-05-27T00:00:00.000Z',
      },
    ]);
    useChatStore.getState().hydrateConversations([
      {
        id: 'old-conv',
        title: 'Old Conversation',
        mode: 'single',
        agent_ids: ['old-agent'],
        is_pinned: false,
        is_archived: false,
        last_message_at: '2026-05-27T00:00:00.000Z',
        last_message_preview: null,
        created_at: '2026-05-27T00:00:00.000Z',
      },
    ]);
    queryClient.setQueryData(queryKeys.agents(userA.id), [{ id: 'old-agent' }]);

    resetClientSession();

    expect(useAuthStore.getState()).toMatchObject({ token: null, user: null });
    expect(queryClient.getQueryCache().getAll()).toHaveLength(0);
    expect(useAgentStore.getState().agents).toEqual([]);
    expect(useChatStore.getState().conversations).toEqual([]);
  });
});
