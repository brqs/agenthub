import { useEffect } from 'react';
import { useNavigate, useParams } from 'react-router-dom';
import { RightAgentPanel } from '@/components/agents/RightAgentPanel';
import { ChatHeader } from '@/components/chat/ChatHeader';
import { MessageInput } from '@/components/chat/MessageInput';
import { MessageList } from '@/components/chat/MessageList';
import { ConversationSidebar } from '@/components/conversation/ConversationSidebar';
import { useChatStore } from '@/stores/chatStore';

export function ChatPage() {
  const { conversationId } = useParams<{ conversationId?: string }>();
  const navigate = useNavigate();
  const conversations = useChatStore((state) => state.conversations);
  const messagesByConversation = useChatStore((state) => state.messagesByConversation);
  const selectedConversationId = useChatStore((state) => state.selectedConversationId);
  const search = useChatStore((state) => state.search);
  const setSearch = useChatStore((state) => state.setSearch);
  const setSelectedConversationId = useChatStore((state) => state.setSelectedConversationId);
  const sendMockMessage = useChatStore((state) => state.sendMockMessage);

  const activeConversationId = conversationId ?? selectedConversationId;
  const conversation = conversations.find((item) => item.id === activeConversationId) ?? conversations[0];
  const messages = conversation ? messagesByConversation[conversation.id] ?? [] : [];

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
      />
      <section className="flex min-w-0 flex-1 flex-col">
        <ChatHeader conversation={conversation} />
        <MessageList messages={messages} />
        <MessageInput
          conversation={conversation}
          onSend={(text) => sendMockMessage(conversation.id, text)}
        />
      </section>
      <RightAgentPanel conversation={conversation} messages={messages} />
    </div>
  );
}

