# Services Layer

## Overview

Four services manage persistence and access control.

```
MessageService    — conversation history (MongoDB: messages collection)
MachineService    — machine online/offline status (MongoDB: machines collection)
StateService      — execution state snapshots (MongoDB: states collection)
PermissionManager — tool approval state (local: active_permissions.json)
```

---

## MessageService (`services/message_service.py`)

**Responsibility**: Persist and load LLM conversation message arrays.

**MongoDB collection**: `MONGODB_COLLECTION_NAME` env var (default: `messages`)

**Document shape**:
```json
{
  "guid": "unique-execution-id",
  "messages": [
    {"role": "system", "content": "..."},
    {"role": "user", "content": "..."},
    {"role": "assistant", "content": "...", "tool_calls": [...]},
    {"role": "tool", "tool_call_id": "...", "content": "..."}
  ],
  "agent_class_name": "FileManagerAgent",
  "parent_message_guid": null,
  "status": "active | complete | paused",
  "run_signal": false,
  "pause_signal": false,
  "machine_id": "<OS/registry machine GUID>",
  "machine_name": "<hostname>",
  "target_machine_id": "<machine_id to route this task to, or null for any>",
  "token_usage": {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}
}
```

`machine_id` and `machine_name` are written by `save_messages()` on every call, reflecting the machine that last processed the conversation. `target_machine_id` is set at conversation creation by the UI and used by `agent-worker.py` to filter task pickup.

`token_usage` is the raw `usage` object from the most recent DeepSeek `chat/completions` response (captured in `BaseAgent._process_with_tools` as `self.last_token_usage` and passed into `save_messages`). Absent until the first LLM call completes. The UI (mongo-chat-ui) reads `token_usage.total_tokens` to show context-window usage, falling back to a client-side character-based estimate if the field is missing.

**Key methods**:
- `save_messages(guid, messages, token_usage=None)` — upsert by guid; `token_usage` is only set in the doc when provided
- `load_messages(guid)` — load with fallback search (exact → with parent GUID → regex)
- `update_status(guid, status)` — set active/complete/paused
- `check_and_clear_pause_signal(guid) → bool` — atomically read + clear pause flag

**Fallback loading strategy**: If exact GUID match fails, tries finding doc where the GUID appears within stored message content (for child agent resumption). This handles cases where child agent GUID is embedded in parent messages.

---

## MachineService (`services/machine_service.py`)

**Responsibility**: Register/deregister this machine's online/offline status in MongoDB
and manage the one-time device pairing flow that links the machine to a Firebase user.

**MongoDB collections**:
- `MONGODB_MACHINES_COLLECTION` env var (default: `machines`)
- `MONGODB_PAIRING_TOKENS_COLLECTION` env var (default: `pairingtokens`)

**Machine document shape**:
```json
{
  "machine_id": "<OS/registry machine GUID>",
  "machine_name": "<hostname>",
  "user_guid": "<Firebase UID — written by backend after pairing>",
  "status": "online | offline",
  "last_seen": "2024-01-01T00:01:00"
}
```

`user_guid` is absent until pairing completes — written by the Express backend after
verifying the user's Firebase ID token (never written directly by the worker).

**Key methods**:
- `is_paired() -> bool` — True if machine doc exists with a non-empty `user_guid`
- `create_pairing_token(token)` — upsert pending token into `pairingtokens` (TTL 10 min)
- `wait_for_pairing(timeout_seconds=600) -> bool` — poll every 5s until `user_guid` appears
- `register()` — upsert with `status='online'`, update `last_seen` (does NOT touch `user_guid`)
- `deregister()` — set `status='offline'`, update `last_seen`

**When called**:
- Pairing check runs in `AgentWorker.__init__()` before `register()`; blocks until done or timeout
- `register()` is called once pairing is confirmed
- `deregister()` is called in `AgentWorker.handle_shutdown()` after the thread pool drains

---

## StateService (`services/state_service.py`)

**Responsibility**: Persist execution state snapshots so agents can resume after interruption.

**MongoDB collection**: `MONGODB_STATE_COLLECTION` env var (default: `states`)

**Document shape**:
```json
{
  "guid": "unique-execution-id",
  "parent_message_guid": null,
  "state": {
    "status": "BEFORE_TOOL_CALL",
    "step": 3,
    "pending_tool_calls": [
      {"id": "call_xyz", "function": {"name": "readFile", "arguments": "{...}"}}
    ],
    "last_tool_results": [...],
    "started_at": "2024-01-01T00:00:00Z",
    "last_updated": "2024-01-01T00:01:00Z"
  }
}
```

**Key methods**:
- `save_state(guid, state_dict)` — upsert by guid
- `load_state(guid) → dict | None` — returns None if no saved state

**Used for**: Determining which resume path to take in `BaseAgent.run()`. If state has `status = BEFORE_TOOL_CALL`, agent re-executes the pending tool calls from `pending_tool_calls`.

---

## PermissionManager (`utils/permission_manager.py`)

**Responsibility**: Gate-keep tool execution behind human approval.

**Storage**: `active_permissions.json` (local file, not MongoDB)

**File shape**:
```json
{
  "tool_permissions": {
    "executeCommand": true,
    "deleteFile": false
  },
  "message_guids": {
    "parent_message_guid": "abc-123",
    "child_message_guid": "def-456"
  },
  "created_at": "2024-01-01T00:00:00Z",
  "last_updated": "2024-01-01T00:01:00Z"
}
```

**Permission states**:
- Key absent / `null` → **Unknown**: Raise `ToolPermissionRequiredException` (pause for human)
- `true` → **Granted**: Execute tool, then consume (remove key)
- `false` → **Denied**: Return denial to LLM without executing

**Key methods**:
- `check_permission(tool_name) → bool | None`
- `grant_permission(tool_name)` — set to `true`
- `deny_permission(tool_name)` — set to `false`
- `consume_permission(tool_name)` — remove entry (one-shot approval)
- `revoke_permission(tool_name)` — same as consume (remove entry)
- `get/set_parent_message_guid()` / `get/set_child_message_guid()` — track agent lineage

**Important**: Permissions are **consumed on use** (one-shot). External interface must re-grant for each invocation. This prevents accidental repeated execution of sensitive tools.

---

## Exception: ToolPermissionRequiredException (`exceptions/tool_permission_exception.py`)

Raised when a tool with `needs_verification=True` is called without a granted permission. Carries:
- `tool_name`: Which tool needs approval
- `tool_args`: Arguments it was called with
- `message_guid`: Current agent's execution ID
- `child_resume_guid`: If this exception came from a child agent, the child's GUID for resumption

This exception propagates all the way up through `FunctionCallingSystem` → `BaseAgent._process_with_tools()` → `BaseAgent.run()` → `agent-worker.py` → (presumably) external interface. The external interface should present the permission request to the user, then resume execution via the appropriate GUID.

---

## MongoDB Connection Pattern

- Connection initialized in `agent-worker.py` main loop
- **Thread-local storage**: Each thread in `ThreadPoolExecutor` creates its own `MongoClient`
- Avoids connection sharing across threads
- Client initialized lazily on first use within each thread
