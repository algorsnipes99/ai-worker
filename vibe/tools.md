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
| (others) | `functions/` | Keyboard, cursor, app control, network | Varies |

## Notable Tool Details

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

## Adding a New Tool

1. Create `functions/your_tool_function.py`
2. Inherit from `Function`
3. Set `name`, `description`, `parameters`, `needs_verification`
4. Implement `execute(**kwargs) -> str`
5. Import and add to the `FunctionRegistry` in the relevant agent's `__init__`
6. If the tool needs permission gating, set `needs_verification = True`
