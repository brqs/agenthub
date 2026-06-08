# Custom Agent Asset Persistence, Version History, and Usage Spec

## Status

Implementation target: 2026-06-08.

## Goal

Move custom Agent knowledge and skill bindings out of ad hoc `Agent.config`
arrays into normalized backend tables while keeping the public API and existing
runtime behavior compatible.

The old `Agent.config["knowledge"]` / `Agent.config["skills"]` arrays remain a
compatibility mirror during the migration window.

## Backend

### Tables

`agent_asset_bindings`

```text
id UUID primary key
agent_id varchar(64) references agents(id) on delete cascade
upload_id UUID references uploads(id) on delete cascade
owner_user_id UUID references users(id) on delete cascade
kind varchar(16)  -- knowledge | skill
status varchar(16) -- active | unbound
label varchar(160) nullable
usage varchar(32) nullable
skill_id varchar(96) nullable unique
name varchar(160) nullable
description varchar(240) nullable
metadata jsonb not null default {}
created_at timestamptz not null default now()
updated_at timestamptz not null default now()
unbound_at timestamptz nullable
```

Indexes:

- `(agent_id, kind, status, created_at)`
- `(owner_user_id, created_at)`
- unique `(agent_id, upload_id, kind)` for active replacement semantics.

`agent_asset_versions`

```text
id UUID primary key
binding_id UUID references agent_asset_bindings(id) on delete cascade
version integer not null
action varchar(32) -- created | updated | unbound | materialized
snapshot jsonb not null
actor_user_id UUID references users(id) nullable
created_at timestamptz not null default now()
```

`agent_asset_usage_events`

```text
id UUID primary key
binding_id UUID references agent_asset_bindings(id) on delete set null
agent_id varchar(64) references agents(id) on delete cascade
upload_id UUID references uploads(id) on delete set null
conversation_id UUID references conversations(id) nullable
run_id varchar(128) nullable
event_type varchar(32) -- context_injection | preview | download
status varchar(32) -- injected | skipped | failed
reason varchar(128) nullable
metadata jsonb not null default {}
created_at timestamptz not null default now()
```

### API

Existing endpoints keep their paths and response shapes:

- `POST /api/v1/agents/{agent_id}/knowledge`
- `PATCH /api/v1/agents/{agent_id}/knowledge/{upload_id}`
- `DELETE /api/v1/agents/{agent_id}/knowledge/{upload_id}`
- `POST /api/v1/agents/{agent_id}/skills`
- `PATCH /api/v1/agents/{agent_id}/skills/{skill_id}`
- `DELETE /api/v1/agents/{agent_id}/skills/{skill_id}`

New read endpoints:

- `GET /api/v1/agents/{agent_id}/assets`
  - returns active knowledge and skills plus summary counts.
- `GET /api/v1/agents/{agent_id}/assets/history`
  - returns version events, newest first.
- `GET /api/v1/agents/{agent_id}/assets/usage`
  - returns runtime usage events, newest first.

### Runtime Injection

`build_agent_asset_context()` must read active rows from
`agent_asset_bindings`. During rollout, if no rows exist for an Agent but old
config arrays exist, it may lazily materialize rows or fallback to config.

Injection records usage:

- `event_type="context_injection"` and `status="injected"` when text was
  included.
- `event_type="context_injection"` and `status="skipped"` with reason for
  missing upload, owner mismatch,
  blocked safety status, deleted upload, unsupported type, or empty text.

Usage recording must be best-effort and never fail the user message.

### Compatibility Mirror

After create/update/delete:

- `Agent.config["knowledge"]` and `Agent.config["skills"]` are rebuilt from
  active rows so older frontend code continues to work.
- The mirror is considered read-compatible, not source of truth.

## Frontend

### Data Source

Short term:

- Continue rendering from `agent.config.knowledge` and `agent.config.skills`
  for compatibility.

Enhancement:

- `useAgentAssets` may fetch `GET /agents/{id}/assets/history` and
  `/usage` when the details panel is open.

### UI

Agent detail panel adds a compact `资产记录` subsection:

- Version history: created / updated / unbound.
- Usage events: injected / skipped, with time and reason.
- History and usage are collapsed by default.

Errors loading history/usage must not hide active assets.

## Acceptance

- Existing upload/edit/unbind APIs still work.
- Active assets are persisted in independent tables.
- Agent config mirrors active rows.
- Runtime injection consumes table rows and records usage events.
- History API shows create/update/unbind snapshots.
- Tests cover create/update/delete/injection usage and compatibility mirror.
