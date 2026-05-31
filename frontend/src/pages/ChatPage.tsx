import { useEffect, useRef, useState } from 'react';
import { MessageSquarePlus } from 'lucide-react';
import { useQueryClient } from '@tanstack/react-query';
import { useNavigate, useParams } from 'react-router-dom';
import { RightAgentPanel } from '@/components/agents/RightAgentPanel';
import { ChatHeader } from '@/components/chat/ChatHeader';
import { MessageInput } from '@/components/chat/MessageInput';
import { MessageList } from '@/components/chat/MessageList';
import { StreamingStatusBar } from '@/components/chat/StreamingStatusBar';
import { NewConversationDialog } from '@/components/conversation/NewConversationDialog';
import { ConversationSidebar } from '@/components/conversation/ConversationSidebar';
import { useAgents } from '@/hooks/useAgents';
import { useCreateConversation } from '@/hooks/useCreateConversation';
import { useConversations } from '@/hooks/useConversations';
import { useMessages } from '@/hooks/useMessages';
import { useRegenerateMessage } from '@/hooks/useRegenerateMessage';
import { useSendMessage } from '@/hooks/useSendMessage';
import { useStream } from '@/hooks/useStream';
import { useUpdateConversation } from '@/hooks/useUpdateConversation';
import { useUpdateMessage } from '@/hooks/useUpdateMessage';
import type { Agent } from '@/lib/types';
import { resolveConversation } from '@/pages/chatPageUtils';
import { useChatStore } from '@/stores/chatStore';
import { useUiStore } from '@/stores/uiStore';

export function ChatPage() {
  const { conversationId } = useParams<{ conversationId?: string }>();
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const [streamingMessageId, setStreamingMessageId] = useState<string | null>(null);
  const streamingToolNamesRef = useRef<Record<string, string>>({});
  const [newConversationOpen, setNewConversationOpen] = useState(false);
  const [mentionInsertRequest, setMentionInsertRequest] = useState<{
    agentId: string;
    requestId: number;
  } | null>(null);
  const { data: conversations, isLoading: conversationsLoading } = useConversations();
  const { data: agents } = useAgents();
  const createConversation = useCreateConversation();
  const selectedConversationId = useChatStore((state) => state.selectedConversationId);
  const search = useChatStore((state) => state.search);
  const setSearch = useChatStore((state) => state.setSearch);
  const setSelectedConversationId = useChatStore((state) => state.setSelectedConversationId);
  const highlightedMessageId = useChatStore((state) => state.highlightedMessageId);
  const applyStreamEvent = useChatStore((state) => state.applyStreamEvent);
  const setHighlightedMessageId = useChatStore((state) => state.setHighlightedMessageId);
  const conversationSidebarCollapsed = useUiStore((state) => state.conversationSidebarCollapsed);
  const rightPanelOpen = useUiStore((state) => state.rightPanelOpen);
  const rightPanelWidth = useUiStore((state) => state.rightPanelWidth);
  const setConversationSidebarCollapsed = useUiStore((state) => state.setConversationSidebarCollapsed);
  const setRightPanelOpen = useUiStore((state) => state.setRightPanelOpen);
  const setRightPanelWidth = useUiStore((state) => state.setRightPanelWidth);
  const { sendMessage, isPending: sendingMessage } = useSendMessage();

  const visibleConversations = conversations.filter((item) => !item.is_archived);
  const conversation = resolveConversation(
    visibleConversations,
    conversationId,
    selectedConversationId,
  );
  const { data: messages, isLoading: messagesLoading } = useMessages(conversation?.id);
  const updateConversation = useUpdateConversation();
  const updateMessage = useUpdateMessage();
  const regenerateMessage = useRegenerateMessage();

  useStream(streamingMessageId, {
    onEvent: (event) => {
      if (streamingMessageId) applyStreamEvent(streamingMessageId, event);
      if (event.event === 'tool_call') {
        streamingToolNamesRef.current[event.data.call_id] = event.data.tool_name;
      }
      if (event.event === 'tool_result') {
        const toolName = streamingToolNamesRef.current[event.data.call_id];
        if (conversation?.id && isWorkspaceWritingTool(toolName)) {
          void queryClient.invalidateQueries({ queryKey: ['workspace-tree', conversation.id] });
        }
        delete streamingToolNamesRef.current[event.data.call_id];
      }
    },
    onDone: () => {
      if (conversation?.id) {
        void queryClient.invalidateQueries({ queryKey: ['messages', conversation.id] });
        void queryClient.invalidateQueries({ queryKey: ['workspace-tree', conversation.id] });
      }
      setStreamingMessageId(null);
    },
    onError: () => setStreamingMessageId(null),
  });

  useEffect(() => {
    streamingToolNamesRef.current = {};
  }, [streamingMessageId]);

  useEffect(() => {
    if (!conversationId && conversation?.id) {
      navigate(`/chat/${conversation.id}`, { replace: true });
    }
    if (conversationId && conversation?.id === conversationId) {
      setSelectedConversationId(conversation.id);
    }
    if (conversationId && conversation?.id && conversation.id !== conversationId) {
      setSelectedConversationId(conversation.id);
      navigate(`/chat/${conversation.id}`, { replace: true });
    }
  }, [conversationId, conversation?.id, navigate, setSelectedConversationId]);

  useEffect(() => {
    if (!highlightedMessageId) return undefined;
    const timer = window.setTimeout(() => setHighlightedMessageId(null), 1200);
    return () => window.clearTimeout(timer);
  }, [highlightedMessageId, setHighlightedMessageId]);

  function selectConversation(nextConversationId: string) {
    setSelectedConversationId(nextConversationId);
    navigate(`/chat/${nextConversationId}`);
  }

  async function toggleConversationPinRemote(conversationId: string) {
    const target = conversations.find((item) => item.id === conversationId);
    if (!target) return;
    await updateConversation.update(conversationId, { is_pinned: !target.is_pinned });
  }

  async function toggleConversationArchiveRemote(conversationId: string) {
    const target = conversations.find((item) => item.id === conversationId);
    if (!target) return;
    await updateConversation.update(conversationId, { is_archived: !target.is_archived });
  }

  async function toggleMessagePinRemote(messageId: string) {
    const target = messages.find((item) => item.id === messageId);
    if (!target) return;
    await updateMessage.update(target, { is_pinned: !target.is_pinned });
  }

  function mentionAgent(agent: Agent) {
    setMentionInsertRequest({ agentId: agent.id, requestId: Date.now() });
  }

  return (
    <div className="flex h-screen overflow-hidden bg-slate-950">
      {!conversationSidebarCollapsed && (
        <ConversationSidebar
          conversations={visibleConversations}
          selectedConversationId={conversation?.id ?? ''}
          search={search}
          onSearch={setSearch}
          onSelect={selectConversation}
          onNewConversation={() => setNewConversationOpen(true)}
          onCollapse={() => setConversationSidebarCollapsed(true)}
          onTogglePin={toggleConversationPinRemote}
          onToggleArchive={toggleConversationArchiveRemote}
        />
      )}
      <section className="flex min-w-0 flex-1 flex-col">
        {conversation ? (
          <>
            <ChatHeader
              conversation={conversation}
              agents={agents}
              sidebarCollapsed={conversationSidebarCollapsed}
              onExpandSidebar={() => setConversationSidebarCollapsed(false)}
              rightPanelOpen={rightPanelOpen}
              onOpenRightPanel={() => setRightPanelOpen(true)}
            />
            <StreamingStatusBar messages={messages} agents={agents} />
            <MessageList
              messages={messages}
              agents={agents}
              highlightedMessageId={highlightedMessageId}
              isLoading={messagesLoading}
              onTogglePin={toggleMessagePinRemote}
              onMentionAgent={conversation.mode === 'group' ? mentionAgent : undefined}
              onRetry={async (messageId) => {
                const target = messages.find((item) => item.id === messageId);
                if (!target) return;
                const nextMessage = await regenerateMessage.regenerate(target);
                setStreamingMessageId(nextMessage.id);
              }}
            />
            <MessageInput
              conversation={conversation}
              agents={agents}
              isSending={sendingMessage}
              mentionInsertRequest={mentionInsertRequest}
              onSend={async (text) => {
                const result = await sendMessage(conversation.id, text);
                if (result?.agentMessageId) setStreamingMessageId(result.agentMessageId);
              }}
            />
          </>
        ) : conversationsLoading ? (
          <LoadingChatPlaceholder />
        ) : (
          <EmptyChatPlaceholder onNew={() => setNewConversationOpen(true)} />
        )}
      </section>
      {conversation && rightPanelOpen && (
        <RightAgentPanel
          conversation={conversation}
          messages={messages}
          agents={agents}
          width={rightPanelWidth}
          onWidthChange={setRightPanelWidth}
          onCollapse={() => setRightPanelOpen(false)}
          onSelectPinnedMessage={setHighlightedMessageId}
        />
      )}
      <NewConversationDialog
        open={newConversationOpen}
        agents={agents}
        isPending={createConversation.isPending}
        onClose={() => setNewConversationOpen(false)}
        onCreate={async (value) => {
          const created = await createConversation.mutateAsync(value);
          setNewConversationOpen(false);
          selectConversation(created.id);
        }}
      />
    </div>
  );
}

