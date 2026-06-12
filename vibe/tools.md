# Tools / Functions Subsystem

## Architecture

```
FunctionRegistry          — catalog of available tools for an agent
  └─ holds: {name → Function instance}
  └─ generates: JSON schemas for LLM function calling

FunctionCallingSystem     — orchestrates LLM calls with tools
  └─ uses FunctionRegistry to build tool schemas
  └─ calls DeepSeek API
  └─ parses tool_calls from response
  └─ checks PermissionManager before executing
  └─ calls Function.execute() for each tool

Function (abstract base)  — one tool implementation
  └─ defines: name, description, parameters schema
  └─ defines: needs_verification flag
  └─ implements: execute(args) → result string
```

## Function Base Class (`functions/function.py`)

Key interface:
```python
class Function:
    name: str                   # Tool name (used in LLM schema + registry key)
    description: str            # Shown to LLM to explain when to use this tool
    parameters: list[dict]      # JSON Schema parameter definitions
    needs_verification: bool    # If True, requires human approval before execution

    def execute(self, **kwargs) -> str:  # Returns string result to LLM
```

Parameters are dicts with: `name`, `type`, `description`, `required`, optional `default`.

## All Available Tools

| Tool | File | Description | Permission Required |
|------|------|-------------|-------------------|
| `readFile` | `file_read_function.py` | Read file at path | No |
| `editFile` | `file_edit_function.py` | Create/overwrite/append file; atomic write + backup | No |
| `executeCommand` | `command_function.py` | Run shell command via subprocess | No |
| `makeApiCall` | `api_function.py` | HTTP GET/POST with headers/body/auth | No |
| `getDatabaseSchema` | `database_function.py` | Inspect MySQL DB schema | No |
| `sql_query` | `sql_query.py` | Execute SQL (SELECT/INSERT/UPDATE/DELETE) | No |
| `update_sql` | `update_sql.py` | Safe parameterized data modifications | No |
| `get_sql_table_data` | `get_sql_table_data.py` | Get column info + sample rows | No |
| `lookupWebsite` | `website_lookup_function.py` | Fetch + parse web page (SSRF protected) | No |
| `codebaseQuery` | `codebase_query_function.py` | RAG semantic search over code repo | No |
| `delegateToAgent` | `delegate_to_agent_function.py` | Spin up a child agent for subtask | No |
| `calculator` | `calculator_function.py` | Safe math expression evaluation | No |
| `sshConnect` | `ssh_functions.py` | Connect to or disconnect from an SSH server | No |
| `sshExecute` | `ssh_functions.py` | Execute a command on an active SSH session | No |
| (others) | `functions/` | Keyboard, cursor, app control, network | Varies |

## Notable Tool Details

### `sshConnect` / `sshExecute` — SSH Remote Access

Two tools that together provide full remote server access via SSH:

- **`sshConnect`** — Opens (or closes) an SSH connection. Use `action="connect"` with
  `host`, `username`, and either `password` or `key_file_path`. Returns a `session_id`
  (format `"host:port"`) that must be passed to `sshExecute`.
  Use `action="disconnect"` with the `session_id` to close the session.
- **`sshExecute`** — Runs any shell command on the remote server via the active session.
  Use `cat <path>` to read remote files, `ls`/`find` to navigate, `cd && <cmd>` or the
  `working_directory` parameter to change directories. Returns `stdout`, `stderr`, and `exit_code`.

**Connection pooling**: Sessions are stored in a module-level dict keyed by `session_id`.
Reconnecting to the same host:port closes the old connection first. Active sessions
persist across tool calls within the same agent execution.

**Requires**: `pip install paramiko`

**Security note**: Credentials (password, key_file_path) appear in tool call arguments
which are stored in MongoDB conversation history. Use key-based auth for production.

**Typical flow**:
1. `sshConnect(action="connect", host="myserver.com", username="admin", password="...")`
2. `sshExecute(session_id="myserver.com:22", command="ls -la /var/log")`
3. `sshExecute(session_id="myserver.com:22", command="cat /var/log/app.log")`
4. `sshConnect(action="disconnect", session_id="myserver.com:22")`

### `editFile` — Atomic File Editing
- Writes to temp file first, then `os.replace()` (atomic on POSIX, best-effort on Windows)
- Automatic backup before overwrite with configurable retention count
- Auto-detects and pretty-prints JSON files
- Modes: `overwrite` (default), `append`

### `delegateToAgent` — Multi-Agent Delegation
- Maps agent name strings to planning prompts + agent class names
- Creates a child agent with a new `message_guid`
- Stores `parent_message_guid` on child
- If child raises `ToolPermissionRequiredException`, captures `child_resume_guid` for external resumption
- **Critical for multi-step workflows** where parent needs to offload specialized work

### `codebaseQuery` — RAG Code Search
- Delegates to external `Code-Repository-RAG` project
- Requires `CODE_REPOSITORY_RAG_PATH` env var
- Takes: `query` string, optional `repo_path` override
- Returns: Relevant code snippets with file locations

### `lookupWebsite` — SSRF-Protected Web Fetch
- Validates URL does not resolve to private IP ranges (SSRF protection)
- Parses HTML with BeautifulSoup, returns cleaned text
- Blocks: localhost, 10.x, 172.16-31.x, 192.168.x

### `executeCommand` — Shell Execution
- Uses `subprocess.run()` with `shell=True`
- Returns stdout + stderr
- No sandboxing — full system access

## FunctionCallingSystem (`functions/function_calling_system.py`)

Central orchestrator. Called by BaseAgent for each LLM interaction.

**Flow**:
1. Build tool schemas from `FunctionRegistry.get_schemas()`
2. POST to DeepSeek API with `tools` parameter
3. Parse response:
   - `finish_reason == "tool_calls"` → extract tool call list
   - `finish_reason == "stop"` → return content, no tools
4. For each tool call:
   - Check `PermissionManager.check_permission(tool_name)`
   - `None` → raise `ToolPermissionRequiredException`
   - `False` → return denial message
   - `True` → call `registry.execute(name, args)`, then `consume_permission()`
5. Return list of tool results

**Error handling**: Tool execution errors are caught and returned as error strings to the LLM (not raised), so the agent can retry or adapt.

## Tool Catalog (`functions/tool_catalog.py`)

Maps tool name strings (the same `name` used in LLM tool schemas, e.g.
`"readFile"`, `"sql_query"`) to factories that build the corresponding
`Function` instance. Used by `CustomAgent` (and any agent calling
`BaseAgent._build_registry_from_available_tools()`) to assemble a
`FunctionRegistry` from a DB/UI-supplied list of tool names.

- `TOOL_CATALOG: Dict[str, Callable[[BaseAgent], Function]]` — factory receives
  the owning agent so context-dependent tools (e.g. `codebaseQuery`, which
  needs `agent._get_repo_paths()`) can be constructed correctly.
- `build_registry(tool_names, agent) -> FunctionRegistry` — looks up each name,
  logs and skips unknown names, registers the rest.
- `delegateToAgent` is intentionally **not** in the catalog — it requires
  resume GUIDs only known after `BaseAgent.__init__` context is fully set up.

## Adding a New Tool

1. Create `functions/your_tool_function.py`
2. Inherit from `Function`
3. Set `name`, `description`, `parameters`, `needs_verification`
4. Implement `execute(**kwargs) -> str`
5. Import and add to the `FunctionRegistry` in the relevant agent's `__init__`
6. If the tool needs permission gating, set `needs_verification = True`
7. If the tool should be selectable for `CustomAgent`/dynamic registration, add
   an entry to `TOOL_CATALOG` in `functions/tool_catalog.py`
