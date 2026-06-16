# AI Worker

A multi-agent AI orchestration worker that pairs with [mongo-chat-ui](../mongo-chat-ui) to let users dispatch tasks to AI agents running on any paired machine. The worker listens for tasks via Redis pub/sub, executes them using specialized agents powered by the DeepSeek LLM, and writes results back to MongoDB.

---

## How It Works

The system is split into two separate projects that share a MongoDB database:

```
mongo-chat-ui  (React frontend + Express backend)
     │  Creates conversation docs in MongoDB with run_signal=true
     │  Publishes Redis event: { type: "run_signal", guid, target_machine_id }
     ▼
Redis (pub/sub event bus)
     ▼
agent-worker.py  (this repo — runs on the target machine)
     │  Picks up the Redis event → looks up the MongoDB doc
     │  Dispatches to the right agent in a thread pool
     ▼
Agent (DatabaseAgent / FileManagerAgent / etc.)
     │  Calls DeepSeek LLM in a loop with tool schemas
     │  Executes tool calls (files, shell, SQL, HTTP, SSH, …)
     │  Appends assistant + tool messages back to MongoDB
     ▼
mongo-chat-ui polls MongoDB every 5s → surfaces new messages to the user
```

### Key Concepts

- **MongoDB as the shared state store** — conversations, execution state, machine registry, and pairing tokens all live here. The UI and worker never talk directly to each other.
- **Redis for real-time signalling** — the Express backend publishes an event when a task is ready; the worker subscribes and reacts immediately instead of waiting for a poll interval.
- **60-second fallback poll** — a daemon thread in the worker also scans MongoDB for any `run_signal=true` docs it may have missed while offline.
- **Stateful resumption** — every agent saves its full execution state (messages + step) to MongoDB before and after each tool call. If the worker is interrupted mid-task, the next run picks up exactly where it left off.
- **Permission gating** — tools marked `needs_verification=True` pause execution and wait for human approval via the UI before proceeding.
- **Machine pairing** — on first run, the worker opens a browser to the UI's `/pair/<token>` page. After the user logs in and confirms, the machine is linked to their Firebase account and all their tasks can be routed to it.

---

## Project Structure

```
agent-worker.py                  Main entry point — Redis listener, thread pool, machine registration
agents/
  base_agent.py                  Stateful agent base: LLM loop, resumption logic
  database_agent.py              SQL operations (MySQL / PostgreSQL / SQLite / MSSQL)
  file_manager_agent.py          File read/write/edit, shell commands, codebase search
  command_prompt_agent.py        Shell command execution
  api_agent.py                   HTTP GET/POST calls
  codebase_expert_agent.py       RAG semantic search over a code repository
  custom_agent.py                Dynamic tool set configured per-task from the UI
  summarization_agent.py         Used internally for conversation compression
functions/
  function_calling_system.py     LLM call → parse tool calls → check permissions → execute
  function_registry.py           Tool registry; generates JSON schemas for the LLM
  tool_catalog.py                Name → factory map for dynamic tool registration
  *.py                           22+ individual tool implementations
services/
  message_service.py             Load/save conversation history in MongoDB
  machine_service.py             Machine pairing flow + online/offline registration
  state_service.py               Execution state snapshots for resumption
  api_key_service.py             Per-user encrypted DeepSeek API keys from MongoDB
  redis_service.py               Redis pub/sub listener with auto-reconnect
utils/
  permission_manager.py          active_permissions.json read/write; tool gating
  crypto.py                      AES-256-GCM encrypt/decrypt (must match mongo-chat-ui)
  machine_info.py                Machine ID (registry/OS) + hostname
exceptions/
  tool_permission_exception.py   Raised when a tool needs human approval
conversation_compressor/         Three compression strategies for long conversations
prompts/                         System prompts per agent type (*.txt)
active_permissions.json          Live tool permission state
.env.example                     Template for required environment variables
```

---

## Agents

| Agent | Tools Available | Use Case |
|-------|----------------|----------|
| `FileManagerAgent` | readFile, editFile, executeCommand, lookupWebsite, codebaseQuery | File operations, code editing, general tasks |
| `DatabaseAgent` | getDatabaseSchema, sql_query, get_sql_table_data, update_sql | Schema inspection + SQL across MySQL/Postgres/SQLite/MSSQL |
| `CommandPromptAgent` | executeCommand, lookupWebsite | Shell-heavy tasks, system administration |
| `ApiAgent` | makeApiCall | Calling external REST APIs |
| `CodebaseExpertAgent` | codebaseQuery | RAG-based codebase Q&A via Code-Repository-RAG |
| `CustomAgent` | Dynamic (configured per-task from the UI) | Any tool set chosen at conversation creation time |

---

## Setup

### Prerequisites

- Python 3.9+
- MongoDB (local or Atlas)
- Redis (local or remote)
- A running instance of [mongo-chat-ui](../mongo-chat-ui) for the UI

### 1. Install Python dependencies

```bash
pip install pymongo python-dotenv requests redis paramiko beautifulsoup4
```

> `paramiko` is only required if you use the `sshConnect` / `sshExecute` SSH tools.

### 2. Configure environment

Copy `.env.example` to `.env` and fill in the values:

