# Custom Agent Model Backpack Spec

## Status

Deprecated on 2026-06-10.

The model backpack design has been removed from the active custom Agent product path. Custom Agents are now server Agent wrappers around `claude-code`, `codex-helper`, or `opencode-helper`.

## Why Deprecated

The earlier model backpack design let users choose a model provider, save an API key, and bind that model account to a from-scratch builtin custom Agent. That created several problems for AgentHub's current product direction:

- it exposed model/runtime complexity to non-technical users;
- it duplicated existing server runtime contracts;
- it mixed user API keys with custom Agent creation;
- it made Orchestrator availability harder to reason about;
- it overlapped with Claude Code, Codex, and OpenCode adapters that already own their runtime auth.

## Current Replacement

Use `docs/spec/custom-agent-assets.spec.md` as the current source of truth.

Current custom Agent configuration:

- choose a server base Agent;
- fill wrapper transfer fields;
- optionally upload Skills;
- execute through the selected base Agent adapter;
- keep model/auth/runtime configuration server-controlled.

## Removed Interfaces

These routes are no longer mounted:

- `GET /api/v1/model-providers`
- `GET /api/v1/model-accounts`
- `POST /api/v1/model-accounts`
- `PATCH /api/v1/model-accounts/{id}`
- `DELETE /api/v1/model-accounts/{id}`
- `POST /api/v1/model-accounts/{id}/verify`

The `user_model_accounts` table may remain temporarily for migration compatibility, but active UI and API code must not depend on it.
