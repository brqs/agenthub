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
export type Memory = Schemas['MemoryOut'];
export type MemoryList = Schemas['MemoryList'];
export type MemoryMount = Schemas['MemoryMountOut'];
export type MemoryMountList = Schemas['MemoryMountList'];
export type UpdateMemoryRequest = Schemas['UpdateMemoryRequest'];

// ─── Workspace deployments ───
export type WorkspaceDeploymentRequest = Schemas['WorkspaceDeploymentRequest'];
export type WorkspaceDeploymentResponse = Schemas['WorkspaceDeploymentResponse'];
export type WorkspaceDeploymentListResponse = Schemas['WorkspaceDeploymentListResponse'];

// ─── Content blocks ───
export interface PresentationMetadata {
  role:
    | 'execution_process'
    | 'tool_trace'
    | 'execution_text'
    | 'artifact_evidence'
    | 'agent_summary'
    | 'final_answer';
  boundary?: 'execution_start' | 'answer_start';
  group_id?: string;
  closes_group_id?: string;
  collapsible: boolean;
  label?: string;
}

type WithPresentation<T> = T & {
  presentation?: PresentationMetadata | null;
};

export type TextBlock = WithPresentation<Schemas['TextBlock']>;
export type CodeBlock = WithPresentation<Schemas['CodeBlock']>;
export type DiffBlock = WithPresentation<Schemas['DiffBlock']>;
export type WebPreviewBlock = WithPresentation<Schemas['WebPreviewBlock']>;
export interface FileBlock {
  type: 'file';
  agent_id?: string | null;
  presentation?: PresentationMetadata | null;
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
  presentation?: PresentationMetadata | null;
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
  presentation?: PresentationMetadata | null;
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
  status: 'done' | 'running' | 'error' | 'skipped' | 'interrupted';
  detail?: string | null;
  agent_id?: string | null;
}
export interface ProcessBlock {
  type: 'process';
  agent_id?: string | null;
  presentation?: PresentationMetadata | null;
  title: string;
  status: 'running' | 'done' | 'partial' | 'error' | 'interrupted';
  default_collapsed: boolean;
  steps: ProcessStep[];
  summary?: string | null;
  metadata?: Record<string, unknown>;
}
export interface ClarificationQuestion {
  id: string;
  question: string;
  reason?: string | null;
  recommended_answer?: string | null;
  options?: string[];
  status: 'pending' | 'answered' | 'skipped';
  answer?: string | null;
}
export interface ClarificationBlock {
  type: 'clarification';
  agent_id?: string | null;
  presentation?: PresentationMetadata | null;
  mode:
    | 'auto'
    | 'requirement_alignment'
    | 'grill_me'
    | 'grill_with_docs'
    | 'setup_matt_pocock_skills';
  title: string;
  status: 'waiting' | 'resolved' | 'cancelled';
  current_question?: ClarificationQuestion | null;
  questions: ClarificationQuestion[];
  summary?: string | null;
  metadata?: Record<string, unknown>;
}
export type UploadPurpose =
  | 'message_attachment'
  | 'workspace_import'
  | 'agent_knowledge'
  | 'agent_icon'
  | 'skill_package'
  | 'mcp_config';

export type UploadSafetyStatus = 'pending' | 'passed' | 'blocked' | 'manual_review_required';

export interface AttachmentPreview {
  kind: 'image' | 'archive' | 'document' | 'text' | 'code' | 'unknown';
  url?: string;
  thumbnail_url?: string;
  width?: number;
  height?: number;
  page_count?: number;
  entries_preview?: string[];
  text_preview?: string;
  truncated?: boolean;
}

export interface UploadOut {
  id: string;
  filename: string;
  content_type: string;
  detected_content_type?: string | null;
  size_bytes: number;
  sha256?: string | null;
  purpose: UploadPurpose;
  status: 'uploading' | 'processing' | 'ready' | 'failed' | 'deleted';
  safety_status: UploadSafetyStatus;
  preview?: AttachmentPreview | null;
  error_code?: string | null;
  error_message?: string | null;
}