```env
# MongoDB — must point to the same database as mongo-chat-ui
MONGODB_URI=mongodb://user:password@host:27017
MONGODB_DB_NAME=your_db_name
MONGODB_COLLECTION_NAME=messages
MONGODB_STATE_COLLECTION=states
MONGODB_MACHINES_COLLECTION=machines
MONGODB_PAIRING_TOKENS_COLLECTION=pairingtokens
MONGODB_API_KEYS_COLLECTION=apikeys

# DeepSeek LLM
# Used as a fallback if the user has no platform API key stored in MongoDB
DEEPSEEK_API_KEY=sk-your-key-here
DEEPSEEK_API_URL=https://api.deepseek.com/v1/chat/completions

# Redis — must match the REDIS_URL in mongo-chat-ui's server/.env
REDIS_URL=redis://localhost:6379
REDIS_CHANNEL=ai-worker:events

# Encryption — must be the same 32-byte base64 key as mongo-chat-ui's ENCRYPTION_KEY
# Generate: python -c "import os, base64; print(base64.b64encode(os.urandom(32)).decode())"
ENCRYPTION_KEY=your-base64-32-byte-key

# URL of the UI — used to open the browser for first-time machine pairing
UI_URL=http://localhost:3000
```

### 3. Run the worker

```bash
python agent-worker.py
```

On first run, if the machine has not been paired yet:
1. The worker generates a pairing token and opens `http://localhost:3000/pair/<token>` in your browser.
2. Log in with your Firebase account in the UI.
3. Confirm the pairing — the UI links this machine to your account.
4. The worker detects the pairing and continues startup normally.

On subsequent runs, the worker registers as online and starts listening immediately.

---

## mongo-chat-ui Setup

The UI lives in a separate repository at `../mongo-chat-ui`. It consists of:

- **React frontend** (Vite) — chat interface, conversation management, agent/machine selection
- **Express backend** (`server/index.js`) — REST API, MongoDB operations, Firebase token verification, Redis publisher

### 1. Install dependencies

```bash
# In mongo-chat-ui root (frontend)
npm install

# In mongo-chat-ui/server (backend)
cd server && npm install
```

### 2. Configure environment

Create `.env` in the `mongo-chat-ui` root:

```env
MONGO_URI=mongodb://user:password@host:27017/your_db_name
VITE_SERVER_PORT=5018
VITE_SERVER_IP=localhost
UI_PORT=3000

# Firebase (from your Firebase project console)
VITE_FIREBASE_API_KEY=...
VITE_FIREBASE_AUTH_DOMAIN=...
VITE_FIREBASE_PROJECT_ID=...
VITE_FIREBASE_STORAGE_BUCKET=...
VITE_FIREBASE_MESSAGING_SENDER_ID=...
VITE_FIREBASE_APP_ID=...

# Redis — must match the REDIS_URL/REDIS_CHANNEL in ai-worker's .env
REDIS_URL=redis://localhost:6379
REDIS_CHANNEL=ai-worker:events

# Shared encryption key — must match ai-worker's ENCRYPTION_KEY exactly
ENCRYPTION_KEY=your-base64-32-byte-key
```

### 3. Start the UI

```bash
# Starts both Vite dev server and Express backend concurrently
npm start
```

Or separately:

```bash
npm run dev      # Vite frontend on port 3000
npm run server   # Express backend on port 5018
```

---

## How Conversations Work

1. **User opens the UI** → logs in with Firebase.
2. **User starts a new conversation** → selects an agent type (e.g., File Manager) and optionally a target machine, then sends a message.
3. **UI sends** `POST /api/messages` → Express creates the MongoDB doc with `run_signal: true` and publishes a Redis event.
4. **Worker receives the Redis event** → finds the doc, clears `run_signal`, and submits the task to a thread pool.
5. **Agent runs** → calls DeepSeek in a loop; for each tool call: checks permissions, executes the tool, appends the result, calls DeepSeek again until it produces a final answer.
6. **Results written to MongoDB** → the agent appends every assistant message and tool result to the conversation's `messages` array.
7. **UI polls every 5 seconds** → detects new messages and renders them (markdown for assistant, collapsible blocks for tool calls/results).

### Pause / Resume / Compress

- **Pause** → UI sets `pause_signal: true`; the agent halts between tool calls and saves its state.
- **Resume** → UI sets `run_signal: true` again; the agent resumes from saved state.
- **Compress** → UI sets `compress_conversation: true` with a strategy (`remove_tool_calls`, `summarize_messages`, or `both`); the worker compresses the message history to reduce token usage.

---

## Per-User API Keys

Users can store their own DeepSeek API key via the UI's Settings panel. It is encrypted with AES-256-GCM before being saved to MongoDB. The worker decrypts it at runtime using the shared `ENCRYPTION_KEY`. If a user has no stored key, the worker falls back to the local `DEEPSEEK_API_KEY` env var. If neither is set, the task is rejected with an explanatory message.

---

## Multi-Agent Delegation

Agents can spin up child agents for subtasks using the `delegateToAgent` tool. The parent agent calls it with a target agent type and a subtask description; the child agent runs inline (in the same thread) and returns its result to the parent. If the child needs tool approval, the exception propagates up and the external interface must resume the child separately using the `child_resume_guid`.

---

## SSH Tools

The `sshConnect` and `sshExecute` tools (available in `FileManagerAgent`) allow agents to connect to remote servers over SSH and run commands. Requires `paramiko`:

```bash
pip install paramiko
```

Sessions persist across tool calls within a single agent execution and are keyed by `host:port`.

---

## Codebase Search (RAG)

`CodebaseExpertAgent` delegates to an external [Code-Repository-RAG](https://github.com/your-org/code-repository-rag) service for semantic code search. Configure via:

```env
CODE_REPOSITORY_RAG_PATH=/path/to/code-repository-rag
CODEBASE_REPO_PATHS=/path/to/repo1,/path/to/repo2
```
