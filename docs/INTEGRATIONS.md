# Integration setup and contracts

The current module handles existing-tenant enquiries and complaints. Move-in/out arrangements, inspection checklists and random PIC assignment are outside scope. No notification adapter may send a legacy move notice.

## Native Hermes and model

Install native Hermes separately and ensure `hermes` is on PATH. The adapter resolves the Python interpreter beside that executable and runs the project's worker there. Configure `BELIVE_AI_PROVIDER` as `openai` or `ollama`, `BELIVE_AI_MODEL`, and the matching key/URL settings in this project's `.env`. Restart after changes. The current OpenAI option uses `https://api.openai.com/v1`; Ollama uses its configured base URL plus `/v1`.

The worker instantiates native `AIAgent` with a five-step bound per stage and exactly `read_case_context` and `read_reviewed_styles`. Context files, default memory and saved trajectories are disabled. Credentials go through stdin, not command arguments. Failed calls and schema/evidence validation failures route the case to staff. No provider call has been claimed successful without a real result; local tests substitute an explicit test double.

Before each stage the isolated MemoryStore is rebuilt from current feedback (at most five shortened native entries). The read-only style tool provides the current reviewed examples. The store is not the global Hermes memory. An empty projection removes previous examples; persistence/revocation has been exercised using the installed runtime without invoking an LLM.

## Public-source reads

Configure only resources BeLive is authorised to access and set the appropriate tokens in `.env`. The source form states that saving starts checks every 15 minutes while the app is open. Pause/resume applies to that source and persists across restarts; it does not control whether the backend is running. No login, challenge handling, broad web crawl or arbitrary URL follow is implemented. HTTP redirects are rejected. Each response is limited to 1 MB and 20 seconds; each scan processes at most 25 recent text entries. There is no pagination, token refresh or historical backfill.

