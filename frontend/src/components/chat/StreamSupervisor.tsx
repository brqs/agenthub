import { useEffect, useRef } from 'react';
import { useQueryClient } from '@tanstack/react-query';
import { useStream } from '@/hooks/useStream';
import { queryKeys } from '@/lib/queryKeys';
import { useAuthStore } from '@/stores/authStore';
import { useChatStore } from '@/stores/chatStore';

export function StreamSupervisor() {
  const activeStreams = useChatStore((state) => state.activeStreams);
  return (
    <>
      {Object.values(activeStreams).map((stream) => (
        <StreamSubscription key={stream.messageId} stream={stream} />
      ))}
    </>
  );
}

function StreamSubscription({
  stream,
}: {
  stream: {
    messageId: string;
    conversationId: string;
    agentId: string | null;
    startedAt: string;
  };
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
      finishActiveStream(stream.messageId);
      invalidateConversationQueries(queryClient, userId, stream.conversationId);
    },
    onError: () => {
      applyStreamEvent(stream.messageId, {
        event: 'error',
        data: { error: 'Agent 回复失败，请重试这条消息。' },
      });
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

function isWorkspaceWritingTool(toolName: string | undefined): boolean {
  if (!toolName) return false;
  const normalized = toolName.toLowerCase();
  return normalized.includes('write') || normalized.includes('file');
}
