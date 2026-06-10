# Agents Subsystem

## BaseAgent (`agents/base_agent.py`)

The core abstraction. All agents inherit from this. It owns:
- The LLM loop (`_process_with_tools`)
- Message history management (via MessageService)
- Execution state tracking (via StateService)
- Resumption logic
- Pause signal checking

### Lifecycle

```
Agent.__init__(message_guid, user_request, plan, parent_message_guid)
  ↓
Agent.run()
  ├─ load existing state (StateService)
  ├─ load existing messages (MessageService)
  ├─ dispatch to resume handler based on state.status:
  │    INIT / None      → _initialize_and_run()
  │    BEFORE_TOOL_CALL → _resume_before_tool_call()
  │    AFTER_TOOL_CALL  → _resume_after_tool_call()
  │    COMPLETED        → _resume_completed()
  │    ERROR            → _resume_error()
  └─ returns final response string

_process_with_tools(messages)
  loop:
    check pause_signal (MessageService.check_and_clear_pause_signal)
    call DeepSeek (FunctionCallingSystem.call_api_with_tools)
    parse response:
      if tool_calls → save state BEFORE_TOOL_CALL, execute tools, save state AFTER_TOOL_CALL, append results, continue loop
      else → COMPLETED, save messages, update status
```

### Abstract Properties (must implement in subclass)

```python
@property
def system_prompt(self) -> str       # Agent's system-level instructions
@property
def tools(self) -> FunctionRegistry  # Which tools this agent has access to
```

### State Constants

```python
STATE_INIT = "INIT"
STATE_BEFORE_TOOL_CALL = "BEFORE_TOOL_CALL"
STATE_AFTER_TOOL_CALL = "AFTER_TOOL_CALL"
STATE_COMPLETED = "COMPLETED"
STATE_ERROR = "ERROR"
```

### Resumption Details

When an agent is interrupted mid-execution (permission exception, error, pause), state is saved to MongoDB with the current `status`. On next `run()` call with same `message_guid`, the agent resumes from the saved state:

- **BEFORE_TOOL_CALL**: The tool calls were queued but not yet executed. Re-executes them.
- **AFTER_TOOL_CALL**: Tools ran, results stored, but LLM continuation not done yet. Appends results and continues.
- **COMPLETED**: Previous turn done. Treats new `user_request` as a follow-up message.

---

## Agent Implementations

### DatabaseAgent

- **File**: `agents/database_agent.py`
- **System prompt**: `prompts/database_agent_prompt.txt`
- **Tools**: `getDatabaseSchema`, `sql_query`, `get_sql_table_data`, `update_sql`
- **Use case**: Schema inspection, querying, data modification across SQL databases
- **DB support**: MySQL, PostgreSQL, SQLite, MSSQL (via connection strings in tool args)

### FileManagerAgent

- **File**: `agents/file_manager_agent.py`
- **System prompt**: `prompts/file_manager_prompt.txt`
- **Tools**: `readFile`, `editFile`, `executeCommand`, `lookupWebsite`, `codebaseQuery`
- **Use case**: General-purpose file operations, code editing, folder exploration
- **Notable**: Broadest tool set; often the default choice for general tasks

### CommandPromptAgent

- **File**: `agents/command_prompt_agent.py`
- **System prompt**: `prompts/command_prompt_prompt.txt`
- **Tools**: `executeCommand`, `lookupWebsite`
- **Use case**: Shell-heavy tasks, system administration, running scripts

### ApiAgent

- **File**: `agents/api_agent.py`
- **System prompt**: `prompts/api_agent_prompt.txt`
- **Tools**: `makeApiCall`
- **Use case**: Calling external REST APIs, webhooks, data fetching

### CodebaseExpertAgent

- **File**: `agents/codebase_expert_agent.py`
- **System prompt**: `prompts/codebase_expert_prompt.txt`
- **Tools**: `codebaseQuery`
- **Use case**: Answering questions about a codebase using semantic RAG search
- **Config**: Default repo paths hardcoded to `C:\dev\mqx\*`; override via `CODEBASE_REPO_PATHS` env var

### CustomAgent

- **File**: `agents/custom_agent.py`
- **System prompt**: `prompts/custom_agent_prompt.txt`
- **Tools**: Dynamic — built from `available_tools` (list of tool name strings) passed
  into `BaseAgent.__init__`, resolved via `functions/tool_catalog.py`. Falls back to
  `["executeCommand"]` if `available_tools` is empty.
- **Use case**: DB-driven / UI-configured agents where the tool set is chosen per-task
  rather than hardcoded in a subclass
- **Notable**: Unknown tool names in `available_tools` are logged and skipped.
  `delegateToAgent` is not available to custom agents (requires resume GUIDs not
  available at `_initialize_tools()` time).

### SummarizationAgent

- **File**: `agents/summarization_agent.py`
- **NOT a task agent** — used internally by compression system only
- Summarizes the first N messages in a conversation to reduce token usage

---

## Dynamic Tool Registration (`available_tools`)

`BaseAgent.__init__` accepts an optional `available_tools: List[str]` param,
stored as `self.available_tools`. Any agent can call
`self._build_registry_from_available_tools(default=[...])` from its
`_initialize_tools()` to build a `FunctionRegistry` from those tool name
strings via `functions/tool_catalog.TOOL_CATALOG` (keyed by the LLM-facing
tool name, e.g. `"readFile"`, `"sql_query"`). Unknown names are logged and
skipped. `CustomAgent` is the only agent currently using this; existing
agents keep their hardcoded `_initialize_tools()`.

## Adding a New Agent

1. Create `agents/your_agent.py` inheriting from `BaseAgent`
2. Implement `system_prompt` property (point to a `prompts/` file)
3. Implement `tools` property returning a `FunctionRegistry` with desired tools
4. Add to `agent-worker.py`'s agent class name → class mapping
5. Add to `delegate_to_agent_function.py` if it should be delegatable
6. Create `prompts/your_agent_prompt.txt`

---

## Parent-Child Agent Relationships

An agent can delegate subtasks to child agents via `delegateToAgent` tool. The child:
- Gets its own `message_guid`
- Stores `parent_message_guid` pointing back to parent
- Runs independently, possibly across multiple resume cycles

The parent captures `child_resume_guid` from `ToolPermissionRequiredException` to allow resuming the child later. The external interface must understand this GUID for resumption.
