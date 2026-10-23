# BeLive Tenant Support

An independent prototype for **BeLive Ventures / BeLive CoLiving, Malaysia**, covering **existing-tenant enquiries and complaints only**. It reuses the earlier project's workflow and UI concepts in a separate application, database and memory store. Move-in/out arrangements, inspections, random PIC assignment, owner support, marketing and sales are outside the current scope.

This version has a Python/SQLite backend, native Hermes integration, tenant-scoped portal access and configurable connectors. It starts with an empty database. Fictional records and fake AI are confined to automated tests.

## Run locally

Use Python 3.11 or newer. Double-click **Run BeLive Prototype.bat**, or run:

```sh
python server.py
```

Open [the local dashboard](http://127.0.0.1:8877). The launcher starts the backend automatically in its own Python window. Keep that window open for scheduled checks; press Ctrl+C once to stop. The batch launcher exits after opening Python, so it does not show an additional “Terminate batch job” prompt. The server listens only on `127.0.0.1`. No pip packages are needed for the dashboard or deterministic workflows. AI requires a separately installed native Hermes runtime and a configured model.

## Tenant-support scope

- Record verified tenant/unit references and relevant property support guidance.
- Receive tenant enquiries and complaints through operator intake, a local tenant portal or selected authorised public API resources.
- Screen immediate risks before AI; obtain structured relevance, category, urgency, evidence, uncertainty and proposed assistance through grouped logical agents.
- Use only the tenant's verified support records and verified house rules for personal assistance. Unverified public reports receive a private-contact invitation draft.
- Hand uncertain, risky or failed AI cases to staff; track ownership, work orders, acknowledgement escalation, follow-ups and evidence-based closure.
- Review notifications before sending through a configured gateway. Store uncertain delivery as `UNKNOWN` without automatic retry.
- Review response wording after closure. Latest rejection/reopening revokes future reuse. Examples are style guidance, never verified facts or model retraining.
- Browse and search saved property, tenant and support-context records in **Database & records**; view activity and case-category counts.
- See the active database file and choose another BeLive database for the next launch.

## First walkthrough

1. Under **Tenant & property records**, enter verified house rules/support guidance and verify the tenant/unit reference against an authorised record.
2. Create a tenant support case. Without model configuration it records an explicit staff handover; it does not invent an AI answer.
3. Acknowledge the case, save a reviewed draft and queue it. Approve/deliver in **Notifications** only when a gateway is configured.
4. Record a work order if needed, complete it with evidence, start follow-up, verify the outcome and close. Silence never automatically closes a case.
5. Approve or correct reusable wording; reject it to revoke reuse.
6. Issue a tenant access key after identity verification and open [the local portal](http://127.0.0.1:8877/portal). The key exposes only that tenant's cases.
7. Open **Database & records** to inspect the saved data, search by reference or evidence, and see its database location. **Choose database for next launch** opens a local file picker. The selected file opens after a restart; current records remain in the current file.
8. Saving an authorised source starts its checks every 15 minutes while the app is open. **Pause checks** and **Resume checks** apply to that source; they do not start or stop the server.

## Configuration and actual connection status

Copy `.env.example` to `.env` in **this** project, fill only the required settings and restart. Never commit `.env`, tenant exports, database files or tokens. The original phone-support application's configuration is not read.

| Integration | Implemented | Still needed for live use |
|---|---|---|
| Native Hermes | Bounded `AIAgent` loop; triage and investigation/response stages; two read-only tools | Hermes on PATH, an OpenAI-compatible configured model through the supported OpenAI/Ollama options, provider credentials when required; live model validation |
| MemoryStore | Isolated current-feedback projection; persistence and revocation tested against installed Hermes | Operator-reviewed, redacted examples |
| Google reviews | Selected authorised Business Profile location; at most 25 recent text reviews | Company-authorised API access/token and live verification |
| Facebook / Threads | Selected Page feed/post comments or selected Threads replies; bounded reads | Required platform access, supported API version/permissions and live verification; these Meta adapters have not been verified against company accounts |
| Notification gateway | HTTPS, HMAC signature, explicit approval, idempotency key and confirmed receipt contract | A company-owned gateway that resolves internal recipients, sends through approved channels and implements the documented receipt contract |
| Company records | Staff-entered verified records | Actual property support guidance and tenancy evidence; no Spacify API connection is assumed |

`Native Hermes configured` checks local prerequisites; it does not prove a successful provider call. No live company messages, public posts, paid model calls or company API reads were made during validation.

The tenant portal and operator dashboard are a **local prototype**, not a production Internet service. The localhost operator token is a CSRF boundary, not staff login. Production hosting needs authenticated staff roles, real tenant identity verification, TLS, access revocation, retention policy and service operations before real tenant use.

## Data

State lives in SQLite, initially `data/belive.db`; sources and audit rows have append-only SQLite guards. **Database & records** shows the active file, saved property/tenant/support records, and any file selected for the next launch. A new filename starts an empty workspace; an existing BeLive database reopens its saved records. Selection does not move, copy or delete records. The selected path is an application preference in ignored `data/workspace.json`, which stores no tenant records. The optional `--database` argument overrides that preference. Native memory lives in `hermes_memory/support` beside the active database. Database access by the machine owner is outside these application guards. Email/long-number masking is basic; staff must remove names, addresses, access codes and other sensitive material from reusable examples before sharing.

Move-in/out operations have been removed from the interface, portal, AI categories and service commands. Old arrangement data is preserved on disk but is excluded from operational snapshots; legacy move notices cannot be approved or delivered. Legacy scheduling rules must be replaced with verified support guidance before AI uses that property context. Restart any running server after updating.

The earlier browser-only demo is retained in Git history. This version does not read, overwrite or migrate its `belive-complaints-prototype:v1` localStorage. Export old demo data from that version if it is needed. The running application has no dependency on the older `core.mjs` model.

## Verification

```sh
python -m unittest discover -s tests -p "test_*.py" -v
# Equivalent: npm test
```

There are 23 backend/HTTP/native-memory/database checks. The native-memory test skips if Hermes is absent and never calls a model. Tests use temporary databases and fictional records. Browser QA requires Playwright plus installed Chrome:

```sh
python -m pip install -r requirements-dev.txt
python tests/browser_check.py
```

Browser QA covers tenant records, absence of move/PIC forms, AI draft integration with a test double, case closure, memory rejection, gateway configuration failure, tenant portal, saved-record search, database selection/cancellation and persistence, source pause/resume, and eight responsive views. The native file-picker result is substituted during browser QA so tests do not open a dialog or change the real workspace. Screenshots go into ignored `artifacts/`.

Read the [tenant-support proposal and methodology](docs/TENANT_SUPPORT_METHODOLOGY.md), [system behavior and diagram mapping](docs/FORUM_SYSTEM.md), [company research](docs/COMPANY_RESEARCH.md) and [integration contract](docs/INTEGRATIONS.md).