export interface AttachmentBlock {
  type: 'attachment';
  agent_id?: string | null;
  presentation?: PresentationMetadata | null;
  upload_id: string;
  filename: string;
  content_type: string;
  size_bytes: number;
  purpose: UploadPurpose;
  safety_status: UploadSafetyStatus;
  preview?: AttachmentPreview | null;
  workspace_import?: {
    status: 'pending' | 'imported' | 'failed';
    imported_paths?: string[];
  } | null;
}

export interface TurnControlBlock {
  type: 'turn_control';
  agent_id?: string | null;
  presentation?: PresentationMetadata | null;
  kind: 'guidance' | 'side_chat' | 'queue_action' | 'stop_and_run';
  status:
    | 'received'
    | 'waiting_safe_point'
    | 'applied'
    | 'answered'
    | 'cancelled'
    | 'expired'
    | 'failed';
  control_id?: string | null;
  active_agent_message_id: string;
  title: string;
  body?: string | null;
  source_message_ids?: string[];
  metadata?: Record<string, unknown>;
}
export interface WorkflowBlock {
  type: 'workflow';
  agent_id?: string | null;
  presentation?: PresentationMetadata | null;
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
  presentation?: PresentationMetadata | null;
  title: string;
  tasks: Array<{
    id: string;
    agent_id: string;
    planned_agent_id?: string | null;
    current_agent_id?: string | null;
    final_agent_id?: string | null;
    title: string;
    status: 'pending' | 'running' | 'done' | 'error' | 'interrupted';
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
  | ClarificationBlock
  | AttachmentBlock
  | TurnControlBlock
  | ToolCallBlock;

// ─── Messages ───
export type RequirementAlignmentMode = 'off' | 'strict';
export interface TurnOptions {
  requirement_alignment?: RequirementAlignmentMode;
}
export type Message = Override<
  Schemas['MessageOut'],
  {
    content: ContentBlock[];
    status: MessageStatus;
    is_pinned: boolean;
    turn_options?: TurnOptions;
  }
>;
export type MessageList = Override<Schemas['MessageList'], { items: Message[] }>;
export type SendMessageRequest = Override<
  Schemas['SendMessageRequest'],
  { requirement_alignment?: RequirementAlignmentMode }
>;
export type SendMessageResponse = Override<
  Schemas['SendMessageResponse'],
  { user_message: Message; agent_message: Message }
>;
export type QueueMessageRequest = Override<
  Schemas['QueueMessageRequest'],
  { requirement_alignment?: RequirementAlignmentMode }
>;
export type UpdateQueuedMessageRequest = Override<
  Schemas['UpdateQueuedMessageRequest'],
  { requirement_alignment?: RequirementAlignmentMode | null }
>;
export type QueueMessageResponse = Override<
  Schemas['QueueMessageResponse'],
  { queued_message: Message }
>;
export interface GuidanceRequest {
  content: ContentBlock[];
}
export interface SideChatRequest {
  content: ContentBlock[];
}
export interface QueueReorderRequest {
  message_ids: string[];
}
export interface QueueMergeRequest {
  message_ids: string[];
  separator?: string;
}
export interface QueueReorderResponse {
  messages: Message[];
}
export interface TurnControl {
  id: string;
  conversation_id: string;
  active_agent_message_id: string;
  created_by_message_id?: string | null;
  kind: TurnControlBlock['kind'];
  state: TurnControlBlock['status'];
  payload: Record<string, unknown>;
  applied_at?: string | null;
  created_at: string;
  updated_at: string;
}
export interface TurnControlResponse {
  control: TurnControl;
  user_message?: Message | null;
  agent_message?: Message | null;
}
export type UpdateMessageRequest = Schemas['UpdateMessageRequest'];
export type InterruptMessageResponse = Override<
  Schemas['InterruptMessageResponse'],
  { message: Message }
>;

export type MessageRole = Message['role'];
export type MessageStatus = 'pending' | 'streaming' | 'done' | 'error' | 'interrupted' | 'queued';

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
export type AgentKnowledgeUsage = 'reference' | 'policy' | 'template' | 'example';

export interface AgentKnowledgeRef {
  upload_id: string;
  filename: string;
  label: string;
  usage: AgentKnowledgeUsage;
  content_type: string;
  size_bytes: number;
  sha256: string;
  created_at: string;
}

export interface AgentSkillRef {
  skill_id: string;
  upload_id: string;
  name: string;
  description: string;
  filename: string;
  content_type: string;
  size_bytes: number;
  sha256: string;
  created_at: string;
  metadata?: Record<string, unknown>;
}

export type AgentAssetKind = 'knowledge' | 'skill';
export type AgentAssetStatus = 'active' | 'unbound';
export type AgentAssetVersionAction = 'created' | 'updated' | 'unbound' | 'materialized';
export type AgentAssetUsageStatus = 'injected' | 'skipped' | 'failed';

export interface AgentAssetBindingRef {
  id: string;
  agent_id: string;
  kind: AgentAssetKind;
  status: AgentAssetStatus;
  upload_id: string;
  filename: string;
  content_type: string;
  size_bytes: number;
  sha256: string;
  label?: string | null;
  usage?: AgentKnowledgeUsage | null;
  skill_id?: string | null;
  name?: string | null;
  description?: string | null;
  metadata?: Record<string, unknown>;
  created_at: string;
  updated_at: string;
  unbound_at?: string | null;
}

export interface AgentAssetsResponse {
  knowledge: AgentKnowledgeRef[];
  skills: AgentSkillRef[];
  bindings: AgentAssetBindingRef[];
}

export interface AgentAssetVersionRef {
  id: string;
  binding_id: string;
  version: number;
  action: AgentAssetVersionAction;
  snapshot: Record<string, unknown>;
  actor_user_id?: string | null;
  created_at: string;
}

export interface AgentAssetHistoryResponse {
  items: AgentAssetVersionRef[];
  total: number;
}

export interface AgentAssetUsageEventRef {
  id: string;
  binding_id?: string | null;
  agent_id: string;
  upload_id?: string | null;
  conversation_id?: string | null;
  run_id?: string | null;
  event_type: string;
  status: AgentAssetUsageStatus;
  reason?: string | null;
  metadata?: Record<string, unknown>;
  created_at: string;
}

export interface AgentAssetUsageResponse {
  items: AgentAssetUsageEventRef[];
  total: number;
}

// ─── SSE events (hand-written; not in OpenAPI) ───
export interface QueuedNextPayload {
  user_message: Message;
  agent_message: Message;
  queue_remaining_count: number;
}

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
      event: 'message_interrupted';
      data: {
        message_id: string;
        conversation_id?: string;
        agent_id?: string;
        reply_to_id?: string | null;
        status?: 'interrupted';
        total_blocks?: number;
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
  | {
      event: 'turn_control';
      data: {
        turn_control: TurnControlBlock;
      };
    }
  | {
      event: 'done';
      data: {
        message_id?: string;
        total_blocks?: number;
        agent_id?: string;
        queued_next?: QueuedNextPayload;
      };
    }
  | {
      event: 'error';
      data: {
        error_code?: string;
        error?: string;
        agent_id?: string;
        queued_next?: QueuedNextPayload;
      };
    }
  | {
      event: 'interrupted';
      data: {
        message_id?: string;
        conversation_id?: string;
        total_blocks?: number;
        agent_id?: string;
        status?: 'interrupted';
        queued_next?: QueuedNextPayload;
      };
    }
  | { event: 'agent_switch'; data: { from_agent: string; to_agent: string; task?: string } }
  | {
      event: 'tool_call';
      data: {
        call_id: string;
        tool_name: string;
        tool_arguments: Record<string, unknown>;
        metadata?: Record<string, unknown>;
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
