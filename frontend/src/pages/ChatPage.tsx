import { useEffect, useState } from 'react';
import { useNavigate, useParams } from 'react-router-dom';
import { RightAgentPanel } from '@/components/agents/RightAgentPanel';
import { ChatHeader } from '@/components/chat/ChatHeader';
import { MessageInput } from '@/components/chat/MessageInput';
import { MessageList } from '@/components/chat/MessageList';
import { NewConversationDialog } from '@/components/conversation/NewConversationDialog';
import { ConversationSidebar } from '@/components/conversation/ConversationSidebar';
import { useAgents } from '@/hooks/useAgents';
import { useCreateConversation } from '@/hooks/useCreateConversation';
import { useConversations } from '@/hooks/useConversations';
import { useMessages } from '@/hooks/useMessages';
import { useSendMessage } from '@/hooks/useSendMessage';
import { useStream } from '@/hooks/useStream';
import { useChatStore } from '@/stores/chatStore';

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
  const applyStreamEvent = useChatStore((state) => state.applyStreamEvent);
  const resetMessageForRetry = useChatStore((state) => state.resetMessageForRetry);
  const { sendMessage, isPending: sendingMessage } = useSendMessage();

  const activeConversationId = conversationId ?? selectedConversationId;
  const conversation = conversations.find((item) => item.id === activeConversationId) ?? conversations[0];
  const { data: messages, isLoading: messagesLoading } = useMessages(conversation?.id);

  useStream(streamingMessageId, {
    onEvent: (event) => {
      if (streamingMessageId) applyStreamEvent(streamingMessageId, event);
    },
    onDone: () => setStreamingMessageId(null),
    onError: () => setStreamingMessageId(null),
  });

  useEffect(() => {
    if (!conversationId && selectedConversationId) {
      navigate(`/chat/${selectedConversationId}`, { replace: true });
    }
  }, [conversationId, navigate, selectedConversationId]);

  if (!conversation) {
    return (
      <div className="flex h-full items-center justify-center bg-slate-950 text-slate-500">
        还没有会话
      </div>
    );
  }

  function selectConversation(nextConversationId: string) {
    setSelectedConversationId(nextConversationId);
    navigate(`/chat/${nextConversationId}`);
  }

  return (
    <div className="flex h-screen overflow-hidden bg-slate-950">
      <ConversationSidebar
        conversations={conversations}
        selectedConversationId={conversation.id}
        search={search}
        onSearch={setSearch}
        onSelect={selectConversation}
        onNewConversation={() => setNewConversationOpen(true)}
      />
      <section className="flex min-w-0 flex-1 flex-col">
        <ChatHeader conversation={conversation} />
        <MessageList
          messages={messages}
          isLoading={messagesLoading}
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
      </section>
      <RightAgentPanel conversation={conversation} messages={messages} />
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
