# Device Pairing Plan

## Problem

`MachineService.register()` uses a hardcoded `user_guid`. We need machines to be
securely linked to the authenticated Firebase user through a browser-based pairing
flow, without the worker touching browser state or credentials.

---

## High-Level Flow

```
Worker starts
  │
  ├─ Check MongoDB: does this machine_id already have a user_guid?
  │    YES → continue normally (skip pairing)
  │    NO  → begin pairing flow
  │
  ├─ Generate secure token, write to new `pairing_tokens` collection
  │
  ├─ Open browser: http://<UI_HOST>/pair/<token>
  │
  ├─ Poll MongoDB every 5s until machine record has user_guid set
  │
  └─ Once paired → continue normal worker startup

Browser (UI)
  │
  ├─ Detect /pair/:token path in App.jsx (no router needed — parse window.location)
  │
  ├─ If not logged in → show Login component, redirect back after auth
  │
  ├─ Show pairing confirmation screen with machine name
  │
  └─ On confirm → POST /api/pair with { token } + Firebase ID token in Authorization header

Backend (server/index.js)
  │
  ├─ POST /api/pair
  │    ├─ Extract Bearer token from Authorization header
  │    ├─ Verify with Firebase Admin SDK → get uid
  │    ├─ Look up pairing token in MongoDB → validate pending + not expired
  │    ├─ Update machine record: set user_guid = uid, status = 'online'
  │    ├─ Mark pairing token as completed
  │    └─ Return { success: true, machine_name }
  │
  └─ GET /api/pair/:token
       └─ Return token doc (machine_name, status) for the UI to display
```

---

## What "Already Paired" Means

A machine is **paired** if its document in the `machines` collection has a non-null
`user_guid`. On first startup (no document) or if `user_guid` is absent/null → needs
pairing.

The existing hardcoded GUID will be treated as unpaired going forward — the worker
will check for a real user-linked record, not the sentinel string.

---

## Changes — File by File

### 1. `ai-worker` — `services/machine_service.py`

- Remove `HARDCODED_USER_GUID`
- Add `is_paired() -> bool`: query `machines` by `machine_id`, return True if doc exists
  and `user_guid` is a non-empty string
- Add `create_pairing_token(token: str) -> None`: upsert into new `pairing_tokens`
  collection with `{ token, machine_id, machine_name, status: 'pending', created_at,
  expires_at: now+10min }`
- Add `wait_for_pairing(timeout_seconds=600) -> bool`: poll `machines` every 5s until
  `user_guid` appears (or timeout)
