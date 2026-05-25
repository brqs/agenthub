/**
 * REST adapters: typed wrappers over `api.ts` that hooks call.
 *
 * Components/hooks MUST NOT call axios directly — go through these adapters
 * so Mock ↔ Real switching stays in one place (see [src/lib/env.ts]).
 *
 * Slice 1 scope: Auth + Conversations list + Agents list.
 * Mutations (send message, regenerate, etc.) land in later slices.
 */

export * as authAdapter from './auth';
export * as conversationsAdapter from './conversations';
export * as agentsAdapter from './agents';
export * as messagesAdapter from './messages';
