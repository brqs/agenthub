import { useEffect, useState } from 'react';
import { MessageSquarePlus } from 'lucide-react';
import { useNavigate, useParams } from 'react-router-dom';
import { RightAgentPanel } from '@/components/agents/RightAgentPanel';
import { ChatHeader } from '@/components/chat/ChatHeader';
import { MessageInput } from '@/components/chat/MessageInput';
import { MessageList } from '@/components/chat/MessageList';
import { StreamingStatusBar } from '@/components/chat/StreamingStatusBar';
import { NewConversationDialog } from '@/components/conversation/NewConversationDialog';
import { ConversationSidebar } from '@/components/conversation/ConversationSidebar';
import { MobileSheet } from '@/components/mobile/MobileSheet';
import { useAgents } from '@/hooks/useAgents';
import { useCreateConversation } from '@/hooks/useCreateConversation';
import { useConversations } from '@/hooks/useConversations';
import { useMessages } from '@/hooks/useMessages';
import { useMediaQuery } from '@/hooks/useMediaQuery';
import { useNetworkStatus } from '@/hooks/useNetworkStatus';
import { useInterruptMessage } from '@/hooks/useInterruptMessage';
import { useQueueMessage } from '@/hooks/useQueueMessage';
import { useRegenerateMessage } from '@/hooks/useRegenerateMessage';
import { useSendMessage } from '@/hooks/useSendMessage';
import { useTurnControlActions } from '@/hooks/useTurnControlActions';
import { useUpdateConversation } from '@/hooks/useUpdateConversation';
import { useUpdateMessage } from '@/hooks/useUpdateMessage';
import type { Agent } from '@/lib/types';
import { resolveConversation } from '@/pages/chatPageUtils';
import { useChatStore } from '@/stores/chatStore';
import { useUiStore } from '@/stores/uiStore';

