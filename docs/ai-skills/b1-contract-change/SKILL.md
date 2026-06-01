---
name: b1-contract-change
description: Use when implementing or reviewing AgentHub B1 backend contract changes, including API/schema/OpenAPI/SSE persistence updates, ownership boundaries, validation commands, and AI collaboration evidence updates.
---

# B1 Contract Change Skill

## When To Use

Use this skill when a task changes B1-owned backend contracts, especially:

- FastAPI endpoints or response shapes.
- Pydantic schemas under `backend/app/schemas/**`.
- `shared/openapi.yaml`.
- SSE stream persistence or message ContentBlock behavior.
- Workspace or conversation/message API behavior.

## Required Reading

Before editing, read:

1. `AGENTS.md`
2. The related B1 spec under `docs/b1/spec/`
3. `shared/openapi.yaml`
4. The affected backend schema / API / service files
5. Existing tests for the touched behavior

If the task crosses B2 or F boundaries, also read the related `docs/b2/spec/` or `docs/frontend/spec/` file.

## Workflow

1. Confirm owner boundaries.
   - B1 owns API, schema, persistence, DB/service behavior, Workspace, and stream gateway persistence.
   - B2 owns Agent runtime behavior and production of runtime metadata such as true child-agent attribution.
   - F owns generated types, UI state, and rendering.

2. Update the contract source of truth.
   - API/schema changes must update `shared/openapi.yaml`.
   - Pydantic schemas must match OpenAPI.
   - Public behavior changes must be reflected in the related spec.

3. Preserve compatibility.
   - Prefer optional fields for additive JSON changes.
   - Do not require database migrations for JSONB-only optional additions.
   - Old messages and old stream chunks must continue to parse.

4. Avoid text parsing for structured semantics.
   - Do not infer ownership, tool state, or routing from natural-language text such as `@agent`.
   - Persist structured fields only when B2 or the stream protocol provides structured data.

5. Add tests before handoff.
   - Cover new behavior, old compatibility, and boundary cases.
   - Include at least one API or persistence-level test when the public response changes.

## Validation

Use the smallest targeted tests first, then run full backend checks when practical:

```bash
docker compose exec -T backend pytest <targeted-tests> -q
docker compose exec -T backend pytest -q
docker compose exec -T backend ruff check
```

If `shared/openapi.yaml` changes, notify F to run:

```bash
cd frontend
pnpm gen:types
pnpm test
pnpm build
```

## Evidence Updates

For competition-grade AI collaboration evidence:

- Current contract: update `docs/b1/spec/*.spec.md`.
- Reusable process: update this skill when a repeated B1 workflow emerges.
- Cross-team decision: append `docs/ai-collaboration-log.md`.
- PR description: call out contract changes, owner boundaries, and validation results.
