import { useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import {
  isDesktopRuntime,
  listenForDesktopDeepLinkActivation,
  listenForDesktopNotificationActivation,
} from '@/lib/desktopBridge';
import { useAuthStore } from '@/stores/authStore';
import { useChatStore } from '@/stores/chatStore';

export function DesktopNativeEventBridge() {
  const navigate = useNavigate();

  useEffect(() => {
    if (!isDesktopRuntime()) return undefined;
    const goToConversation = (conversationId: string) => {
      if (!useAuthStore.getState().token) return;
      useChatStore.getState().setSelectedConversationId(conversationId);
      navigate(`/chat/${conversationId}`);
    };
    let disposed = false;
    let notificationUnlisten: (() => void) | undefined;
    let deepLinkUnlisten: (() => void) | undefined;
    listenForDesktopNotificationActivation(({ conversationId }) => {
      goToConversation(conversationId);
    })
      .then((nextUnlisten) => {
        if (disposed) {
          nextUnlisten();
          return;
        }
        notificationUnlisten = nextUnlisten;
      })
      .catch(() => undefined);
    listenForDesktopDeepLinkActivation((activation) => {
      goToConversation(activation.conversationId);
    })
      .then((nextUnlisten) => {
        if (disposed) {
          nextUnlisten();
          return;
        }
        deepLinkUnlisten = nextUnlisten;
      })
      .catch(() => undefined);
    return () => {
      disposed = true;
      notificationUnlisten?.();
      deepLinkUnlisten?.();
    };
  }, [navigate]);

  return null;
}
