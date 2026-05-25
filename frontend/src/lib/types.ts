/**
 * ⚠️ This file is normally auto-generated from `shared/openapi.yaml` via:
 *
 *   pnpm gen:types
 *
 * The hand-written types below are placeholders so the project compiles
 * before the first generation. Once generated, this file will be overwritten.
 */

// ─── Domain types (placeholder; will be replaced by generated `components.schemas`) ───

export interface User {
  id: string;
  username: string;
  avatar_url: string | null;
  created_at: string;
}

export interface AuthResponse {
  access_token: string;
  token_type: 'bearer';
  expires_in: number;
  user: User;
}

export interface Conversation {
  id: string;
  title: string;
  mode: 'single' | 'group';
  agent_ids: string[];
  is_pinned: boolean;
  is_archived: boolean;
  last_message_at: string;
  last_message_preview?: string | null;
  created_at: string;
}

export type ContentBlock =
  | { type: 'text'; text: string }
  | { type: 'code'; language: string; code: string }
  | { type: 'diff'; filename: string; before: string; after: string }
  | { type: 'web_preview'; url: string; title?: string | null; description?: string | null }
  | { type: 'file'; filename: string; url: string; size: number; mime_type: string };

export type MessageRole = 'user' | 'agent' | 'system';
export type MessageStatus = 'pending' | 'streaming' | 'done' | 'error';

export interface Message {
  id: string;
  conversation_id: string;
  role: MessageRole;
  agent_id: string | null;
  content: ContentBlock[];
  reply_to_id: string | null;
  status: MessageStatus;
  is_pinned: boolean;
  created_at: string;
}

export interface Agent {
  id: string;
  name: string;
  provider: 'claude' | 'openai' | 'custom';
  avatar_url: string;
  capabilities: string[];
  system_prompt: string | null;
  config: Record<string, unknown>;
  is_builtin: boolean;
  created_at: string;
}

// ─── SSE events ───

export type StreamEvent =
  | { event: 'start'; data: { message_id?: string; agent_id?: string } }
  | { event: 'block_start'; data: { block_index: number; block_type: string; metadata?: Record<string, unknown> } }
  | { event: 'delta'; data: { block_index: number; text_delta?: string; code_delta?: string } }
  | { event: 'block_end'; data: { block_index: number } }
  | { event: 'done'; data: { message_id?: string; total_blocks?: number } }
  | { event: 'error'; data: { error_code?: string; error?: string } }
  | { event: 'agent_switch'; data: { from_agent: string; to_agent: string; task?: string } }
  | { event: 'heartbeat'; data: Record<string, never> };
