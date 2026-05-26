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
import { useAgents } from '@/hooks/useAgents';
import { useCreateConversation } from '@/hooks/useCreateConversation';
import { useConversations } from '@/hooks/useConversations';
import { useMessages } from '@/hooks/useMessages';
import { useSendMessage } from '@/hooks/useSendMessage';
import { useStream } from '@/hooks/useStream';
import { useChatStore } from '@/stores/chatStore';
import { useUiStore } from '@/stores/uiStore';

export function ChatPage() {
  const { conversationId } = useParams<{ conversationId?: string }>();
  const navigate = useNavigate();
  const [streamingMessageId, setStreamingMessageId] = useState<string | null>(null);
  const [newConversationOpen, setNewConversationOpen] = useState(false);
  const { data: conversations } = useConversations();
  const { data: agents } = useAgents();
  const createConversation = useCreateConversation();
  const selectedConversationId = useChatStore((state) => state.selectedConversationId);
  const search = useChatStore((state) => state.search);
  const setSearch = useChatStore((state) => state.setSearch);
  const setSelectedConversationId = useChatStore((state) => state.setSelectedConversationId);
  const highlightedMessageId = useChatStore((state) => state.highlightedMessageId);
  const applyStreamEvent = useChatStore((state) => state.applyStreamEvent);
  const resetMessageForRetry = useChatStore((state) => state.resetMessageForRetry);
  const setHighlightedMessageId = useChatStore((state) => state.setHighlightedMessageId);
  const toggleMessagePin = useChatStore((state) => state.toggleMessagePin);
  const toggleConversationPin = useChatStore((state) => state.toggleConversationPin);
  const toggleConversationArchive = useChatStore((state) => state.toggleConversationArchive);
  const conversationSidebarCollapsed = useUiStore((state) => state.conversationSidebarCollapsed);
  const setConversationSidebarCollapsed = useUiStore((state) => state.setConversationSidebarCollapsed);
  const { sendMessage, isPending: sendingMessage } = useSendMessage();

  const visibleConversations = conversations.filter((item) => !item.is_archived);
  const activeConversationId = conversationId ?? selectedConversationId;
  const conversation =
    conversations.find((item) => item.id === activeConversationId) ?? visibleConversations[0];
  const { data: messages, isLoading: messagesLoading } = useMessages(conversation?.id);

  useStream(streamingMessageId, {
    onEvent: (event) => {
      if (streamingMessageId) applyStreamEvent(streamingMessageId, event);
    },
    onDone: () => setStreamingMessageId(null),
    onError: () => setStreamingMessageId(null),
  });

  useEffect(() => {
    if (!conversationId && conversation?.id) {
      navigate(`/chat/${conversation.id}`, { replace: true });
    }
  }, [conversationId, conversation?.id, navigate]);

  useEffect(() => {
    if (!highlightedMessageId) return undefined;
    const timer = window.setTimeout(() => setHighlightedMessageId(null), 1200);
    return () => window.clearTimeout(timer);
  }, [highlightedMessageId, setHighlightedMessageId]);

  function selectConversation(nextConversationId: string) {
    setSelectedConversationId(nextConversationId);
    navigate(`/chat/${nextConversationId}`);
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
          onTogglePin={toggleConversationPin}
          onToggleArchive={toggleConversationArchive}
        />
      )}
      <section className="flex min-w-0 flex-1 flex-col">
        {conversation ? (
          <>
            <ChatHeader
              conversation={conversation}
              sidebarCollapsed={conversationSidebarCollapsed}
              onExpandSidebar={() => setConversationSidebarCollapsed(false)}
            />
            <StreamingStatusBar messages={messages} />
            <MessageList
              messages={messages}
              highlightedMessageId={highlightedMessageId}
              isLoading={messagesLoading}
              onTogglePin={toggleMessagePin}
              onRetry={(messageId) => {
                resetMessageForRetry(messageId);
                setStreamingMessageId(messageId);
              }}
            />
            <MessageInput
              conversation={conversation}
              isSending={sendingMessage}
              onSend={async (text) => {
                const result = await sendMessage(conversation.id, text);
                if (result?.agentMessageId) setStreamingMessageId(result.agentMessageId);
              }}
            />
          </>
        ) : (
          <EmptyChatPlaceholder onNew={() => setNewConversationOpen(true)} />
        )}
      </section>
      {conversation && (
        <RightAgentPanel
          conversation={conversation}
          messages={messages}
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
