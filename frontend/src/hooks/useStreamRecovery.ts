import { useEffect, useRef } from 'react';
import * as messagesAdapter from '@/lib/adapters/messages';
import { useAuthStore } from '@/stores/authStore';
import { useChatStore } from '@/stores/chatStore';

const RECOVERY_MESSAGE_LIMIT = 30;

export function useStreamRecovery() {
  const userId = useAuthStore((state) => state.user?.id);
  const conversations = useChatStore((state) => state.conversations);
  const hydrateMessages = useChatStore((state) => state.hydrateMessages);
  const scannedRef = useRef<Set<string>>(new Set());
  const userRef = useRef<string | null | undefined>(undefined);

  useEffect(() => {
    if (userRef.current !== userId) {
      userRef.current = userId;
      scannedRef.current = new Set();
    }
  }, [userId]);

  useEffect(() => {
    if (!userId) return;
    for (const conversation of conversations) {
      if (conversation.is_archived) continue;
      if (scannedRef.current.has(conversation.id)) continue;
      scannedRef.current.add(conversation.id);
      void messagesAdapter
        .listMessages(conversation.id, {
          limit: RECOVERY_MESSAGE_LIMIT,
          direction: 'before',
        })
        .then((page) => {
          if (userRef.current !== userId) return;
          hydrateMessages(conversation.id, page.items);
        })
        .catch(() => {
          scannedRef.current.delete(conversation.id);
        });
    }
  }, [conversations, hydrateMessages, userId]);
}
