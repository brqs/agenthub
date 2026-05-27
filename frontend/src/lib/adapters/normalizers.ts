import type { Agent, Conversation, Message } from '@/lib/types';

export function normalizeConversation(conversation: Conversation): Conversation {
  return {
    ...conversation,
    agent_ids: conversation.agent_ids ?? [],
    is_pinned: conversation.is_pinned ?? false,
    is_archived: conversation.is_archived ?? false,
    last_message_preview: conversation.last_message_preview ?? null,
  };
}

export function normalizeAgent(agent: Agent): Agent {
  return {
    ...agent,
    avatar_url: agent.avatar_url ?? '',
    capabilities: agent.capabilities ?? [],
    config: agent.config ?? {},
    is_builtin: agent.is_builtin ?? false,
  };
}

export function normalizeMessage(message: Message): Message {
  return {
    ...message,
    agent_id: message.agent_id ?? null,
    content: message.content ?? [],
    reply_to_id: message.reply_to_id ?? null,
    status: message.status ?? 'done',
    is_pinned: message.is_pinned ?? false,
  };
}