function isWorkspaceWritingTool(toolName: string | undefined): boolean {
  if (!toolName) return false;
  const normalized = toolName.toLowerCase();
  return normalized.includes('write') || normalized.includes('file');
}

function LoadingChatPlaceholder() {
  return (
    <div className="flex flex-1 items-center justify-center bg-slate-950 p-8">
      <div className="rounded-md border border-slate-800 bg-slate-900 px-5 py-4 text-sm text-slate-400">
        正在恢复会话
      </div>
    </div>
  );
}

function EmptyChatPlaceholder({ onNew }: { onNew: () => void }) {
  return (
    <div className="flex flex-1 items-center justify-center bg-slate-950 p-8">
      <div className="max-w-md rounded-lg border border-slate-800 bg-slate-900 p-8 text-center">
        <div className="mx-auto mb-4 flex h-12 w-12 items-center justify-center rounded-full bg-brand/15 text-brand-light">
          <MessageSquarePlus className="h-6 w-6" />
        </div>
        <h2 className="text-base font-semibold text-white">还没有会话</h2>
        <p className="mt-2 text-sm leading-6 text-slate-500">
          创建一个会话，挑选一个或多个 Agent，开始你的第一次协作。
        </p>
        <button
          type="button"
          onClick={onNew}
          className="mt-5 inline-flex items-center gap-2 rounded-md bg-brand px-4 py-2 text-sm font-medium text-white hover:bg-brand-hover"
        >
          <MessageSquarePlus className="h-4 w-4" />
          新建会话
        </button>
      </div>
    </div>
  );
}
