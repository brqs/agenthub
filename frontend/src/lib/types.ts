/**
 * Friendly aliases over the auto-generated OpenAPI types in `types.gen.ts`.
 *
 * Regenerate via:
 *   pnpm gen:types
 *
 * Hand-written here: SSE `StreamEvent` (OpenAPI does not describe the
 * text/event-stream payloads) and a couple of convenience unions.
 */

import type { components } from './types.gen';

type Schemas = components['schemas'];

/**
 * Replace properties from `T` with the (typically narrower) `R`.
 * Used to mark fields the backend always populates (via column defaults)
 * but did not flag as `required` in OpenAPI.
 *
 * TODO(B1): tighten Conversation/Agent/Message `required` lists so
 * we can drop these overrides.
 */
type Override<T, R> = Omit<T, keyof R> & R;

// ─── Auth ───
export type User = Schemas['User'];
export type AuthResponse = Schemas['AuthResponse'];
export type LoginRequest = Schemas['LoginRequest'];
export type RegisterRequest = Schemas['RegisterRequest'];

// ─── Conversations ───
export type Conversation = Override<
  Schemas['Conversation'],
  { agent_ids: string[]; is_pinned: boolean; is_archived: boolean }
>;
export type ConversationList = Override<
  Schemas['ConversationList'],
  { items: Conversation[] }
>;
export type CreateConversationRequest = Schemas['CreateConversationRequest'];
export type UpdateConversationRequest = Schemas['UpdateConversationRequest'];

// ─── Content blocks ───
export type TextBlock = Schemas['TextBlock'];
export type CodeBlock = Schemas['CodeBlock'];
export type DiffBlock = Schemas['DiffBlock'];
export type WebPreviewBlock = Schemas['WebPreviewBlock'];
export type FileBlock = Schemas['FileBlock'];
export type ContentBlock = TextBlock | CodeBlock | DiffBlock | WebPreviewBlock | FileBlock;

// ─── Messages ───
export type Message = Override<
  Schemas['Message'],
  { content: ContentBlock[]; status: MessageStatus; is_pinned: boolean }
>;
export type MessageList = Override<Schemas['MessageList'], { items: Message[] }>;
export type SendMessageRequest = Schemas['SendMessageRequest'];
export type SendMessageResponse = Override<
  Schemas['SendMessageResponse'],
  { user_message: Message; agent_message: Message }
>;
export type UpdateMessageRequest = Schemas['UpdateMessageRequest'];

export type MessageRole = Message['role'];
export type MessageStatus = 'pending' | 'streaming' | 'done' | 'error';

// ─── Agents ───
export type Agent = Override<
  Schemas['Agent'],
  { capabilities: string[]; config: Record<string, unknown>; is_builtin: boolean; avatar_url: string }
>;
export type AgentList = Override<Schemas['AgentList'], { items: Agent[] }>;
export type CreateAgentRequest = Schemas['CreateAgentRequest'];
export type UpdateAgentRequest = Schemas['UpdateAgentRequest'];

// ─── SSE events (hand-written; not in OpenAPI) ───
export type StreamEvent =
  | { event: 'start'; data: { message_id?: string; agent_id?: string } }
  | {
      event: 'block_start';
      data: { block_index: number; block_type: string; metadata?: Record<string, unknown> };
    }
  | { event: 'delta'; data: { block_index: number; text_delta?: string; code_delta?: string } }
  | { event: 'block_end'; data: { block_index: number } }
  | { event: 'done'; data: { message_id?: string; total_blocks?: number } }
  | { event: 'error'; data: { error_code?: string; error?: string } }
  | { event: 'agent_switch'; data: { from_agent: string; to_agent: string; task?: string } }
  | { event: 'heartbeat'; data: Record<string, never> };
