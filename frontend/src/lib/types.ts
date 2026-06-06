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
export type User = Schemas['UserOut'];
export type AuthResponse = Schemas['AuthResponse'];
export type LoginRequest = Schemas['LoginRequest'];
export type RegisterRequest = Schemas['RegisterRequest'];

// ─── Conversations ───
export type Conversation = Override<
  Schemas['ConversationOut'],
  { agent_ids: string[]; is_pinned: boolean; is_archived: boolean }
>;
export type ConversationList = Override<Schemas['ConversationList'], { items: Conversation[] }>;
export type CreateConversationRequest = Schemas['CreateConversationRequest'];
export type UpdateConversationRequest = Schemas['UpdateConversationRequest'];
export type OrchestratorRunList = Schemas['OrchestratorRunList'];
export type OrchestratorRun = Schemas['OrchestratorRunOut'];
export type OrchestratorRunDetail = Schemas['OrchestratorRunDetailOut'];
export type OrchestratorTask = Schemas['OrchestratorTaskOut'];
export type OrchestratorTaskAttempt = Schemas['OrchestratorTaskAttemptOut'];
export type OrchestratorRunEvent = Schemas['OrchestratorRunEventOut'];

// ─── Workspace deployments ───
export type WorkspaceDeploymentRequest = Schemas['WorkspaceDeploymentRequest'];
export type WorkspaceDeploymentResponse = Schemas['WorkspaceDeploymentResponse'];
export type WorkspaceDeploymentListResponse = Schemas['WorkspaceDeploymentListResponse'];

// ─── Content blocks ───
export type TextBlock = Schemas['TextBlock'];
export type CodeBlock = Schemas['CodeBlock'];
export type DiffBlock = Schemas['DiffBlock'];
export type WebPreviewBlock = Schemas['WebPreviewBlock'];
export interface FileBlock {
  type: 'file';
  agent_id?: string | null;
  path?: string | null;
  artifact_kind?: 'document' | 'ppt' | 'image' | 'archive' | 'code' | 'workflow' | 'other';
  filename: string;
  url: string;
  size: number;
  mime_type: string;
  preview_text?: string | null;
  preview_truncated?: boolean | null;
  metadata?: Record<string, unknown>;
}
export interface DeploymentStatusBlock {
  type: 'deployment_status';
  agent_id?: string | null;
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
  agent_id?: string | null;
  call_id: string;
  tool_name: string;
  arguments: Record<string, unknown>;
  status: 'pending' | 'ok' | 'error';
  output_preview?: string;
  output_truncated?: boolean;
  error_code?: string;
}
export interface ProcessStep {
  id?: string;
  label: string;
  kind:
    | 'routing'
    | 'planning'
    | 'dispatch'
    | 'tool'
    | 'review'
    | 'evaluation'
    | 'workflow'
    | 'deployment'
    | 'artifact'
    | 'repair'
    | 'summary';
  status: 'done' | 'running' | 'error' | 'skipped';
  detail?: string | null;
  agent_id?: string | null;
}
export interface ProcessBlock {
  type: 'process';
  agent_id?: string | null;
  title: string;
  status: 'running' | 'done' | 'partial' | 'error';
  default_collapsed: boolean;
  steps: ProcessStep[];
  summary?: string | null;
  metadata?: Record<string, unknown>;
}
export interface WorkflowBlock {
  type: 'workflow';
  agent_id?: string | null;
  last_run_id?: string | null;
  name?: string | null;
  path?: string | null;
  format?: 'json' | 'yaml';
  definition?: Record<string, unknown>;
  raw_definition?: string | null;
  nodes?: Array<Record<string, unknown>>;
  edges?: Array<Record<string, unknown>>;
  validation_status?: 'passed' | 'failed' | 'unknown';
  runtime_status?: 'ready' | 'invalid' | 'not_supported';
  dry_run_status?: 'passed' | 'failed' | 'not_supported';
  health_status?: 'passed' | 'failed' | 'unknown';
  validation_errors?: string[];
}

export interface TaskCardBlock {
  type: 'task_card';
  agent_id?: string | null;
  title: string;
  tasks: Array<{
    id: string;
    agent_id: string;
    title: string;
    status: 'pending' | 'running' | 'done' | 'error';
  }>;
}

export type ContentBlock =
  | TextBlock
  | CodeBlock
  | DiffBlock
  | WebPreviewBlock
  | FileBlock
  | DeploymentStatusBlock
  | WorkflowBlock
  | TaskCardBlock
  | ProcessBlock
  | ToolCallBlock;

// ─── Messages ───
export type Message = Override<
  Schemas['MessageOut'],
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
  Schemas['AgentOut'],
  {
    capabilities: string[];
    config: Record<string, unknown>;
    is_builtin: boolean;
    avatar_url: string;
  }
>;
export type AgentList = Override<Schemas['AgentList'], { items: Agent[] }>;
export type CreateAgentRequest = Schemas['CreateAgentRequest'];
export type CreatableAgentProvider = CreateAgentRequest['provider'];
export type UpdateAgentRequest = Schemas['UpdateAgentRequest'];

// ─── SSE events (hand-written; not in OpenAPI) ───
export type StreamEvent =
  | { event: 'start'; data: { message_id?: string; agent_id?: string } }
  | {
      event: 'message_start';
      data: {
        message_id: string;
        conversation_id: string;
        agent_id: string;
        reply_to_id?: string | null;
        created_at?: string;
        status?: 'streaming';
      };
    }
  | {
      event: 'message_done';
      data: {
        message_id: string;
        conversation_id?: string;
        agent_id?: string;
        reply_to_id?: string | null;
        status?: 'done';
        total_blocks?: number;
      };
    }
  | {
      event: 'message_error';
      data: {
        message_id: string;
        conversation_id?: string;
        agent_id?: string;
        reply_to_id?: string | null;
        status?: 'error';
        error_code?: string;
        error?: string;
      };
    }
  | {
      event: 'block_start';
      data: {
        block_index: number;
        block_type: string;
        metadata?: Record<string, unknown>;
        agent_id?: string;
        message_id?: string;
      };
    }
  | {
      event: 'delta';
      data: {
        block_index: number;
        text_delta?: string;
        code_delta?: string;
        metadata?: Record<string, unknown>;
        agent_id?: string;
        message_id?: string;
      };
    }
  | { event: 'block_end'; data: { block_index: number; agent_id?: string; message_id?: string } }
  | { event: 'done'; data: { message_id?: string; total_blocks?: number; agent_id?: string } }
  | { event: 'error'; data: { error_code?: string; error?: string; agent_id?: string } }
  | { event: 'agent_switch'; data: { from_agent: string; to_agent: string; task?: string } }
  | {
      event: 'tool_call';
      data: {
        call_id: string;
        tool_name: string;
        tool_arguments: Record<string, unknown>;
        agent_id?: string;
        message_id?: string;
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
        agent_id?: string;
        message_id?: string;
      };
    }
  | { event: 'heartbeat'; data: { agent_id?: string } };
