# BeLive Complaint Operations Prototype

An independent local project inspired by the overall BeLive complaint flowchart and the existing phone-support project's separation of deterministic workflow, review and memory concepts. It does not import or modify the phone-support application.

## Run

Double-click **Run BeLive Prototype.bat**, or run `python server.py`. Open http://127.0.0.1:8877. Python 3 is the only runtime requirement; no packages, credentials or model configuration are required. Stop the launcher with Ctrl+C.

This is an **interactive workflow prototype**, not a live AI integration. Four fictional sample cases and one fictional approved writing example are loaded into a new browser workspace. Sample records remain labelled. Operator-entered cases do not receive simulated AI results.

## Demonstrate

1. Open a high-priority sample from Overview and acknowledge it under a staff role.
2. Save a local response draft. Record an action to move into follow-up.
3. Either return the unresolved case to staff or record verification evidence.
4. Close the verified case locally, then approve or correct its wording.
5. Open Shared memory to see the reviewed example. Reject it to revoke reuse.
6. Inspect Activity log, then export a JSON copy if needed.

Use New complaint for local intake. Exact duplicate title/details are rejected. New high/critical cases go to staff review. Category and severity are operator-selected, not AI judgments. Closing requires operator-recorded verification; this is not independent proof of resolution.

## Data and separation

Cases, notes, feedback and activity live only in this browser origin's localStorage under `belive-complaints-prototype:v1`. Using another browser or port gives a different workspace. Export data before clearing browser storage or resetting the demo. Export is a backup for inspection; import is not implemented. Activity is local history, not immutable server audit storage.

There is no SQLite database, shared credential file, dependency on the Lowyat application, or connection to its Hermes memory. Marketing and sales remain separate, unconnected concepts. Complaint memory is a local collection of reviewed style examples; it is not training or automatic knowledge validation. Basic email and phone/number masking is implemented, not comprehensive PII detection.

## Implemented

- Responsive overview, inbox, overall workflow, shared-memory view and activity log.
- Local intake, exact duplicate protection, operator-assigned category and priority.
- Ownership acknowledgement, response drafting, follow-up, reassessment and verified closure gates.
- Append-in-application activity entries, reviewed examples, latest-rejection revocation and reopen revocation.
- Browser persistence, JSON export and confirmed demo reset.

## Not connected

Live Hermes/LLM generation, public-site collection, customer portals/accounts, customer identity verification, staff notifications, external messages, refunds or business actions, scheduling, autonomous follow-up, model training and cross-module memory services. The screen labels these as integration concepts. No real posts, messages or customer-system actions can be submitted.

## Tests

`npm test` (Node.js; no npm install needed) runs workflow/guard tests. Browser verification is in `tests/browser_check.py`; it requires Playwright and an installed Chrome, and uses isolated browser contexts without external services.

See [docs/FORUM_SYSTEM.md](docs/FORUM_SYSTEM.md) for architecture and the reference mapping.
