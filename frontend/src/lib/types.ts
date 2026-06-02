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

// ─── Workspace deployments ───
export type WorkspaceDeploymentRequest = Schemas['WorkspaceDeploymentRequest'];
export type WorkspaceDeploymentResponse = Schemas['WorkspaceDeploymentResponse'];
export type WorkspaceDeploymentListResponse = Schemas['WorkspaceDeploymentListResponse'];

// ─── Content blocks ───
export type TextBlock = Schemas['TextBlock'];
export type CodeBlock = Schemas['CodeBlock'];
export type DiffBlock = Schemas['DiffBlock'];
export type WebPreviewBlock = Schemas['WebPreviewBlock'];
export type FileBlock = Schemas['FileBlock'];
export interface DeploymentStatusBlock {
  type: 'deployment_status';
  deployment_id: string;
  kind: 'static_site' | 'source_zip' | 'container';
  status: Schemas['DeploymentStatusBlock']['status'];
  title?: string | null;
  url?: string | null;
  download_url?: string | null;
  error?: string | null;
  logs_preview?: string | null;
  size_bytes?: number | null;
  artifact_digest?: string | null;
  file_count?: number | null;
  published_at?: string | null;
  stopped_at?: string | null;
  expires_at?: string | null;
  runtime_kind?: string | null;
  runtime_status?: string | null;
  host_port?: number | null;
  container_port?: number | null;
  healthcheck_url?: string | null;
  image_id?: string | null;
  container_id?: string | null;
  logs_tail?: string | null;
  queued_at?: string | null;
  started_at?: string | null;
  completed_at?: string | null;
  last_checked_at?: string | null;
}
export interface ToolCallBlock {
  type: 'tool_call';
  call_id: string;
  tool_name: string;
  arguments: Record<string, unknown>;
  status: 'pending' | 'ok' | 'error';
  output_preview?: string;
  output_truncated?: boolean;
  error_code?: string;
}

export type ContentBlock =
  | TextBlock
  | CodeBlock
  | DiffBlock
  | WebPreviewBlock
  | FileBlock
  | DeploymentStatusBlock
  | ToolCallBlock;

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
export type CreatableAgentProvider = CreateAgentRequest['provider'];
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
  | {
      event: 'tool_call';
      data: {
        call_id: string;
        tool_name: string;
        tool_arguments: Record<string, unknown>;
      };
    }
  | {
      event: 'tool_result';
      data: {
        call_id: string;
        tool_status: 'ok' | 'error';
        tool_output?: string;
        tool_output_truncated?: boolean;
        error_code?: string;
      };
    }
  | { event: 'heartbeat'; data: Record<string, never> };
