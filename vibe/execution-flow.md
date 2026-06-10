# Execution Flow & Data Movement

## End-to-End Flow

```
1. External system inserts MongoDB doc:
   {run_signal: true, user_request: "...", agent_class_name: "FileManagerAgent"}

2. agent-worker.py polls every 5 seconds
   → finds doc
   → IMMEDIATELY clears run_signal (prevents double-trigger)
   → resolves agent class from string name
   → submits to ThreadPoolExecutor

3. Thread runs agent:
   AgentClass(message_guid, user_request, plan, parent_message_guid).run()

4. BaseAgent.run():
   a. Load existing state from StateService (may be None for first run)
   b. Load existing messages from MessageService (may be empty)
   c. Based on state.status, call appropriate resume/init method

5. _initialize_and_run() (first run):
   → build initial messages: [system_prompt, user_request]
   → call _process_with_tools(messages)

6. _process_with_tools() loop:
   a. Check pause_signal via MessageService.check_and_clear_pause_signal()
      → if True: save state, set status=paused, return
   b. Call FunctionCallingSystem.call_api_with_tools(messages, registry)
   c. If response has tool_calls:
      → append assistant message with tool_calls to messages
      → save state with status=BEFORE_TOOL_CALL + pending_tool_calls
      → save messages to MessageService
      → for each tool call:
           check PermissionManager
           execute tool
           collect result
      → save state with status=AFTER_TOOL_CALL
      → append tool result messages
      → save messages again
      → continue loop (go back to step a)
   d. If response has no tool_calls (final answer):
      → append final assistant message
      → save messages
      → update status to "complete" in MessageService
      → save state with status=COMPLETED
      → return response content

7. agent-worker.py receives return value (or exception)
   → if ToolPermissionRequiredException: propagate up to external interface
   → if other exception: log error, state already saved as ERROR
```

---

## Message Array Structure Over Time

The `messages` list grows with each LLM turn:

```python
# Initial state
[
  {"role": "system", "content": "<agent system prompt>"},
  {"role": "user",   "content": "<user request>"}
]

# After first LLM call (with tool use)
[
  {"role": "system",    "content": "..."},
  {"role": "user",      "content": "..."},
  {"role": "assistant", "content": null, "tool_calls": [
    {"id": "call_abc", "function": {"name": "readFile", "arguments": '{"path": "/foo.txt"}'}}
  ]}
]

# After tool execution
[
  ... (above),
  {"role": "tool", "tool_call_id": "call_abc", "content": "<file contents>"}
]

# After second LLM call (final answer)
[
  ... (above),
  {"role": "assistant", "content": "Here is what I found: ..."}
]
```

This full array is saved to MongoDB after each state transition.

---

## Compression Flow

Separate from normal execution. Triggered by:
```json
{"compress_conversation": true, "compression_strategy": "tool_call_remover | message_summarizer | combined"}
```

```
agent-worker.py detects compress_conversation=True
→ clears flag
→ reads messages from MongoDB
→ selects compressor based on strategy
→ runs compressor (may call DeepSeek for summarization)
→ saves compressed messages back to MongoDB
```

Compressors in `conversation_compressor/`:
- **ToolCallRemover**: Removes all `role=tool` and messages containing `tool_calls`
- **MessageSummarizer**: LLM-summarizes first N messages, keeps last M intact
- **CombinedCompressor**: ToolCallRemover first, then MessageSummarizer

---

## Permission Exception Flow

When a tool needs approval:

```
FunctionCallingSystem.execute_tool()
  → PermissionManager.check_permission("sensitiveTool") → None
  → raise ToolPermissionRequiredException(
        tool_name="sensitiveTools",
        tool_args={...},
        message_guid="abc-123"
    )

BaseAgent._process_with_tools()
  → state saved with BEFORE_TOOL_CALL status
  → exception re-raised

agent-worker.py
  → exception propagates to caller

External interface receives exception:
  → shows user: "Agent wants to run 'sensitiveTools' with args {...}. Allow?"
  → user approves → PermissionManager.grant_permission("sensitiveTools")
  → external interface calls agent again with same message_guid
  → agent resumes from BEFORE_TOOL_CALL state
  → tool executes, permission consumed
```

