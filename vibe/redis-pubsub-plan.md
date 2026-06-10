# Redis Pub/Sub Migration

## Status: IMPLEMENTED ✓

All components described in this plan are live in the codebase.

---

## What Was Built

### `services/redis_service.py` ✓
- Wraps `redis-py` pub/sub
- Connects via `REDIS_URL` env var (default: `redis://localhost:6379`)
- Subscribes to `REDIS_CHANNEL` (default: `ai-worker:events`)
- `listen()` yields parsed JSON event dicts, blocks until message arrives
- Auto-reconnects on connection drop with 5s delay
- Handles `TimeoutError` silently (no-message read timeout, not a real error)
- `close()` / `_reset()` cleanly tears down pub/sub and client

### `agent-worker.py` — `run()` method ✓
- Primary loop: `for event in redis_service.listen()` — replaces the old 5s MongoDB poll
- `_handle_redis_event()` checks `target_machine_id` — skips events not for this machine
- Dispatches to `_process_run_signal()` or `_process_compress_signal()` based on `event['type']`
- Both methods do a single MongoDB doc lookup by `guid`, clear the flag immediately, then submit to thread pool
- 60-second fallback poll runs as a daemon thread (`_fallback_poll_loop`) — catches events missed while worker was offline

### `.env.example` ✓
```
REDIS_URL=redis://localhost:6379
REDIS_CHANNEL=ai-worker:events
# REDIS_FALLBACK_POLL_INTERVAL=60
```

---

## Event Schema (as published by backend)

```json
{
  "type": "run_signal" | "compress_conversation",
  "guid": "<message_guid>",
  "target_machine_id": "<machine_id or null>"
}
```

---

## Implementation Notes

- `run_signal` is unset via `$unset` (not `$set: false`) — cleaner than leaving a false flag
- `_process_run_signal` double-checks `target_machine_id` in the MongoDB query as well as the event payload — prevents a race where another machine already cleared the signal
- Compression strategy key mapping in worker uses `remove_tool_calls` / `summarize_messages` / `both` (plan doc said `tool_call_remover` etc — actual code keys differ)
- `REDIS_FALLBACK_POLL_INTERVAL` is configurable via env var (default 60s)

---

## What Did Not Change

| Component | Status |
|-----------|--------|
| All agents (`BaseAgent`, subclasses) | Untouched |
| `FunctionCallingSystem`, tools | Untouched |
| `MessageService.check_and_clear_pause_signal()` | Untouched |
| Compression logic | Same dispatch, triggered by event |
| Thread pool, machine pairing, graceful shutdown | Untouched |
| `run_signal` clear-immediately pattern | Preserved |
