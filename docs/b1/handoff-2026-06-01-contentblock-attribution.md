# B1 Handoff: Group Observer Context + ContentBlock Attribution

> Date: 2026-06-01
> Owner: B1 Backend Core
> Purpose: help the next AI agent continue this work without losing the spec / skill / rules discipline.

## 1. First Read

Before changing anything, read these in order:

1. `AGENTS.md`
2. `docs/ai-skills/b1-contract-change/SKILL.md`
3. `docs/b1/spec/group-observer-context.spec.md`
4. `docs/b1/spec/message-content-block-attribution.spec.md`
5. `docs/b2/spec/orchestrator-message-attribution.spec.md`
6. `docs/frontend/spec/orchestrated-message-rendering.spec.md`

Key rule: do not treat chat history as the source of truth. Specs, skills, rules, OpenAPI, and tests are the handoff contract.

## 2. Current Work Summary

Two B1-side capabilities have been implemented locally:

### Group Agent observer context

Status: implemented and tested.

What it does:

- `stream.py` passes the current target `message.agent_id` into `build_context()`.
- Group context now tells the current agent who it is and that it is observing a group conversation.
- Labeled messages such as `[Agent: claude-code] ...` are explained as other agents' statements, not the current agent's own work.
- Single conversations do not receive this group observer prompt.

Primary files:

- `backend/app/api/v1/stream.py`
- `backend/app/services/context_builder.py`
- `backend/tests/test_context_builder.py`
- `backend/tests/test_stream_tool_calls.py`
- `docs/b1/spec/group-observer-context.spec.md`

### B1 ContentBlock attribution

Status: implemented and tested locally.

What it does:

- All ContentBlock schemas now support optional `agent_id`.
- OpenAPI includes optional `agent_id` on text, code, diff, web_preview, file, and tool_call blocks.
- `StreamContentAccumulator` persists `StreamChunk.agent_id` to content blocks.
- If `chunk.agent_id` is absent, B1 falls back to `chunk.metadata["agent_id"]`.
- `tool_result` updates the existing tool block without overwriting its original `agent_id`.
- diff block finalization preserves `agent_id`.
- Legacy blocks without `agent_id` remain valid.

Primary files:

- `backend/app/schemas/message.py`
- `backend/app/api/v1/stream_accumulator.py`
- `shared/openapi.yaml`
- `backend/tests/test_stream_content_blocks.py`
- `backend/tests/test_stream_tool_calls.py`
- `docs/b1/spec/message-content-block-attribution.spec.md`

## 3. AI Collaboration Assets Added

The project is graded on AI collaboration practices, so this work also adds collaboration artifacts:

- `docs/ai-skills/b1-contract-change/SKILL.md`
- `AGENTS.md` section `9.4 协作资产规则`
- `docs/README.md` link to the B1 skill
- `docs/ai-collaboration-log.md` entry for the B1 AI collaboration four-piece set
- P1/P2 follow-up coverage in `docs/b1/spec/group-observer-context.spec.md`

Update: the B1 group observer P1/P2 follow-up is now covered by regression tests and the spec debug note. It remains B1-only guardrail coverage; B2 still owns Orchestrator child-agent prompt construction.

Future agents must keep this loop alive:

```text
code change
+ spec update
+ skill/rules update when the workflow becomes reusable
+ collaboration log update for important decisions
+ tests / review evidence
```

## 4. Current Review Note

There is one known documentation issue from review:

- `docs/ai-collaboration-log.md` currently says the B1 collaboration artifact update did not implement the `message-content-block-attribution.spec.md` code. That was true when the log entry was created, but the code implementation has since been completed locally.

Recommended fix before PR:

- Either update that log entry to mention that implementation followed afterwards, or add a new `2026-06-01` entry specifically for the ContentBlock attribution implementation.

Do not change the owner boundary while fixing the text:

- B1 saves attribution.
- B2 produces true runtime attribution.
- F consumes attribution for rendering.

## 5. Validation Already Run

These commands have passed locally in Docker:

```bash
docker compose exec -T backend pytest tests/test_context_builder.py tests/test_stream_tool_calls.py -q
docker compose exec -T backend pytest tests/test_stream_tool_calls.py tests/test_stream_content_blocks.py -q
docker compose exec -T backend pytest -q
docker compose exec -T backend ruff check
git diff --check
```

Most recent full backend result:

```text
452 passed, 7 skipped, 1 warning
```

The warning is an existing FastAPI deprecation warning in `tests/test_b1_quality.py::test_context_compression_config_rejects_unsupported_model`.

## 6. Important Boundaries

Do not implement these in B1 unless explicitly asked:

- B2 Orchestrator generation of real `StreamChunk.agent_id`.
- B2 removal of plain text `@agent` headers.
- Frontend grouped rendering UI.
- Frontend type generation.

B1 should only ensure that structured attribution, once provided, is preserved through schema, OpenAPI, SSE persistence, and message API output.

## 7. Working Tree Notes

There is an older untracked local file:

```text
docs/b1/handoff-2026-05-31-runtime-integration.md
```

Earlier instruction said that older handoff does not need to be submitted to GitHub. Do not stage it unless the user explicitly changes that instruction.

If committing this work, stage only intentional files. Suggested included files:

```text
AGENTS.md
backend/app/api/v1/stream.py
backend/app/services/context_builder.py
backend/app/api/v1/stream_accumulator.py
backend/app/schemas/message.py
backend/tests/test_context_builder.py
backend/tests/test_stream_content_blocks.py
backend/tests/test_stream_tool_calls.py
docs/README.md
docs/ai-collaboration-log.md
docs/ai-skills/b1-contract-change/SKILL.md
docs/b1/spec/group-observer-context.spec.md
docs/b1/spec/message-content-block-attribution.spec.md
docs/b1/handoff-2026-06-01-contentblock-attribution.md
shared/openapi.yaml
```

Before commit / PR, run:

```bash
git status --short
git diff --check
docker compose exec -T backend pytest tests/test_stream_tool_calls.py tests/test_stream_content_blocks.py -q
docker compose exec -T backend pytest -q
docker compose exec -T backend ruff check
```

## 8. PR Description Checklist

The PR should clearly say:

- Group observer context is implemented for model input semantics.
- ContentBlock `agent_id` persistence is implemented for model output attribution.
- No database migration is required because `messages.content` is JSONB and `agent_id` is optional.
- No public endpoint was added.
- B2 still owns production of true child-agent attribution.
- F should regenerate types and render with `block.agent_id ?? message.agent_id`.
- Tests passed with command output.

## 9. How The Next Agent Should Work

When continuing this thread, the next agent should:

1. Read this handoff and the required docs in section 1.
2. Check `git status --short`.
3. Fix the collaboration log wording noted in section 4.
4. Re-run targeted tests if any code changed.
5. Review the final diff.
6. If asked to submit, stage intentional files only and exclude the older untracked handoff unless instructed otherwise.
7. After any meaningful change, update the relevant spec / skill / rules / collaboration log instead of leaving the reasoning only in chat.
