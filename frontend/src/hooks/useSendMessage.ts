import { useState } from 'react';
import * as messagesAdapter from '@/lib/adapters/messages';
import { env } from '@/lib/env';
import { useChatStore } from '@/stores/chatStore';

/** Parse `@agent-id` from group-chat input. Returns null for single chat or no mention. */
function parseMentionedAgent(
  text: string,
  mode: 'single' | 'group',
  agentIds: string[],
): string | null {
  if (mode !== 'group') return null;
  const lower = text.toLowerCase();
  return agentIds.find((id) => lower.includes(`@${id.toLowerCase()}`)) ?? null;
}

function resolveTargetAgentId(
  text: string,
  mode: 'single' | 'group',
  agentIds: string[],
): string | null {
  if (mode !== 'group') return null;
  return (
    parseMentionedAgent(text, mode, agentIds) ??
    (agentIds.includes('orchestrator') ? 'orchestrator' : agentIds[0] ?? null)
  );
}

export function useSendMessage() {
  const [isPending, setIsPending] = useState(false);
  const createPendingExchange = useChatStore((state) => state.createPendingExchange);
  const appendRemoteExchange = useChatStore((state) => state.appendRemoteExchange);
  const conversations = useChatStore((state) => state.conversations);

  async function sendMessage(
    conversationId: string,
    text: string,
  ): Promise<{ agentMessageId: string } | null> {
    setIsPending(true);
    try {
      if (env.useMockApi) {
        await new Promise((resolve) => window.setTimeout(resolve, 120));
        return createPendingExchange(conversationId, text);
      }

      const conversation = conversations.find((c) => c.id === conversationId);
      const targetAgentId = conversation
        ? resolveTargetAgentId(text, conversation.mode, conversation.agent_ids)
        : null;

      const response = await messagesAdapter.sendMessage(conversationId, {
        content: [{ type: 'text', text }],
        target_agent_id: targetAgentId,
      });
      appendRemoteExchange(conversationId, response.user_message, response.agent_message);
      return { agentMessageId: response.agent_message.id };
    } finally {
      setIsPending(false);
    }
  }

  return { sendMessage, isPending };
}