- Google: resource `accounts/ACCOUNT_ID/locations/LOCATION_ID`, token `BELIVE_GOOGLE_TOKEN`. Uses the official Business Profile [reviews.list](https://developers.google.com/my-business/reference/rest/v4/accounts.locations.reviews/list) endpoint, ordered by update time.
- Facebook: `PAGE_ID/feed` or `POST_ID/comments`, token `BELIVE_FACEBOOK_TOKEN`, explicit `BELIVE_FACEBOOK_VERSION` such as the version approved for your application. Uses Graph fields `id,message,created_time`. [Official Page posts documentation](https://developers.facebook.com/docs/pages-api/posts/).
- Threads: `POST_ID/replies`, token `BELIVE_THREADS_TOKEN`, fields `id,text,timestamp`. This is selected post replies, not marketing lead search or broad keyword discovery. Validate current supported access against the [official Threads documentation](https://developers.facebook.com/docs/threads/) before a live pilot.

Meta documentation access was rate-limited during research; these adapters are implementation candidates, not claimed live-verified company integrations. Tokens, permissions, ownership, platform version and permitted collection scope must be checked using the actual company application. Missing configuration is reported; no fixture data is substituted.

A public item gets an immutable redacted source version. Repeated identical versions are reused; changed text produces a new version/intake for review. Different public IDs remain distinct even when wording matches. Stable identifiers are not phone-number masked.

## Notification gateway

Set `BELIVE_NOTIFICATION_URL` to a trusted HTTPS company endpoint and `BELIVE_NOTIFICATION_SECRET` to a private shared secret. The application never resolves external recipient addresses itself: `target` is a verified tenant reference or internal department/role. The gateway must map that reference using its authorised records, enforce channel permissions and handle provider receipts.

The operator approves the exact saved message and explicitly selects Deliver. The POST body is UTF-8 JSON with these fields:

```json
{"id":"MSG-EXAMPLE","entity":"BL-EXAMPLE","kind":"TENANT_RESPONSE","text":"Reviewed response text","target":"TENANT-REF"}
```

Headers:

- `Content-Type: application/json`
- `Idempotency-Key`: message `id`
- `X-BeLive-Signature`: hex HMAC-SHA256 of the exact request body bytes using the configured secret

The gateway must verify the signature, persist idempotency and avoid sending the same message twice. Return a confirmed outcome only when delivery is actually established:

```json
{"idempotency_key":"MSG-EXAMPLE","status":"delivered","receipt_id":"provider-confirmed-receipt"}
```

Queue acceptance alone must not be described as delivered. A timeout, invalid receipt, transport failure or interrupted send becomes `UNKNOWN`; the application does not automatically retry or expose a retry action. Staff must reconcile an unknown result with gateway records before taking further action. No live provider or gateway messages were sent during testing.

## Shared memory

`BELIVE_MEMORY_CLIENTS` is a JSON object mapping approved client labels to separate secret bearer tokens. With such a token, `GET /api/shared-memory` returns only explicitly shared, currently approved/corrected style examples from closed cases. It returns no case/tenant object and does not grant write access. Rejection/reopening removes the example from subsequent retrieval. Review text for identifying details before enabling sharing; email/number masking is incomplete anonymisation.

## Local tenant portal

Staff issues a seven-day bearer key after verification. Only its hash is stored in the portal table; the raw key is returned once and is excluded from the idempotency cache. Do not place keys in URLs. Keys permit viewing that tenant's public conversations and limited case fields, replying and reporting outcomes; they cannot access the operator snapshot.

This is a local demonstration of scoped access, not deployable identity infrastructure. The operator dashboard now requires Admin/Support login; data/configuration operations enforce roles on the server. Tenant keys are independently scoped and revocable. Production use still needs a deployment/identity design, TLS, protection against abuse and an agreed data lifecycle. A public GitHub repository does not host the running backend or tenant portal.

## Database location and visible records

Open **Database & records** to search stored property, tenant and support-context tables and inspect the active file path. Operational records are persisted in SQLite. The local file picker selects a file for the next launch; it does not relocate the active database or migrate its contents. Reopen an existing BeLive database to see its records, or choose a new filename to start empty after restarting. Validation reads existing database schema without modifying it and rejects unrelated databases.

The default file is `data/belive.db`. The ignored `data/workspace.json` preference contains only the selected path. No tenant records are stored there or in browser localStorage. `python server.py --database ABSOLUTE_PATH` can explicitly override selection for a launch. Python's Tk support is needed for the native picker; normal database use and record browsing do not depend on Tk.

The Windows launcher opens a dedicated Python console and exits its batch process immediately. Leave the Python window running for the dashboard and scheduled checks; one Ctrl+C stops it. An already-running older launcher must be stopped before using the revised one.

## Reviewed portal responses

The local portal is an implemented communication channel. Operators review/save wording and explicitly publish it to the verified tenant's conversation. No external credentials are needed for that local operation. Gateway queue approval/delivery remains separate; portal publication is not reported as external delivery. Tenant resolved feedback is an assertion for staff review. Unresolved feedback can reopen a closed case; safety flags always route to staff.

## Operator access

Create an admin in first-run setup, then create Support accounts in settings. Credentials belong to the selected database. There is no default account or hard-coded password. The session cookie is HttpOnly/SameSite=Strict for this loopback HTTP app. Admin operations include users, source and context changes, AI checks, portal-key management, backup/recovery and database selection. Support operations include case handling, internal notes, reviewed responses and external notification review. Role checks are enforced independently of the visible UI.

## Real AI check and evaluation

The admin **Test AI connection** action sends a neutral request to the configured provider through native Hermes and records the validated outcome and timestamp. It sends no tenant data but may incur model charges. The separate 24-case evaluation is opt-in with `python scripts/evaluate_ai.py --run-live`; without that flag the script only describes the fictional test set. See the README for setup and interpretation. A [limited live Hermes/Ollama Cloud smoke test](LIVE_AI_SMOKE_TEST.md) passed on 26 October 2026 with fictional records. The full 24-case evaluation has not been run, and no overall accuracy score is claimed.

## Backup recovery

Admin backup uses SQLite's online backup API and stores a verified checksum beside the database. Recovery creates a separate copy rather than replacing the live file. In that copy, source checks pause, outstanding messages enter `RECOVERY_HOLD`, sessions and tenant keys are revoked and guidance is excluded until reviewed again. This protects against replay and against reviving examples that may have been rejected after the snapshot. Keep backup files private: they contain tenant records and account hashes. A restored database uses the user accounts that existed when that backup was taken.