---

## Pause/Resume Flow

```
External interface sets pause_signal=True in MongoDB doc

Next iteration of _process_with_tools():
  → MessageService.check_and_clear_pause_signal(guid) returns True
  → state saved with "paused" status
  → agent returns early

Later, external interface sets run_signal=True again
  → agent-worker picks it up
  → agent resumes from saved state
```

---

## Child Agent Flow (Delegation)

```
Parent agent's LLM decides to call delegateToAgent("FileManagerAgent", "Read and summarize logs")

delegateToAgent.execute():
  → generates new child_message_guid
  → creates FileManagerAgent(child_message_guid, subtask, parent_guid=parent_message_guid)
  → calls child_agent.run()

  If child completes normally:
    → returns child's final response to parent's tool result
    → parent continues with that result

  If child raises ToolPermissionRequiredException:
    → delegateToAgent catches it
    → wraps it with child_resume_guid
    → re-raises to parent
    → parent agent stops
    → external interface must resume the child_resume_guid separately
```

---

## Machine Registration & Pairing Flow

On worker startup (`AgentWorker.__init__`):
```
get_machine_id()   → reads Windows registry (HKLM\SOFTWARE\Microsoft\Cryptography\MachineGuid)
                     or /etc/machine-id on Linux
get_machine_name() → socket.gethostname()

MachineService.is_paired()?
  YES → skip pairing, continue to register()
  NO  →
    token = secrets.token_urlsafe(32)
    MachineService.create_pairing_token(token)
      → upsert pairingtokens: { token, machine_id, machine_name, status:'pending', expires_at: now+10min }
    webbrowser.open("UI_URL/pair/<token>")
    MachineService.wait_for_pairing(timeout=600s)
      → polls machines collection every 5s for user_guid to appear
      → returns True when paired, False on timeout
    if timeout → sys.exit(1)

MachineService.register()
  → upsert machines collection: { machine_id, machine_name, status:'online', last_seen }
  (does NOT overwrite user_guid)
```

On worker shutdown (`AgentWorker.handle_shutdown`):
```
thread pool drains (wait=True)
MachineService.deregister()
  → update machines collection: { status:'offline', last_seen }
```

**UI pairing side** (handled in `mongo-chat-ui`):
```
Browser opens UI_URL/pair/<token>
  → App.jsx detects /pair/ prefix → renders <PairDevice token={...}>
  → PairDevice fetches GET /api/pair/:token (validates token, gets machine_name)
  → if not logged in → shows Login form
  → on login: AuthContext.currentUser becomes non-null
  → useEffect detects currentUser + status=NEEDS_LOGIN
  → calls POST /api/pair { token } with Authorization: Bearer <Firebase ID token>
  → backend verifies token via Firebase REST API → gets uid
  → backend writes user_guid=uid on machines document
  → backend marks pairing token status='completed'
  → PairDevice shows success screen ("Device paired!")
  → worker's wait_for_pairing() detects user_guid, returns True
  → worker continues normal startup
```

---

## Data Storage Summary

| Data | Where | Key |
|------|-------|-----|
| Conversation messages | MongoDB `messages` collection | `guid` |
| Machine online/offline status | MongoDB `machines` collection | `machine_id` |
| Pairing tokens | MongoDB `pairingtokens` collection | `token` |
| Execution state | MongoDB `states` collection | `guid` |
| Tool permissions | `active_permissions.json` | tool name |
| Agent lineage (parent/child GUIDs) | `active_permissions.json` | fixed keys |
| System prompts | `prompts/*.txt` | file per agent |
| LLM inference | DeepSeek API (stateless) | — |
