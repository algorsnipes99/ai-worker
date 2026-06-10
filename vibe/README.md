# Vibe Docs — Navigation Guide

Quick-start reference for LLM sessions working on this codebase.

## Which doc to read first

| Your task | Read first |
|-----------|-----------|
| "What does this system do?" | [overview.md](overview.md) |
| "Where do I start for task X?" | [context-map.md](context-map.md) |
| "How does agent execution work?" | [agents.md](agents.md) |
| "How do I add/modify a tool?" | [tools.md](tools.md) |
| "How does state/persistence work?" | [services.md](services.md) |
| "How does data flow end-to-end?" | [execution-flow.md](execution-flow.md) |
| "Why isn't X being triggered?" | [execution-flow.md](execution-flow.md) — check MongoDB signal flags |
| "Why is a tool blocked?" | [services.md](services.md) — PermissionManager section |

## Doc Summaries

- **[overview.md](overview.md)** — Architecture diagram, component table, key design decisions, external deps
- **[context-map.md](context-map.md)** — File→purpose index, MongoDB shapes, state machine, common task starting points, gotchas
- **[agents.md](agents.md)** — BaseAgent lifecycle, all agent types, how to add a new agent
- **[tools.md](tools.md)** — All 22+ tools, FunctionCallingSystem flow, how to add a new tool
- **[services.md](services.md)** — MessageService, StateService, PermissionManager, exception handling
- **[execution-flow.md](execution-flow.md)** — Full end-to-end flow, message array evolution, compression, permission exception, delegation

## Planned Changes

- **[redis-pubsub-plan.md](redis-pubsub-plan.md)** — Replace MongoDB polling with Redis pub/sub (notify-then-fetch pattern)

## TL;DR

This is a **MongoDB-triggered multi-agent AI worker**. MongoDB docs with `run_signal=true` trigger specialized AI agents that use tool calling (DeepSeek LLM) to complete tasks. Full execution state is persisted for resumption after interruptions, permission denials, or pauses.

Entry point: `agent-worker.py` → `agents/base_agent.py` → `functions/function_calling_system.py`
