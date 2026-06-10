# Task: DB-Driven Custom Agent (Dynamic Tool Registration)

## Status: PLANNING — awaiting review

## Goal

Allow an agent to be configured with a list of tool-name strings (sourced from
MongoDB / the UI's agent-builder) and have only those tools registered at
runtime — instead of every agent class hardcoding a fixed tool set in
`_initialize_tools()`.

This unblocks a "Custom Agent" type where a user picks tools from a list in
the UI, and the worker assembles the right `FunctionRegistry` on the fly.

---

## Current State (for reference)

- `BaseAgent.__init__` (`agents/base_agent.py:31`) calls `self._initialize_tools()`,
  an abstract method each subclass implements by manually `registry.register(SomeFunction())`
  for a fixed list of tools (see `DatabaseAgent`, `FileManagerAgent`, etc.).
- `FunctionRegistry` (`functions/function_registry.py`) is just a `dict[name, Function]`
  with `register()`, `get_schemas()`, `execute()`. No factory/lookup-by-string today.
- `agent-worker.py._get_agent_class()` maps `agent_class_name` strings (from the
  MongoDB doc) to agent classes, and `_process_document_thread()` constructs the
  agent with a fixed kwarg list.
- Some tools need extra constructor context beyond zero-args:
  - `CodebaseQueryFunction(repo_paths=[...])`
  - `DelegateToAgentFunction(calling_agent=..., parent_resume_guid=..., child_resume_guid=...)`
  Everything else (`FileReadFunction`, `FileEditFunction`, `CommandFunction`,
  `ApiFunction`, `WebsiteLookupFunction`, `WebsiteLookupRenderedFunction`,
  `SQLQuery`, `UpdateSQL`, `GetSQLTableData`, `DatabaseFunction`,
  `CalculatorFunction`, etc.) are zero-arg constructors.

---

## Proposed Design

### 1. New file: `functions/tool_catalog.py`

A single source of truth mapping **tool name string → factory**. The factory
receives the owning agent instance so tools that need context (repo paths,
calling agent) can pull it from `agent`.

```python
TOOL_CATALOG: Dict[str, Callable[["BaseAgent"], Function]] = {
    "readFile":               lambda agent: FileReadFunction(),
    "editFile":                lambda agent: FileEditFunction(),
    "executeCommand":          lambda agent: CommandFunction(),
    "makeApiCall":             lambda agent: ApiFunction(),
    "lookupWebsite":           lambda agent: WebsiteLookupFunction(),
    "lookupWebsiteRendered":   lambda agent: WebsiteLookupRenderedFunction(),
    "getDatabaseSchema":       lambda agent: DatabaseFunction(),
    "sql_query":               lambda agent: SQLQuery(),
    "update_sql":              lambda agent: UpdateSQL(),
    "get_sql_table_data":      lambda agent: GetSQLTableData(),
    "calculator":              lambda agent: CalculatorFunction(),
    "codebaseQuery":           lambda agent: CodebaseQueryFunction(repo_paths=agent._get_repo_paths()),
    # delegateToAgent intentionally excluded for v1 — see "Open Questions"
}

def build_registry(tool_names: List[str], agent: "BaseAgent") -> FunctionRegistry:
    registry = FunctionRegistry()
    for name in tool_names:
        factory = TOOL_CATALOG.get(name)
        if not factory:
            logging.warning(f"Unknown tool '{name}' in available_tools, skipping")
            continue
        registry.register(factory(agent))
    return registry
```

Tool name strings == the same `name` the LLM already sees in tool schemas
(`readFile`, `sql_query`, etc.) — see "Open Questions" for alternatives.

`agent._get_repo_paths()` already exists on `FileManagerAgent`/`CommandPromptAgent`;
move it to `BaseAgent` so any agent (including `CustomAgent`) can use it.

### 2. `agents/base_agent.py` changes

- `__init__` gains a new optional parameter:
  ```python
  available_tools: Optional[List[str]] = None
  ```
  stored as `self.available_tools = available_tools or []`.
- Add a small helper:
  ```python
  def _build_registry_from_available_tools(self, default: Optional[List[str]] = None) -> FunctionRegistry:
      from functions.tool_catalog import build_registry
      tool_names = self.available_tools or default or []
      return build_registry(tool_names, self)
  ```
- Move `_get_repo_paths()` (currently duplicated in `FileManagerAgent` and
  `CommandPromptAgent`) up to `BaseAgent` so `tool_catalog` and `CustomAgent`
  can call it too.
- **No change** to existing agents' `_initialize_tools()` — they keep their
  hardcoded registries. `available_tools` is simply unused/ignored by them.

### 3. New file: `agents/custom_agent.py`

```python
class CustomAgent(BaseAgent):
    @property
    def messages_dir(self) -> str:
        return "messages/custom_agents"

    @property
    def system_prompt_path(self) -> str:
        return "prompts/custom_agent_prompt.txt"

    def _initialize_tools(self) -> FunctionRegistry:
        return self._build_registry_from_available_tools(default=[])
```

### 4. New file: `prompts/custom_agent_prompt.txt`

Generic system prompt explaining the agent has a dynamic, configurable tool
set (modeled after `prompts/file_manager_prompt.txt` but without
tool-specific assumptions baked in).

### 5. `agent-worker.py` changes

- `_get_agent_class()`: add `'customagent': CustomAgent` to the mapping.
- `_process_run_signal()`: read `available_tools` (array of strings, default `[]`)
  off the MongoDB doc and include it in the `message` dict passed to the thread.
- `_process_document_thread()`: pass `available_tools=message.get('available_tools', [])`
  to the agent constructor. Safe for *all* agent classes since the param is
  optional on `BaseAgent` and ignored by existing `_initialize_tools()` implementations.

### 6. MongoDB doc shape addition (docs only — `vibe/context-map.md`)

```json
{
  "agent_class_name": "CustomAgent",
  "available_tools": ["readFile", "editFile", "executeCommand"]
}
```

---

## Open Questions / Suggestions for Review

1. **Tool name keys** — recommend using the existing LLM-facing tool `name`
   (e.g. `"readFile"`, `"sql_query"`) as the catalog key, since that's already
   stable, user-recognizable, and is what shows up in tool schemas/permissions.
   Alternative would be class names (`"FileReadFunction"`) but that's an
   implementation detail and less DB/UI-friendly.

2. **`delegateToAgent` and `codebaseQuery`** — these need extra constructor
   context (`calling_agent`, `repo_paths`). `codebaseQuery` is handled above
   via `agent._get_repo_paths()`. `delegateToAgent` additionally needs
   `parent_resume_guid`/`child_resume_guid` which are only known inside
   `BaseAgent.__init__` *during* construction — chicken-and-egg with
   `_initialize_tools()` being called from `__init__` before those are fully
   resolved. **Recommendation: exclude `delegateToAgent` from `available_tools`
   for v1** (custom agents can't spawn sub-agents yet); revisit as a follow-up
   if needed.

3. **Default tool set when `available_tools` is empty/missing** — currently
   proposed as `[]` (agent has zero tools, can only respond with text).
   Alternative: fall back to a small safe default (e.g. `["readFile"]`).
   Let me know which you'd prefer.

4. **Should existing agents (Database/File/Api/...) also be allowed to use
   `available_tools` to *extend* their hardcoded set** (e.g. give
   `FileManagerAgent` access to `sql_query` if requested), or is this strictly
   a `CustomAgent`-only mechanism for now? Plan above assumes the latter
   (simplest, no risk of changing existing agent behavior).

5. **Unknown/invalid tool names** — proposed behavior is log-and-skip rather
   than raising, so a bad config doesn't crash agent init entirely. Confirm
   this is desired vs. failing loudly.

---

## Implementation Checklist

- [ ] `functions/tool_catalog.py` — `TOOL_CATALOG` dict + `build_registry()`
- [ ] `agents/base_agent.py` — `available_tools` param, `_build_registry_from_available_tools()`,
      hoist `_get_repo_paths()` from `FileManagerAgent`/`CommandPromptAgent`
- [ ] `agents/custom_agent.py` — new `CustomAgent` class
- [ ] `prompts/custom_agent_prompt.txt` — new generic system prompt
- [ ] `agent-worker.py` — agent class mapping + `available_tools` pass-through
- [ ] Update `vibe/agents.md`, `vibe/tools.md`, `vibe/context-map.md` with the
      new agent type, catalog, and MongoDB field
- [ ] Manual test: MongoDB doc with `agent_class_name: "CustomAgent"` +
      `available_tools: ["readFile", "executeCommand"]`, verify only those
      tools are callable and unknown names are skipped with a warning
