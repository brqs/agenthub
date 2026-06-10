# Custom Agent Server Wrapper and Skills Spec

## Status

Implemented direction: 2026-06-10.

This spec replaces the older "from-scratch builtin custom Agent" roadmap. A user-created custom Agent is now a **server Agent wrapper**: it chooses one server-provided base Agent and adds user-facing routing/profile fields plus optional Skills.

Supported base Agents:

- `claude-code`
- `codex-helper`
- `opencode-helper`

The custom Agent does not own a model, API key, MCP server, shell command, or independent runtime. Execution always goes through the selected base Agent adapter.

## Goals

- Let non-technical users create a useful Agent by choosing a base Agent and filling understandable fields.
- Keep runtime behavior aligned with existing server Agent contracts for Claude Code, Codex, and OpenCode.
- Make Orchestrator routing better by exposing wrapper planning fields.
- Keep Skills as the only extra asset capability in the main custom Agent path.
- Remove model backpack, knowledge-first builder, MCP JSON, builtin runtime permission setup, and advanced runtime settings from the user-facing create flow.

## Non-Goals

- User-provided model API keys for custom Agents.
- Creating `provider="builtin"` custom Agents.
- User-defined MCP servers in this workflow.
- Custom shell commands, sandbox mode, CLI auth, runtime env, or adapter args.
- Knowledge files as a first-class builder step. Lower-level knowledge endpoints may remain for compatibility, but the product path is Skills-only.
- Migrating old custom Agents. Existing non-builtin custom Agents are intentionally deleted by migration per product decision.

## Backend Contract

Custom Agents still live in the `agents` table:

- `is_builtin=false`
- `provider` is inherited from the base Agent: `claude_code | codex | opencode`
- `config.custom_agent_mode="server_agent_wrapper"`
- `config.base_agent_id` is one of `claude-code | codex-helper | opencode-helper`
- `config.wrapper_profile` stores user-facing transfer fields

Wrapper profile:

```ts
type AgentWrapperProfile = {
  role?: string | null;
  purpose?: string | null;
  planning_profile?: string | null;
  planning_strengths: string[];
  planning_weaknesses: string[];
  preferred_task_types: string[];
  capabilities: string[];
  output_style?: string | null;
  boundaries: string[];
};
```

### Create Agent

```http
POST /api/v1/agents
```

Required semantics:

- `provider` must be `claude_code`, `codex`, or `opencode`.
- `config.custom_agent_mode` must be `server_agent_wrapper`.
- `config.base_agent_id` must match `provider`.
- `config.wrapper_profile` must be an object.

Forbidden user config fields include:

- `command`
- `args`
- `sandbox_mode`
- `runtime auth`
- `model_profile`
- `api_key`, `secret`, `token`, `authorization`
- MCP server JSON
- builtin tool permissions

B1/B2 copies safe runtime defaults from the base Agent, then overlays only wrapper/profile fields. The copied runtime config remains controlled by server seed/configuration.

### Update Agent

```http
PATCH /api/v1/agents/{agent_id}
```

Allowed for wrappers:

- display fields such as name/avatar/capabilities/system prompt
- `config.wrapper_profile`

Disallowed:

- changing `base_agent_id`
- changing provider/runtime command/auth/model/MCP/sandbox fields

### Skills

Retained endpoints:

```http
POST /api/v1/agents/{agent_id}/skills
PATCH /api/v1/agents/{agent_id}/skills/{skill_id}
DELETE /api/v1/agents/{agent_id}/skills/{skill_id}
```

Accepted files:

- `.md`
- `.markdown`
- `SKILL.md`

Skill imports do not execute scripts. They create metadata and a binding that is injected into runtime prompts through the existing asset service.

## Registry Runtime Contract

When `registry.get_adapter(custom_agent_id)` sees `custom_agent_mode=server_agent_wrapper`:

1. Load `base_agent_id`.
2. Use the base Agent provider and adapter class.
3. Merge base runtime config with wrapper fields.
4. Combine base system prompt, custom system prompt, wrapper profile, and uploaded Skills.
5. Instantiate the adapter with the custom Agent id so UI/timeline attribution uses the user-created Agent name.

The wrapper cannot override executable runtime settings.

## Orchestrator Contract

Orchestrator sees wrappers as normal conversation members, but receives additional planning fields:

- `planning_profile`
- `planning_strengths`
- `planning_weaknesses`
- `preferred_task_types`
- `capabilities`
- display name
- real provider/base runtime availability

Group-scoped dispatch remains mandatory. A wrapper can only be selected if it is in the current conversation and its base runtime is available.

## Frontend Contract

The create dialog is a "服务器 Agent 套壳构建器":

1. Choose base Agent: Claude Code, Codex Helper, or OpenCode Helper.
2. Fill transfer fields: name, purpose, role, strengths, weaknesses, task types, scheduling description, output style, boundaries.
3. Upload optional Skills.
4. Confirm base Agent, profile summary, and Skill count.

Removed from the main UI:

- model backpack
- "AgentHub 免费 DeepSeek / 使用我的 API"
- advanced config
- MCP JSON
- builtin tool permissions
- knowledge upload step

Agent detail shows:

- base Agent
- wrapper profile summary
- Skills management
- test run
- asset status

## Data Cleanup

The migration `e2f3a4b5c6d7_reset_custom_agents_for_wrappers` removes pre-wrapper custom Agent data:

- delete `is_builtin=false` agents
- remove those ids from `conversations.agent_ids`
- delete related asset bindings, versions, usage events
- clear `user_model_accounts`

This is intentionally destructive because the old custom Agent design is no longer compatible with the product direction.

## Tests

Backend:

- wrapper create validates provider/base match
- forbidden config fields return 422
- registry instantiates the base adapter and injects wrapper profile + Skills
- Orchestrator planning receives wrapper fields
- migration removes old custom Agent references
- model account API routes are not mounted

Frontend:

- create flow sends wrapper payload
- no model backpack/advanced/MCP UI appears
- Skills upload accepts Markdown and ignores unsupported files
- detail page shows base Agent, profile, and Skills

Manual smoke:

- Create a wrapper named "前端页面实现助手" based on OpenCode.
- Upload a Skill.
- Add it to a group chat.
- Ask Orchestrator for a frontend artifact.
- Timeline shows the custom Agent name while execution uses OpenCode runtime.
