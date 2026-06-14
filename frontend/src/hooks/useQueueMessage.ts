import { useState } from 'react';
import { extractApiError } from '@/lib/api';
import * as messagesAdapter from '@/lib/adapters/messages';
import { useChatStore } from '@/stores/chatStore';
import { resolveTargetAgentId } from './useSendMessage';
import type { RequirementAlignmentMode } from '@/lib/types';

export function useQueueMessage() {
  const [isPending, setIsPending] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const appendQueuedMessage = useChatStore((state) => state.appendQueuedMessage);
  const updateMessageLocal = useChatStore((state) => state.updateMessageLocal);
  const removeMessageLocal = useChatStore((state) => state.removeMessageLocal);
  const conversations = useChatStore((state) => state.conversations);

  async function queueMessage(
    conversationId: string,
    text: string,
    attachmentIds: string[] = [],
    requirementAlignment: RequirementAlignmentMode = 'off',
  ) {
    setIsPending(true);
    setError(null);
    try {
      const conversation = conversations.find((c) => c.id === conversationId);
      const targetAgentId = conversation
        ? resolveTargetAgentId(
            text,
            conversation.mode,
            conversation.agent_ids,
            requirementAlignment,
          )
        : null;
      const response = await messagesAdapter.queueMessage(conversationId, {
        content: [{ type: 'text', text }],
        target_agent_id: targetAgentId,
        requirement_alignment: requirementAlignment,
        ...(attachmentIds.length ? { attachment_ids: attachmentIds } : {}),
      } as messagesAdapter.QueueMessageWithAttachments);
      appendQueuedMessage(conversationId, response.queued_message);
      return response;
    } catch (err) {
      const message = extractApiError(err);
      setError(message);
      throw new Error(message);
    } finally {
      setIsPending(false);
    }
  }

  async function updateQueuedMessage(
    messageId: string,
    text: string,
    requirementAlignment?: RequirementAlignmentMode,
  ) {
    setIsPending(true);
    setError(null);
    try {
      const response = await messagesAdapter.updateQueuedMessage(messageId, {
        content: [{ type: 'text', text }],
        ...(requirementAlignment ? { requirement_alignment: requirementAlignment } : {}),
      });
      updateMessageLocal(response.queued_message);
      return response;
    } catch (err) {
      const message = extractApiError(err);
      setError(message);
      throw new Error(message);
    } finally {
      setIsPending(false);
    }
  }

  async function deleteQueuedMessage(messageId: string) {
    setIsPending(true);
    setError(null);
    try {
      await messagesAdapter.deleteQueuedMessage(messageId);
      removeMessageLocal(messageId);
    } catch (err) {
      const message = extractApiError(err);
      setError(message);
      throw new Error(message);
    } finally {
      setIsPending(false);
    }
  }

  return {
    queueMessage,
    updateQueuedMessage,
    deleteQueuedMessage,
    isPending,
    error,
  };
}
