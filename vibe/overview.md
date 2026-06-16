# AI-Worker System Overview

## Purpose

A **multi-agent AI orchestration worker** that monitors MongoDB for task requests and executes them using specialized AI agents backed by the DeepSeek LLM API. Agents use tool/function calling to interact with databases, files, shells, APIs, and codebases.

## Architecture Summary

```
MongoDB (event source + persistence)
     │  run_signal=True triggers execution
     ▼
agent-worker.py  (main polling loop)
     │  ThreadPoolExecutor (5 workers default)
     ▼
BaseAgent.run()  (stateful execution with resumption)
     │  loop: call LLM → execute tools → call LLM → ...
     ▼
FunctionCallingSystem  (tool orchestration)
     │  PermissionManager gates sensitive tools
     ▼
Tool implementations  (22+ tools)
     │  file I/O, shell, SQL, HTTP, RAG search, delegation
     ▼
DeepSeek API  (LLM backend, model: deepseek-chat)
```

## Major Components

| Component | Location | Role |
|-----------|----------|------|
| Main worker | `agent-worker.py` | MongoDB polling, thread dispatch, compression handling, machine registration |
| BaseAgent | `agents/base_agent.py` | Stateful agent loop, resumption, LLM orchestration |
| Agent types | `agents/*.py` | Specialized agents (DB, files, shell, API, codebase) |
| FunctionCallingSystem | `functions/function_calling_system.py` | Tool execution pipeline, permission checks |
| FunctionRegistry | `functions/function_registry.py` | Tool catalog and schema generation for LLM |
| Tools | `functions/` | 22+ tool implementations |
| MessageService | `services/message_service.py` | Conversation history in MongoDB (includes machine_id/name) |
| MachineService | `services/machine_service.py` | Machine pairing + online/offline registration in MongoDB |
| StateService | `services/state_service.py` | Execution state snapshots for resumption |
| ApiKeyService | `services/api_key_service.py` | Looks up per-user DeepSeek API keys (encrypted at rest) in MongoDB |
| PermissionManager | `utils/permission_manager.py` | Tool-level permission gating via JSON file |
| MachineInfo | `utils/machine_info.py` | Get machine ID (from OS/registry) and hostname |
| Compressors | `conversation_compressor/` | Message history compression strategies |

## Agent Types

| Agent | File | Tools Available |
|-------|------|----------------|
| DatabaseAgent | `agents/database_agent.py` | getDatabaseSchema, sql_query, get_sql_table_data, update_sql |
| FileManagerAgent | `agents/file_manager_agent.py` | readFile, editFile, executeCommand, lookupWebsite, codebaseQuery |
| CommandPromptAgent | `agents/command_prompt_agent.py` | executeCommand, lookupWebsite |
| ApiAgent | `agents/api_agent.py` | makeApiCall |
| CodebaseExpertAgent | `agents/codebase_expert_agent.py` | codebaseQuery (RAG) |

## Key Design Decisions

1. **Event-driven via MongoDB**: `run_signal=True` triggers execution; worker clears it immediately to prevent double-processing.
2. **Stateful resumption**: Full execution state (messages + state snapshot) persisted in MongoDB. Agents can restart from exact interrupt point (before/after tool call, error, pause).
3. **Three-tier GUID system**: `message_guid` (this execution), `parent_message_guid` (who delegated), `child_resume_guid` (resume a child agent). Enables parent-child agent relationships.
4. **Permission gates**: `needs_verification=True` on a tool raises `ToolPermissionRequiredException`, bubbles up to external interface for human approval before resuming.
5. **Tool-first LLM loop**: Every agent iterates: call LLM with tool schemas → parse response → if tool calls, execute them → append results → loop. Terminates when LLM responds with no tool calls.
6. **Thread isolation**: Each thread gets its own MongoDB client to avoid connection sharing issues.

## External Dependencies

- **DeepSeek API**: All LLM inference (`DEEPSEEK_API_KEY`, `DEEPSEEK_API_URL`)
- **MongoDB**: Event bus + persistence (`MONGODB_URI`, `MONGODB_DB_NAME`)
- **MySQL/PostgreSQL/SQLite/MSSQL**: Via DatabaseAgent
- **Code-Repository-RAG**: External project for semantic code search (`CODE_REPOSITORY_RAG_PATH`)
- **HTTP APIs**: Via ApiAgent, SSRF-protected website lookup

## Configuration

All config via `.env` file. Key variables:
```
MONGODB_URI, MONGODB_DB_NAME, MONGODB_COLLECTION_NAME, MONGODB_STATE_COLLECTION
MONGODB_MACHINES_COLLECTION          (default: 'machines')
MONGODB_PAIRING_TOKENS_COLLECTION    (default: 'pairingtokens')
MONGODB_API_KEYS_COLLECTION          (default: 'apikeys')
DEEPSEEK_API_KEY, DEEPSEEK_API_URL    — optional per-machine key, used as a fallback when the user has no platform key (ApiKeyService); reported to the machines collection as has_local_api_key
ENCRYPTION_KEY                        — shared AES-256-GCM secret (base64, 32 bytes); must match mongo-chat-ui's ENCRYPTION_KEY
CODE_REPOSITORY_RAG_PATH, CODEBASE_REPO_PATHS
UI_URL                               (default: 'http://localhost:3000') — used for first-run pairing link
```

See `CONFIGURATION.md` for full reference.
