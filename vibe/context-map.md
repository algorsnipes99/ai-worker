# Context Map (Token-Efficient Reference)

## Quick Orientation

**What this is**: MongoDB-triggered multi-agent AI worker. DeepSeek LLM + tool calling. Stateful with full resumption support.

**Entry point**: `agent-worker.py` — polls MongoDB every 5s for `{run_signal: true}` docs.

**To understand any task type**, read the relevant agent file + its system prompt in `prompts/`.

---

## File → Purpose (one-line)

```
agent-worker.py                          Main loop: MongoDB poll → thread dispatch
agents/base_agent.py                     Stateful agent base: LLM loop, resumption, state machine
agents/database_agent.py                 SQL operations (MySQL/Postgres/SQLite/MSSQL)
agents/file_manager_agent.py             File read/write/edit + commands + codebase search
agents/command_prompt_agent.py           Shell command execution
agents/api_agent.py                      HTTP API calls (GET/POST)
agents/codebase_expert_agent.py          RAG-based codebase Q&A
agents/summarization_agent.py            Conversation compression via summarization
functions/function_calling_system.py     LLM call + tool parse + execute + permission check
functions/function_registry.py           Tool catalog; generates JSON schemas for LLM
functions/function.py                    Abstract base for all tools
functions/delegate_to_agent_function.py  Create child agents; key for multi-agent workflows
functions/file_edit_function.py          Atomic file edit with backup
functions/command_function.py            Shell command runner (subprocess)
functions/sql_query.py                   SQL SELECT/INSERT/UPDATE/DELETE
functions/codebase_query_function.py     Delegates to Code-Repository-RAG for code search
services/message_service.py             Save/load conversation history in MongoDB
services/state_service.py               Save/load execution state snapshots in MongoDB
utils/permission_manager.py             active_permissions.json read/write; gating logic
exceptions/tool_permission_exception.py  Raised when tool needs human approval
conversation_compressor/                 Three strategies: remove tools, summarize, combined
active_permissions.json                  Live permission state (tool approvals/denials)
prompts/*.txt                            System prompts per agent type
```

---

## MongoDB Document Shape

**Task trigger (messages collection)**:
```json
{
  "guid": "<message_guid>",
  "run_signal": true,
  "user_request": "Do X",
  "plan": "Optional plan text",
  "agent_class_name": "FileManagerAgent",
  "parent_message_guid": null,
  "messages": [],
  "status": "active"
}
```

**State snapshot (states collection)**:
```json
{
  "guid": "<message_guid>",
  "state": {
    "status": "BEFORE_TOOL_CALL | AFTER_TOOL_CALL | COMPLETED | ERROR",
    "step": 3,
    "pending_tool_calls": [...],
    "last_tool_results": [...],
    "started_at": "...",
    "last_updated": "..."
  }
}
```

---

## Execution State Machine

```
INIT → [call LLM] → tool calls?
  YES: BEFORE_TOOL_CALL → [execute tools] → AFTER_TOOL_CALL → [call LLM again] → loop
  NO:  COMPLETED
  ERR: ERROR (state saved, resumable)
  PAUSE: pause_signal=True in MongoDB → agent halts, state saved
```

Resumption entry points in `base_agent.py`:
- `_resume_before_tool_call()` — re-execute pending tools
- `_resume_after_tool_call()` — append tool results, continue LLM loop
- `_resume_completed()` — start new turn on completed session

---

## Tool Permission Flow

```
FunctionCallingSystem calls tool
  → check PermissionManager.check_permission(tool_name)
  → None (unknown): raise ToolPermissionRequiredException
  → True: execute, then consume_permission()
  → False: return denial message to LLM
```

Permission state lives in `active_permissions.json`. External interface must set permissions before resuming agent.

---

## Common Task Starting Points

| Task | Start reading |
|------|--------------|
| Add a new agent type | `agents/base_agent.py`, then any existing agent |
| Add a new tool | `functions/function.py`, then any existing tool; register in agent's `__init__` |
| Debug execution resumption | `agents/base_agent.py` (run/resume methods) + `services/state_service.py` |
| Change permission behavior | `utils/permission_manager.py` + `exceptions/tool_permission_exception.py` |
| Modify compression | `conversation_compressor/` (pick a strategy) |
| Change LLM parameters | `functions/function_calling_system.py` |
| Add new agent system prompt | `prompts/` + wire in agent's `system_prompt` property |
| Understand MongoDB schema | `services/message_service.py` + `services/state_service.py` |
| Multi-agent delegation | `functions/delegate_to_agent_function.py` |

---

## Key Gotchas

1. **`run_signal` cleared immediately** before agent runs — prevents double-processing but means errors after clearing won't re-trigger.
2. **`active_permissions.json` is stateful** — stale entries can block or auto-grant tools unexpectedly. Check it when debugging permission issues.
3. **GUIDs are the join key** — messages and states linked by `guid`. Parent-child agents linked by `parent_message_guid`. Resume GUIDs passed back through `ToolPermissionRequiredException`.
4. **CodebaseExpertAgent default paths hardcoded** to `C:\dev\mqx\*` — must override with env vars for other repos.
5. **Thread-local MongoDB clients** — each thread creates its own client; connection pooling is per-thread.
6. **SummarizationAgent is NOT a task agent** — it's only called during compression, not from MongoDB task triggers.
7. **Compression triggered separately** by `compress_conversation=True` flag on MongoDB doc — different path from normal `run_signal`.
