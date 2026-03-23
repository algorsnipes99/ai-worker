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
  "target_machine_id": "<machine_id to route this task to, or null for any>"
}
```

`machine_id` and `machine_name` are written by `save_messages()` on every call, reflecting the machine that last processed the conversation. `target_machine_id` is set at conversation creation by the UI and used by `agent-worker.py` to filter task pickup.

**Key methods**:
- `save_messages(guid, messages)` — upsert by guid
- `load_messages(guid)` — load with fallback search (exact → with parent GUID → regex)
- `update_status(guid, status)` — set active/complete/paused
- `check_and_clear_pause_signal(guid) → bool` — atomically read + clear pause flag

**Fallback loading strategy**: If exact GUID match fails, tries finding doc where the GUID appears within stored message content (for child agent resumption). This handles cases where child agent GUID is embedded in parent messages.

---

## MachineService (`services/machine_service.py`)

**Responsibility**: Register this machine as online when the worker starts and offline when it shuts down.

**MongoDB collection**: `MONGODB_MACHINES_COLLECTION` env var (default: `machines`)

**Document shape**:
```json
{
  "machine_id": "<OS/registry machine GUID>",
  "machine_name": "<hostname>",
  "user_guid": "m8JLGcC0mxMWHWQ1QbO2NJ3xlgz2",
  "status": "online | offline",
  "last_seen": "2024-01-01T00:01:00"
}
```

`machine_id` is unique. Documents are upserted — one record per physical machine.

**Key methods**:
- `register()` — upsert with `status='online'`, update `last_seen`
- `deregister()` — set `status='offline'`, update `last_seen`

**When called**:
- `register()` is called in `AgentWorker.__init__()` immediately after the machine ID is resolved
- `deregister()` is called in `AgentWorker.handle_shutdown()` after the thread pool drains

**Note**: `user_guid` is currently hardcoded to `m8JLGcC0mxMWHWQ1QbO2NJ3xlgz2`. To support multi-user deployments, move this to an env var.

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
