import { useState } from 'react';
import { useQueryClient } from '@tanstack/react-query';
import { extractApiError } from '@/lib/api';
import * as messagesAdapter from '@/lib/adapters/messages';
import { queryKeys } from '@/lib/queryKeys';
import { useAuthStore } from '@/stores/authStore';
import { useChatStore } from '@/stores/chatStore';

export function useTurnControlActions() {
  const [isPending, setIsPending] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const updateMessageLocal = useChatStore((state) => state.updateMessageLocal);
  const removeMessageLocal = useChatStore((state) => state.removeMessageLocal);
  const setActiveStreamInterrupting = useChatStore((state) => state.setActiveStreamInterrupting);
  const queryClient = useQueryClient();
  const userId = useAuthStore((state) => state.user?.id);

  async function run<T>(operation: () => Promise<T>) {
    setIsPending(true);
    setError(null);
    try {
      return await operation();
    } catch (err) {
      const message = extractApiError(err);
      setError(message);
      throw new Error(message);
    } finally {
      setIsPending(false);
    }
  }

  async function sendGuidance(activeMessageId: string, text: string) {
    return run(async () => {
      const response = await messagesAdapter.sendGuidance(activeMessageId, {
        content: [{ type: 'text', text }],
      });
      if (response.user_message) {
        updateMessageLocal(response.user_message);
        invalidateMessages(response.user_message.conversation_id);
      }
      return response;
    });
  }

  async function sendSideChat(activeMessageId: string, text: string) {
    return run(async () => {
      const response = await messagesAdapter.sendSideChat(activeMessageId, {
        content: [{ type: 'text', text }],
      });
      if (response.user_message) {
        updateMessageLocal(response.user_message);
      }
      if (response.agent_message) {
        updateMessageLocal(response.agent_message);
        invalidateMessages(response.agent_message.conversation_id);
      }
      return response;
    });
  }

  async function convertQueuedToGuidance(messageId: string) {
    return run(async () => {
      const response = await messagesAdapter.convertQueuedMessageToGuidance(messageId);
      if (response.user_message) {
        updateMessageLocal(response.user_message);
        invalidateMessages(response.user_message.conversation_id);
      }
      return response;
    });
  }

  async function stopAndRunQueuedMessage(messageId: string) {
    return run(async () => {
      const response = await messagesAdapter.stopAndRunQueuedMessage(messageId);
      updateMessageLocal(response.message);
      setActiveStreamInterrupting(response.message.id, response.state === 'interrupting');
      invalidateMessages(response.message.conversation_id);
      return response;
    });
  }

  async function reorderQueuedMessages(conversationId: string, messageIds: string[]) {
    return run(async () => {
      const response = await messagesAdapter.reorderQueuedMessages(conversationId, {
        message_ids: messageIds,
      });
      response.messages.forEach(updateMessageLocal);
      invalidateMessages(conversationId);
      return response;
    });
  }

  async function mergeQueuedMessages(conversationId: string, messageIds: string[]) {
    return run(async () => {
      const response = await messagesAdapter.mergeQueuedMessages(conversationId, {
        message_ids: messageIds,
      });
      updateMessageLocal(response.queued_message);
      messageIds
        .filter((messageId) => messageId !== response.queued_message.id)
        .forEach(removeMessageLocal);
      invalidateMessages(conversationId);
      return response;
    });
  }

  function invalidateMessages(conversationId: string) {
    void queryClient.invalidateQueries({ queryKey: queryKeys.messages(userId, conversationId) });
  }

  return {
    sendGuidance,
    sendSideChat,
    convertQueuedToGuidance,
    stopAndRunQueuedMessage,
    reorderQueuedMessages,
    mergeQueuedMessages,
    isPending,
    error,
  };
}
