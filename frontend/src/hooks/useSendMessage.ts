import { useState } from 'react';
import { extractApiError } from '@/lib/api';
import * as messagesAdapter from '@/lib/adapters/messages';
import { useChatStore } from '@/stores/chatStore';
import type { RequirementAlignmentMode } from '@/lib/types';

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

export function resolveTargetAgentId(
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
  const [error, setError] = useState<string | null>(null);
  const appendRemoteExchange = useChatStore((state) => state.appendRemoteExchange);
  const startActiveStream = useChatStore((state) => state.startActiveStream);
  const conversations = useChatStore((state) => state.conversations);

  async function sendMessage(
    conversationId: string,
    text: string,
    attachmentIds: string[] = [],
    requirementAlignment: RequirementAlignmentMode = 'off',
  ): Promise<{ agentMessageId: string } | null> {
    setIsPending(true);
    setError(null);
    try {
      const conversation = conversations.find((c) => c.id === conversationId);
      const targetAgentId = conversation
        ? resolveTargetAgentId(text, conversation.mode, conversation.agent_ids)
        : null;

      const response = await messagesAdapter.sendMessage(conversationId, {
        content: [{ type: 'text', text }],
        target_agent_id: targetAgentId,
        requirement_alignment: requirementAlignment,
        ...(attachmentIds.length ? { attachment_ids: attachmentIds } : {}),
      } as messagesAdapter.SendMessageWithAttachments);
      appendRemoteExchange(conversationId, response.user_message, response.agent_message);
      startActiveStream(response.agent_message);
      return { agentMessageId: response.agent_message.id };
    } catch (err) {
      const message = extractApiError(err);
      setError(message);
      throw new Error(message);
    } finally {
      setIsPending(false);
    }
  }

  return { sendMessage, isPending, error };
}
