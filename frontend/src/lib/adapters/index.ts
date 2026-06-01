/**
 * REST adapters: typed wrappers over `api.ts` that hooks call.
 *
 * Components/hooks MUST NOT call axios directly. Use these adapters so API
 * calls stay typed and centralized.
 *
 * Slice 1 scope: Auth + Conversations list + Agents list.
 * Mutations (send message, regenerate, etc.) land in later slices.
 */

export * as authAdapter from './auth';
export * as conversationsAdapter from './conversations';
export * as agentsAdapter from './agents';
export * as messagesAdapter from './messages';
export * as workspacesAdapter from './workspaces';
export * as deploymentsAdapter from './deployments';
