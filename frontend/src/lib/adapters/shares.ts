import { api } from '@/lib/api';

export interface PublicSharedMessage {
  id: string;
  role: string;
  agent_id?: string | null;
  content: Array<Record<string, unknown>>;
  created_at: string;
}

export interface PublicConversationShare {
  conversation_id: string;
  title: string;
  mode: string;
  include_artifacts: boolean;
  created_at: string;
  expires_at?: string | null;
  messages: PublicSharedMessage[];
}

export async function getPublicConversationShare(token: string): Promise<PublicConversationShare> {
  const { data } = await api.get<PublicConversationShare>(`/api/v1/conversation-shares/${token}`);
  return data;
}
