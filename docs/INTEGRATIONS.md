# Integration setup and contracts

## Native Hermes and model

Install native Hermes separately and ensure `hermes` is on PATH. The adapter resolves the Python interpreter beside that executable and runs the project's worker there. Configure `BELIVE_AI_PROVIDER` as `openai` or `ollama`, `BELIVE_AI_MODEL`, and the matching key/URL settings in this project's `.env`. Restart after changes. The current OpenAI option uses `https://api.openai.com/v1`; Ollama uses its configured base URL plus `/v1`.

The worker instantiates native `AIAgent` with a five-step bound per stage and exactly `read_case_context` and `read_reviewed_styles`. Context files, default memory and saved trajectories are disabled. Credentials go through stdin, not command arguments. Failed calls and schema/evidence validation failures route the case to staff. No provider call has been claimed successful without a real result; local tests substitute an explicit test double.

Before each stage the isolated MemoryStore is rebuilt from current feedback (at most five shortened native entries). The read-only style tool provides the current reviewed examples. The store is not the global Hermes memory. An empty projection removes previous examples; persistence/revocation has been exercised using the installed runtime without invoking an LLM.

## Public-source reads

Configure only resources BeLive is authorised to access, enable them explicitly and set the appropriate tokens in `.env`. No login, challenge handling, broad web crawl or arbitrary URL follow is implemented. HTTP redirects are rejected. Each response is limited to 1 MB and 20 seconds; each scan processes at most 25 recent text entries. There is no pagination, token refresh or historical backfill.

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

Staff issues a seven-day bearer key after verification. Only its hash is stored in the portal table; the raw key is returned once and is excluded from the idempotency cache. Do not place keys in URLs. Keys permit viewing that tenant's limited case/move fields and submitting reports/updates; they cannot access the operator snapshot.

This is a local demonstration of scoped access, not deployable identity infrastructure. The operator dashboard is accessible to the local machine user. Production use needs staff authentication and roles, tenant authentication/revocation, TLS, protection against abuse and an agreed data lifecycle. A public GitHub repository does not host the running backend or tenant portal.