export function ChatPage() {
  const { conversationId } = useParams<{ conversationId?: string }>();
  const navigate = useNavigate();
  const [newConversationOpen, setNewConversationOpen] = useState(false);
  const [retryingMessageIds, setRetryingMessageIds] = useState<Record<string, boolean>>({});
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
  const activeStreams = useChatStore((state) => state.activeStreams);
  const startActiveStream = useChatStore((state) => state.startActiveStream);
  const setHighlightedMessageId = useChatStore((state) => state.setHighlightedMessageId);
  const conversationSidebarCollapsed = useUiStore((state) => state.conversationSidebarCollapsed);
  const rightPanelOpen = useUiStore((state) => state.rightPanelOpen);
  const rightPanelWidth = useUiStore((state) => state.rightPanelWidth);
  const setConversationSidebarCollapsed = useUiStore(
    (state) => state.setConversationSidebarCollapsed,
  );
  const setRightPanelOpen = useUiStore((state) => state.setRightPanelOpen);
  const setRightPanelWidth = useUiStore((state) => state.setRightPanelWidth);
  const mobileSheet = useUiStore((state) => state.mobileSheet);
  const openMobileSheet = useUiStore((state) => state.openMobileSheet);
  const closeMobileSheet = useUiStore((state) => state.closeMobileSheet);
  const { sendMessage, isPending: sendingMessage } = useSendMessage();
  const queueMessage = useQueueMessage();
  const turnControlActions = useTurnControlActions();
  const isDesktopWorkspace = useMediaQuery('(min-width: 1280px)');
  const isOnline = useNetworkStatus();

  const visibleConversations = conversations.filter((item) => !item.is_archived);
  const conversation = resolveConversation(
    visibleConversations,
    conversationId,
    selectedConversationId,
  );
  const {
    data: messages,
    isLoading: messagesLoading,
    isLoadingMore: messagesLoadingMore,
    hasMore: messagesHasMore,
    fetchPreviousPage: fetchPreviousMessages,
  } = useMessages(conversation?.id);
  const updateConversation = useUpdateConversation();
  const updateMessage = useUpdateMessage();
  const regenerateMessage = useRegenerateMessage();
  const interruptMessage = useInterruptMessage();
  const currentActiveStream = conversation
    ? Object.values(activeStreams)
        .filter((stream) => stream.conversationId === conversation.id)
        .sort((a, b) => Date.parse(b.startedAt) - Date.parse(a.startedAt))[0]
    : undefined;
  const interruptingMessageIds = Object.fromEntries(
    Object.entries(activeStreams)
      .filter(([, stream]) => stream.interrupting)
      .map(([messageId]) => [messageId, true]),
  );

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
    closeMobileSheet();
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
    <div className="flex h-full overflow-hidden bg-slate-950">
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
              onOpenConversationList={() => openMobileSheet('conversation-list')}
              onOpenWorkspace={() => openMobileSheet('workspace')}
            />
            <StreamingStatusBar messages={messages} agents={agents} />
            <MessageList
              messages={messages}
              agents={agents}
              highlightedMessageId={highlightedMessageId}
              isLoading={messagesLoading}
              isLoadingMore={messagesLoadingMore}
              hasMore={messagesHasMore}
              onLoadMore={fetchPreviousMessages}
              onTogglePin={toggleMessagePinRemote}
              onMentionAgent={conversation.mode === 'group' ? mentionAgent : undefined}
              retryingMessageIds={retryingMessageIds}
              onRetry={async (messageId) => {
                if (retryingMessageIds[messageId]) return;
                const target = messages.find((item) => item.id === messageId);
                if (!target) return;
                setRetryingMessageIds((current) => ({ ...current, [messageId]: true }));
                try {
                  const nextMessage = await regenerateMessage.regenerate(target);
                  startActiveStream(nextMessage);
                } finally {
                  setRetryingMessageIds((current) => {
                    const next = { ...current };
                    delete next[messageId];
                    return next;
                  });
                }
              }}
              onUpdateQueuedMessage={async (messageId, text, requirementAlignment) => {
                await queueMessage.updateQueuedMessage(messageId, text, requirementAlignment);
              }}
              onDeleteQueuedMessage={async (messageId) => {
                await queueMessage.deleteQueuedMessage(messageId);
              }}
              onReorderQueuedMessages={async (conversationId, messageIds) => {
                await turnControlActions.reorderQueuedMessages(conversationId, messageIds);
              }}
              onMergeQueuedMessages={async (conversationId, messageIds) => {
                await turnControlActions.mergeQueuedMessages(conversationId, messageIds);
              }}
              onConvertQueuedToGuidance={async (messageId) => {
                await turnControlActions.convertQueuedToGuidance(messageId);
              }}
              onStopAndRunQueuedMessage={async (messageId) => {
                await turnControlActions.stopAndRunQueuedMessage(messageId);
              }}
              interruptingMessageIds={interruptingMessageIds}
            />
            <MessageInput
              conversation={conversation}
              agents={agents}
              isSending={sendingMessage}
              isQueueing={queueMessage.isPending || turnControlActions.isPending}
              isOffline={!isOnline}
              isStreaming={Boolean(currentActiveStream)}
              isInterrupting={Boolean(currentActiveStream?.interrupting)}
              onInterrupt={
                currentActiveStream
                  ? async () => {
                      await interruptMessage.interrupt(currentActiveStream.messageId);
                    }
                  : undefined
              }
              mentionInsertRequest={mentionInsertRequest}
              onQueue={async (text, attachmentIds, requirementAlignment) => {
                await queueMessage.queueMessage(
                  conversation.id,
                  text,
                  attachmentIds ?? [],
                  requirementAlignment,
                );
              }}
              onGuidance={
                currentActiveStream
                  ? async (text) => {
                      await turnControlActions.sendGuidance(currentActiveStream.messageId, text);
                    }
                  : undefined
              }
              onSideChat={
                currentActiveStream
                  ? async (text) => {
                      await turnControlActions.sendSideChat(currentActiveStream.messageId, text);
                    }
                  : undefined
              }
              onStopAndRun={
                currentActiveStream
                  ? async (text, requirementAlignment) => {
                      const queued = await queueMessage.queueMessage(
                        conversation.id,
                        text,
                        [],
                        requirementAlignment,
                      );
                      await turnControlActions.stopAndRunQueuedMessage(queued.queued_message.id);
                    }
                  : undefined
              }
              onSend={async (text, attachmentIds, requirementAlignment) => {
                await sendMessage(conversation.id, text, attachmentIds ?? [], requirementAlignment);
              }}
            />
          </>
        ) : conversationsLoading ? (
          <LoadingChatPlaceholder />
        ) : (
          <EmptyChatPlaceholder onNew={() => setNewConversationOpen(true)} />
        )}
      </section>
      {conversation && rightPanelOpen && isDesktopWorkspace && (
        <RightAgentPanel
          key={`desktop-${conversation.id}`}
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
      <MobileSheet
        open={mobileSheet === 'conversation-list'}
        variant="drawer"
        onClose={closeMobileSheet}
      >
        <ConversationSidebar
          conversations={visibleConversations}
          selectedConversationId={conversation?.id ?? ''}
          search={search}
          presentation="mobile"
          onSearch={setSearch}
          onSelect={selectConversation}
          onNewConversation={() => {
            closeMobileSheet();
            setNewConversationOpen(true);
          }}
          onCollapse={closeMobileSheet}
          onTogglePin={toggleConversationPinRemote}
          onToggleArchive={toggleConversationArchiveRemote}
        />
      </MobileSheet>
      {conversation && (
        <MobileSheet open={mobileSheet === 'workspace'} hiddenAt="xl" onClose={closeMobileSheet}>
          <RightAgentPanel
            key={`mobile-${conversation.id}`}
            conversation={conversation}
            messages={messages}
            agents={agents}
            presentation="mobile"
            onCollapse={closeMobileSheet}
            onSelectPinnedMessage={(messageId) => {
              closeMobileSheet();
              setHighlightedMessageId(messageId);
            }}
          />
        </MobileSheet>
      )}
    </div>
  );
}

function LoadingChatPlaceholder() {
  return (
    <div className="flex flex-1 items-center justify-center bg-slate-100 p-8 dark:bg-slate-950">
      <div className="rounded-md border border-slate-300 bg-white px-5 py-4 text-sm text-slate-600 dark:border-slate-800 dark:bg-slate-900 dark:text-slate-400">
        正在恢复会话
      </div>
    </div>
  );
}

function EmptyChatPlaceholder({ onNew }: { onNew: () => void }) {
  return (
    <div className="flex flex-1 items-center justify-center bg-slate-100 p-8 dark:bg-slate-950">
      <div className="max-w-md rounded-lg border border-slate-300 bg-white p-8 text-center dark:border-slate-800 dark:bg-slate-900">
        <div className="mx-auto mb-4 flex h-12 w-12 items-center justify-center rounded-full bg-brand/10 text-brand dark:bg-brand/15 dark:text-brand-light">
          <MessageSquarePlus className="h-6 w-6" />
        </div>
        <h2 className="text-base font-semibold text-slate-950 dark:text-white">还没有会话</h2>
        <p className="mt-2 text-sm leading-6 text-slate-600 dark:text-slate-500">
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