- Update `register()`: no longer writes `user_guid` (that's now set by the UI backend).
  Only writes `machine_id`, `machine_name`, `status`, `last_seen`

### 2. `ai-worker` — `agent-worker.py`

In `__init__`, before calling `self.machine_service.register()`:

```
if not self.machine_service.is_paired():
    token = secrets.token_urlsafe(32)
    self.machine_service.create_pairing_token(token)
    ui_url = os.getenv('UI_URL', 'http://localhost:3000')
    webbrowser.open(f"{ui_url}/pair/{token}")
    self.logger.info(f"Waiting for pairing at {ui_url}/pair/{token}")
    paired = self.machine_service.wait_for_pairing()
    if not paired:
        self.logger.error("Pairing timed out. Exiting.")
        sys.exit(1)

self.machine_service.register()  # now just sets status=online + last_seen
```

Add `UI_URL` to `.env`.

### 3. `mongo-chat-ui` — `server/models/PairingToken.js` (NEW FILE)

```js
{
  token:        String (required, unique)   // the secure random token
  machine_id:   String (required)
  machine_name: String
  status:       String enum ['pending', 'completed', 'expired']  default 'pending'
  created_at:   Date
  expires_at:   Date
}
```

### 4. `mongo-chat-ui` — `server/models/Machine.js`

- Make `user_guid` optional (remove `required: true`) so machine can exist pre-pairing

### 5. `mongo-chat-ui` — `server/index.js`

**New dependency:** `firebase-admin` npm package

**Initialization** (top of file):
```js
const admin = require('firebase-admin');
admin.initializeApp({
  credential: admin.credential.cert(process.env.FIREBASE_SERVICE_ACCOUNT_PATH)
});
```

**New endpoint — `GET /api/pair/:token`:**
- Find pairing token doc in DB
- If not found → 404
- If expired → update status='expired', return 410
- Return `{ token, machine_id, machine_name, status }`

**New endpoint — `POST /api/pair`:**
- Extract `Authorization: Bearer <id_token>` from headers
- `admin.auth().verifyIdToken(idToken)` → get `uid`
- Extract `{ token }` from body
- Find pairing token: must exist, status=pending, expires_at > now
- If invalid → 400/410
- `Machine.findOneAndUpdate({ machine_id }, { $set: { user_guid: uid } }, { upsert: true })`
- `PairingToken.updateOne({ token }, { $set: { status: 'completed' } })`
- Return `{ success: true, machine_name }`

**New env var:** `FIREBASE_SERVICE_ACCOUNT_PATH` — path to Firebase service account JSON file

### 6. `mongo-chat-ui` — `src/App.jsx`

At the top of `App`, detect if the current URL is a pairing URL:

```js
const pairingToken = window.location.pathname.startsWith('/pair/')
  ? window.location.pathname.split('/pair/')[1]
  : null;
```

In the render:
```jsx
if (pairingToken) {
  return <PairDevice token={pairingToken} />;
}
```

This sits above the normal chat UI render — no routing library needed.

### 7. `mongo-chat-ui` — `src/components/PairDevice.jsx` (NEW FILE)

A self-contained component that handles the full pairing flow:

**States:**
- `loading` — fetching token info from `GET /api/pair/:token`
- `not_found` / `expired` — error states
- `needs_login` — user is not authenticated → render `<Login />` with a callback to
  return to this component after login
- `ready` — show machine name + "Pair this device" confirm button
- `pairing` — awaiting `POST /api/pair` response
- `success` — show success message ("Device paired! You can close this tab.")
- `error` — server error

**Flow:**
1. On mount: `GET /api/pair/:token` → get machine info; if not found/expired, show error
2. Check `currentUser` from `useAuth()`:
   - null → render `<Login onSuccess={() => setNeedsLogin(false)} />` (Login already exists)
   - set → proceed to confirm screen
3. On "Pair" button click:
   - `const idToken = await currentUser.getIdToken()`
   - `POST /api/pair { token }` with `Authorization: Bearer <idToken>`
   - Show success or error

**Note on Login redirect:** The existing `Login.jsx` currently has no callback prop.
We'll need to add an `onSuccess` prop to it so `PairDevice` can react after login
without a page reload. This is a small, isolated change.

---

## New Env Vars

| Location | Var | Example |
|----------|-----|---------|
| `ai-worker/.env` | `UI_URL` | `http://localhost:3000` |
| `mongo-chat-ui/.env` | `FIREBASE_SERVICE_ACCOUNT_PATH` | `./service-account.json` |

---

## MongoDB Collections Summary

| Collection | Change |
|-----------|--------|
| `machines` | `user_guid` becomes optional (no longer required at insert) |
| `pairing_tokens` | **NEW** — short-lived pairing token records |

---

## What Does NOT Change

- The normal agent polling loop in `agent-worker.py` — pairing only runs at startup
- `deregister()` — unchanged
- All existing API endpoints — no modifications
- Firebase Auth on the frontend — reused as-is
- The 5-second polling architecture — worker reuses same MongoDB polling pattern

---

## Security Properties

- Token is `secrets.token_urlsafe(32)` (256 bits of entropy)
- Token is single-use (marked `completed` on first successful pair)
- Token expires in 10 minutes (`expires_at` checked server-side)
- User identity verified server-side via Firebase Admin SDK (`verifyIdToken`)
- The frontend never directly writes `user_guid` to the DB — only the backend does,
  after verifying the Firebase ID token
- Worker never reads cookies, localStorage, or browser auth state

---

## Implementation Order

1. `server/models/PairingToken.js` — new model
2. `server/models/Machine.js` — make `user_guid` optional
3. `server/index.js` — Firebase Admin init + 2 new endpoints
4. `src/components/PairDevice.jsx` — new component
5. `src/components/Login.jsx` — add optional `onSuccess` prop
6. `src/App.jsx` — detect `/pair/` path, render `<PairDevice>`
7. `services/machine_service.py` — refactor (remove hardcoded guid, add pairing methods)
8. `agent-worker.py` — pairing flow in `__init__`
9. Update `.env` files with new vars
10. Update vibe docs
