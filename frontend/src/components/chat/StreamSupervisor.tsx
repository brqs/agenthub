import { useEffect, useRef } from 'react';
import { useQueryClient } from '@tanstack/react-query';
import { useStream } from '@/hooks/useStream';
import { useDesktopEnvironment } from '@/hooks/useDesktopEnvironment';
import { showDesktopNotification } from '@/lib/desktopBridge';
import { queryKeys } from '@/lib/queryKeys';
import { useAuthStore } from '@/stores/authStore';
import { useChatStore } from '@/stores/chatStore';

export function StreamSupervisor() {
  const activeStreams = useChatStore((state) => state.activeStreams);
  const desktop = useDesktopEnvironment();
  const notificationsEnabled = Boolean(
    desktop.isDesktop && desktop.preferences?.notificationsEnabled,
  );
  return (
    <>
      {Object.values(activeStreams).map((stream) => (
        <StreamSubscription
          key={stream.messageId}
          stream={stream}
          notificationsEnabled={notificationsEnabled}
        />
      ))}
    </>
  );
}

function StreamSubscription({
  stream,
  notificationsEnabled,
}: {
  stream: {
    messageId: string;
    conversationId: string;
    agentId: string | null;
    startedAt: string;
  };
  notificationsEnabled: boolean;
}) {
  const queryClient = useQueryClient();
  const userId = useAuthStore((state) => state.user?.id);
  const applyStreamEvent = useChatStore((state) => state.applyStreamEvent);
  const finishActiveStream = useChatStore((state) => state.finishActiveStream);
  const toolNamesRef = useRef<Record<string, string>>({});

  useStream(stream.messageId, {
    onEvent: (event) => {
      applyStreamEvent(stream.messageId, event);
      if (event.event === 'tool_call') {
        toolNamesRef.current[event.data.call_id] = event.data.tool_name;
      }
      if (event.event === 'tool_result') {
        const toolName = toolNamesRef.current[event.data.call_id];
        if (isWorkspaceWritingTool(toolName)) {
          invalidateWorkspaceQueries(queryClient, stream.conversationId);
        }
        delete toolNamesRef.current[event.data.call_id];
      }
    },
    onDone: () => {
      notifyDesktopTerminal(stream, notificationsEnabled, 'done');
      finishActiveStream(stream.messageId);
      invalidateConversationQueries(queryClient, userId, stream.conversationId);
    },
    onInterrupted: () => {
      finishActiveStream(stream.messageId);
      invalidateConversationQueries(queryClient, userId, stream.conversationId);
    },
    onError: () => {
      applyStreamEvent(stream.messageId, {
        event: 'error',
        data: { error: 'Agent 回复失败，请重试这条消息。' },
      });
      notifyDesktopTerminal(stream, notificationsEnabled, 'error');
      finishActiveStream(stream.messageId);
      invalidateConversationQueries(queryClient, userId, stream.conversationId);
    },
    onTransportError: () => {
      finishActiveStream(stream.messageId);
      invalidateConversationQueries(queryClient, userId, stream.conversationId);
    },
  });

  useEffect(() => {
    toolNamesRef.current = {};
  }, [stream.messageId]);

  return null;
}

const notifiedTerminalMessages = new Set<string>();

function notifyDesktopTerminal(
  stream: {
    messageId: string;
    conversationId: string;
    agentId: string | null;
  },
  notificationsEnabled: boolean,
  terminal: 'done' | 'error',
) {
  if (!notificationsEnabled) return;
  const state = useChatStore.getState();
  const sameConversationVisible = isDesktopConversationForeground(
    stream.conversationId,
    state.selectedConversationId,
    document.visibilityState,
    document.hasFocus(),
  );
  if (sameConversationVisible) return;

  const message = state.messagesByConversation[stream.conversationId]?.find(
    (item) => item.id === stream.messageId,
  );
  const kind = resolveDesktopNotificationKind(message?.content ?? [], terminal);
  const dedupeKey = `${stream.messageId}:${kind}`;
  if (notifiedTerminalMessages.has(dedupeKey)) return;
  notifiedTerminalMessages.add(dedupeKey);
  while (notifiedTerminalMessages.size > 1_000) {
    const oldest = notifiedTerminalMessages.values().next().value;
    if (!oldest) break;
    notifiedTerminalMessages.delete(oldest);
  }

  void showDesktopNotification({
    notificationId: createNotificationId(),
    conversationId: stream.conversationId,
    kind,
    agentLabel: formatAgentLabel(stream.agentId),
  }).catch(() => {
    notifiedTerminalMessages.delete(dedupeKey);
  });
}

export function isDesktopConversationForeground(
  conversationId: string,
  selectedConversationId: string,
  visibilityState: DocumentVisibilityState,
  hasFocus: boolean,
): boolean {
  return (
    visibilityState === 'visible' &&
    hasFocus &&
    selectedConversationId === conversationId
  );
}

export function resolveDesktopNotificationKind(
  content: Array<{ type: string; status?: string }>,
  terminal: 'done' | 'error',
): 'done' | 'error' | 'attention' {
  if (terminal === 'error') return 'error';
  return content.some(
    (block) => block.type === 'clarification' && block.status === 'waiting',
  )
    ? 'attention'
    : 'done';
}

function createNotificationId(): string {
  if (typeof crypto !== 'undefined' && typeof crypto.randomUUID === 'function') {
    return crypto.randomUUID();
  }
  const bytes = new Uint8Array(16);
  if (typeof crypto !== 'undefined' && typeof crypto.getRandomValues === 'function') {
    crypto.getRandomValues(bytes);
  } else {
    for (let index = 0; index < bytes.length; index += 1) {
      bytes[index] = Math.floor(Math.random() * 256);
    }
  }
  bytes[6] = (bytes[6] & 0x0f) | 0x40;
  bytes[8] = (bytes[8] & 0x3f) | 0x80;
  const hex = Array.from(bytes, (value) => value.toString(16).padStart(2, '0')).join('');
  return `${hex.slice(0, 8)}-${hex.slice(8, 12)}-${hex.slice(12, 16)}-${hex.slice(16, 20)}-${hex.slice(20)}`;
}

function formatAgentLabel(agentId: string | null): string {
  if (!agentId) return 'AgentHub';
  return agentId
    .split('-')
    .filter(Boolean)
    .map((part) => `${part.slice(0, 1).toUpperCase()}${part.slice(1)}`)
    .join(' ');
}

function invalidateConversationQueries(
  queryClient: ReturnType<typeof useQueryClient>,
  userId: string | null | undefined,
  conversationId: string,
) {
  void queryClient.invalidateQueries({ queryKey: queryKeys.messages(userId, conversationId) });
  invalidateWorkspaceQueries(queryClient, conversationId);
  void queryClient.invalidateQueries({ queryKey: ['workspace-deployments', conversationId] });
}

function invalidateWorkspaceQueries(
  queryClient: ReturnType<typeof useQueryClient>,
  conversationId: string,
) {
  void queryClient.invalidateQueries({ queryKey: ['workspace-tree', conversationId] });
}

export function isWorkspaceWritingTool(toolName: string | undefined): boolean {
  if (!toolName) return false;
  const normalized = toolName.toLowerCase().replace(/[-\s]+/g, '_');
  const terminalSegment = normalized.split('.').pop() ?? normalized;
  return [
    'write',
    'edit',
    'write_file',
    'create_file',
    'delete_file',
    'save_file',
    'replace_file',
  ].includes(terminalSegment);
}
