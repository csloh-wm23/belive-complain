# BeLive Tenant Support

An independent prototype for **BeLive Ventures / BeLive CoLiving, Malaysia**, covering **existing-tenant enquiries and complaints only**. It reuses the earlier project's workflow and UI concepts in a separate application, database and memory store. Move-in/out arrangements, inspections, random PIC assignment, owner support, marketing and sales are outside the current scope.

This version has a Python/SQLite backend, native Hermes integration, tenant-scoped portal access and configurable connectors. It starts with an empty database. Fictional records are confined to tests and the separate opt-in evaluation set; fake AI exists only in automated tests.

## New here?

Start with the [short teammate guide](docs/TEAMMATE_GUIDE.md) or [download the two-page PDF](output/pdf/BeLive-Quick-Guide.pdf). They explain the first login, all eight pages, the Resource field and one practice case.

## Run locally

Use Python 3.11 or newer. Double-click **Run BeLive Prototype.bat**, or run:

```sh
python server.py
```

Open [the local dashboard](http://127.0.0.1:8877). The launcher starts the backend automatically in its own Python window. Keep that window open for scheduled checks; press Ctrl+C once to stop. The batch launcher exits after opening Python, so it does not show an additional “Terminate batch job” prompt. The server listens only on `127.0.0.1`. No pip packages are needed for the dashboard or deterministic workflows. AI requires a separately installed native Hermes runtime and a configured model.

On the first launch for a database, create your own administrator account in the dashboard. There is no default password. Admins can create Support accounts under **Tenant & property records**. Operator accounts belong to that database, so selecting a new empty database starts a new setup.

## Tenant-support scope

- Sign in as an Admin or Support operator; admin-only settings are enforced by the API.
- Record verified tenant/unit references and relevant property support guidance.
- Receive tenant enquiries and complaints through operator intake, a local tenant portal or selected authorised public API resources.
- Screen immediate risks before AI; obtain structured relevance, category, urgency, evidence, uncertainty and proposed assistance through grouped logical agents.
- Use only the tenant's verified support records and verified house rules for personal assistance. Unverified public reports receive a private-contact invitation draft.
- Hand uncertain, risky or failed AI cases to staff; show critical and overdue cases first, record the next action/deadline, maintain internal notes and require evidence for closure.
- Publish reviewed responses to a tenant-scoped conversation. Tenants can reply and report resolved/unresolved outcomes; their confirmation never automatically closes a case.
- Correct, expire or deactivate verified support context with immutable version history. AI citations show the exact record version used; changes during generation discard the result.
- Review notifications before sending through a configured gateway. Store uncertain delivery as `UNKNOWN` without automatic retry.
- Review response wording after closure. Latest rejection/reopening revokes future reuse. Examples are style guidance, never verified facts or model retraining.
- Browse and search saved property, tenant and support-context records in **Database & records**; view activity and case-category counts.
- See the active database file and choose another BeLive database for the next launch.
- Create verified SQLite backups and recover into a separate workspace without overwriting the active database.
- Run an actual AI connection probe and use a separate English/Malay/Chinese evaluation set.

## First walkthrough

1. Create/sign in to the database's admin account. Add a Support account if another teammate will handle cases.
2. Under **Tenant & property records**, save verified support guidance and verify a tenant/unit reference against an authorised record. Add relevant support context.
3. Create a case. Without model configuration it explicitly hands over to staff. With configuration it proposes structured AI assistance; the normal workflow never substitutes a fictional response.
4. Acknowledge the case under the signed-in operator. Review the urgency/category, save the next action/deadline and add any private notes.
5. Review and save the response draft, check the confirmation box, then select **Publish saved response to tenant portal**. This creates an actual message in the local portal. External gateway delivery remains a separate reviewed action.
6. As admin, issue a tenant access key after identity verification and open [the local portal](http://127.0.0.1:8877/portal). The tenant sees published messages and can reply. **Still unresolved** routes/reopens the case to staff; **Issue resolved** records feedback for staff verification.
7. Complete work orders, follow up, verify the outcome and close. Close only with evidence and no open work orders. Review reusable wording after closure; latest rejection/reopening revokes reuse.
8. Open **Database & records** to inspect data and record versions. Correct or deactivate outdated support context. Create a verified backup. Recovery opens a new paused copy on the next launch; current records stay in place.
9. Saving an authorised public source starts its checks every 15 minutes while the app is open. **Pause checks** / **Resume checks** affect only that source.

## Real AI connection and evaluation

Configure this project's `.env`, restart and use **Test AI connection** under **Tenant & property records**. The test sends a neutral prompt with no tenant records and requires a genuine schema-valid provider response. Provider charges may apply. Its saved outcome distinguishes `RUNNING`, `PASSED` and `FAILED`; configuration presence alone is not a successful check.

The separate evaluation set contains 24 fictional cases: eight each in English, Malay and Chinese. Inspect it without calling a provider:

```sh
python scripts/evaluate_ai.py
```

Opt in to actual model evaluation only after configuration:

```sh
python scripts/evaluate_ai.py --run-live --limit 24
```

The script uses an isolated temporary database, not the operator database, and writes an ignored report to `artifacts/ai-evaluation.json`. Automated scoring checks valid output, expected categories and required human handover. Human review is still needed for language quality, factual accuracy and usefulness. A [real Hermes/Ollama Cloud smoke test](docs/LIVE_AI_SMOKE_TEST.md) passed on 26 October 2026 using three provider requests and fictional tenant records. The full 24-case evaluation has not been run; this limited smoke test is not an overall quality score.

## Configuration and actual connection status

Copy `.env.example` to `.env` in **this** project, fill only the required settings and restart. Never commit `.env`, tenant exports, database files or tokens. The original phone-support application's configuration is not read.

| Integration | Implemented | Still needed for live use |
|---|---|---|
| Native Hermes | Bounded `AIAgent` loop; triage and investigation/response stages; two read-only tools | Hermes on PATH, an OpenAI-compatible configured model through the supported OpenAI/Ollama options, provider credentials when required; validation of your own connection and broader support quality |
| MemoryStore | Isolated current-feedback projection; persistence and revocation tested against installed Hermes | Operator-reviewed, redacted examples |
| Google reviews | Selected authorised Business Profile location; at most 25 recent text reviews | Company-authorised API access/token and live verification |
| Facebook / Threads | Selected Page feed/post comments or selected Threads replies; bounded reads | Required platform access, supported API version/permissions and live verification; these Meta adapters have not been verified against company accounts |
| Notification gateway | HTTPS, HMAC signature, explicit approval, idempotency key and confirmed receipt contract | A company-owned gateway that resolves internal recipients, sends through approved channels and implements the documented receipt contract |
| Company records | Staff-entered verified records | Actual property support guidance and tenancy evidence; no Spacify API connection is assumed |

`Native Hermes configured` checks local prerequisites; it does not prove a successful provider call. Real Ollama Cloud calls were made for the documented fictional-data smoke test. No live company messages, public posts or company API reads were made during validation.

The application remains a local prototype listening only on loopback. It now has Admin/Support login, hashed passwords, expiring operator sessions, account deactivation and tenant-key revocation. Production hosting still requires a deployment design, TLS, stronger tenant identity verification, operational monitoring and agreed retention rules. A public GitHub repository does not host the running portal.

## Backup and recovery

Admin **Create verified backup** uses SQLite's online backup API and an integrity check, then records a SHA-256 checksum. Backups are saved beside the active database under `backups/`; they contain sensitive database content, including account password hashes, and are not served as public downloads.

**Recover into a separate workspace** checks that checksum, creates a new copy under `recovered/` and selects it for the next launch. It does not overwrite the active database or the backup. In the recovered copy, old sessions and tenant keys are revoked, sources are paused, outstanding gateway messages are held, active cases require staff review, and support guidance/style examples require fresh review before AI reuse. Sign in with an admin account present in the backup and revalidate records before resuming work. `--database` still overrides the selected file for an explicit CLI launch.

## Data

State lives in SQLite, initially `data/belive.db`; sources and audit rows have append-only SQLite guards. **Database & records** shows the active file, saved property/tenant/support records, and any file selected for the next launch. A new filename starts an empty workspace; an existing BeLive database reopens its saved records. Selection does not move, copy or delete records. The selected path is an application preference in ignored `data/workspace.json`, which stores no tenant records. The optional `--database` argument overrides that preference. Native memory lives in `hermes_memory/support` beside the active database. Database access by the machine owner is outside these application guards. Email/long-number masking is basic; staff must remove names, addresses, access codes and other sensitive material from reusable examples before sharing.

Move-in/out operations have been removed from the interface, portal, AI categories and service commands. Old arrangement data is preserved on disk but is excluded from operational snapshots; legacy move notices cannot be approved or delivered. Legacy scheduling rules must be replaced with verified support guidance before AI uses that property context. Restart any running server after updating.

The earlier browser-only demo is retained in Git history. This version does not read, overwrite or migrate its `belive-complaints-prototype:v1` localStorage. Export old demo data from that version if it is needed. The running application has no dependency on the older `core.mjs` model.

## Verification

```sh
python -m unittest discover -s tests -p "test_*.py" -v
# Equivalent: npm test
```

There are 35 backend/HTTP/native-memory/database checks. The native-memory test skips if Hermes is absent and never calls a model. Tests use temporary databases and fictional records. Browser QA requires Playwright plus installed Chrome:

```sh
python -m pip install -r requirements-dev.txt
python tests/browser_check.py
```

Browser QA covers first-admin setup and Support login, role-restricted controls, reviewed portal replies, private-note isolation, tenant unresolved/resolved feedback, verified closure, versioned-record correction, backups, a test-double connection check, database selection/persistence, source controls and eight responsive views. The native file-picker result is substituted during browser QA so tests do not open a dialog or change the real workspace. Screenshots go into ignored `artifacts/`.

Read the [tenant-support proposal and methodology](docs/TENANT_SUPPORT_METHODOLOGY.md), [system behavior and diagram mapping](docs/FORUM_SYSTEM.md), [company research](docs/COMPANY_RESEARCH.md) and [integration contract](docs/INTEGRATIONS.md).
