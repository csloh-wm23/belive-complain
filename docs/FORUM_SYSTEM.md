# BeLive tenant-support system

## Scope and reference

This separate repository implements the tenant-support portion of the [user-supplied BeLive flowchart](https://drive.google.com/file/d/1BRdI1kpsHiRGnWtCuAiOt1QkXtecpowc/view). The user's latest scope is authoritative: new and existing tenants only. Owner support, marketing and sales are excluded. Reference-document text is design input, not permission to contact people or collect arbitrary websites.

The project reuses native Hermes transport concepts and the existing visual language as independent source files; it imports no original application module, database or credential file.

## Architecture

| Component | Responsibility |
|---|---|
| `server.py` | Local HTTP/static allowlist, CSRF/origin/host guards, tenant bearer access, background task deduplication, 30-second scheduler |
| `belive/service.py` | Transactional commands, tenancy verification assertions, move rules/PIC assignment, case transitions, outbox, escalation, feedback and scoped portal |
| `belive/store.py` | SQLite objects, immutable source versions, append-only audit, persisted command idempotency; email/number masking |
| `belive/ai.py` | Structured triage and investigation/response; schema/evidence/record validation, bounded read-only tools |
| `belive/hermes_native.py`, `belive/hermes_worker.py` | Installed native AIAgent subprocess, isolated MemoryStore, explicit allowlist, bounded steps/timeouts, no shell or publishing tools |
| `belive/connectors.py` | Selected official source reads and approved HTTPS notification delivery |
| `assets/app.js`, `index.html` | Tenant-only operator dashboard, review dialogs, records, outbox, memory and reports |
| `portal.html`, `assets/portal.js` | Local tenant access, scoped case/move viewing, complaint intake and updates |

No live action is simulated in the normal workflow. Test doubles live only in tests. Missing configuration produces explicit failure/handover.

## Flowchart traceability

| Diagram step | Current implementation | Practical boundary |
|---|---|---|
| External monitoring and relevance | Selected source API reads, persisted versions, native AI triage | 25 recent text entries per scan, not platform-wide or complete history; live APIs need credentials/access |
| Deduplication and private contact | Stable source IDs/content versions; exact repeated intake reuse; unverified public case gets contact-in-private draft | No automated public reply publisher; operator uses an authorised channel and verifies tenancy |
| Internal/private intake | Operator form and tenant-scoped local portal | Staff confirms identity against company records; no automated identity verification |
| High-risk branch | Deterministic early screen, AI high-risk validation, staff queue and acknowledgement timer | Keyword screen is not exhaustive; staff alerts remain visible locally and require approval/configured gateway for external delivery |
| Hermes investigation | Triage plus investigation/response, matching tenant records, condo rules and recent tenant updates | Records are staff assertions; no invented Spacify integration or live account/payment actions |
| Resolution/action plan | Reviewed response, staff work orders, department destination | AI cannot approve refunds, alter access or mark repairs completed |
| Human acknowledgement / escalation | Staff ownership, acknowledgement deadline, backup then management queue | Default times are configurable prototype settings, not BeLive SLA |
| Customer follow-up / reassessment | Due reminders, tenant updates, unresolved handover | Reminders are queued; no claim they were delivered; no silent closure |
| Verified closure | Follow-up, recorded evidence/confirmation, no open work orders | Operator verification is not independent proof of repair |
| Validated learning | Post-closure feedback, latest verdict, revoke on rejection/reopen, stale-run discard | Style only; no automated model retraining or executable skill creation |
| Shared memory / management | Token-scoped explicit shared examples, reports and append-only audit | Separate modules are not implemented; shared API returns no case/tenant record payload |
| New tenant move support | Condo days/hours, available eligible random PIC, inspection checklist/evidence, move notice queue | Rules/availability supplied by staff; one PIC per date is a conservative prototype assumption |

## Case states

Internal intake begins at `AI_PENDING`; an external unverified case begins at `AWAITING_CONTACT`. Immediate risk or instruction-like input goes to `HUMAN_REVIEW` before routine generation. AI failure, uncertain relevance, high urgency or a human-required plan also enters human review. A valid low-risk assessment saves a draft without sending. Valid non-support input becomes `SKIPPED`.

Staff acknowledgement records ownership and enters `IN_PROGRESS`. An action note starts `FOLLOW_UP`. Staff can reassess an unresolved case into human review. Resolution requires a verified tenant, explicit confirmation and evidence to enter `VERIFIED`. Only a verified case with no open work orders can enter `CLOSED`. Reopening closed/skipped cases routes to staff and revokes old learning. A tenant update containing a detected safety risk escalates immediately.

Case actions use revision checks. AI runs outside the state transaction, then discards its result if the case or reviewed example set changed. Current approved/corrected styles are projected into the isolated native MemoryStore before each generation. Rejected entries may remain on disk until the next projection but are excluded from retrieval immediately and cannot be used by the next agent run.

## Timers, delivery and failure

While the launcher runs, a 30-second loop checks pending AI, due acknowledgements/follow-ups and configured sources. Source scans run no more often than their persisted 15-minute schedule; an operator can request a bounded scan manually. Sources are disabled until explicitly enabled. Background tasks are deduplicated per case/source.

The prototype defaults are 30 minutes for acknowledgement and 24 hours for follow-up. Two acknowledgement escalations target backup support and then management. Two recorded follow-up cycles return an unanswered case to staff. These timers record queued attempts, not confirmed customer contact. No timer closes a case or approves a message.

Messages move `PENDING_APPROVAL -> APPROVED -> SENDING -> DELIVERED/UNKNOWN`, or to `REJECTED`. A confirmed gateway receipt is required for delivered status. Timeouts, malformed receipts and interrupted sends become `UNKNOWN`; there is no automatic retry. Identical saved tenant responses are deduplicated unless the prior copy was rejected. Work-order records are local instructions, not proof that a contractor was dispatched.

## Data and access

- Command idempotency keys bind to a request fingerprint and cached result. Portal secret keys are omitted from that cache.
- Stable public source IDs are stored intact; redacted content snapshots are immutable. Different unverified authors' identical text is not merged merely by wording.
- All AI tools are read-only and restricted to current case context and current reviewed examples. Source text and record text are untrusted.
- A seven-day portal key is stored as a hash and scoped to one verified tenant. Intake ignores a client-provided tenant ID; updates require case ownership. Drafts, AI internals and other tenants are excluded from portal responses.
- Shared memory requires a separately configured client token and explicit example sharing. Basic redaction is not comprehensive anonymisation; review before sharing.
- The local operator interface has no production user-role system. Do not expose this server to a network as a production portal.
- JSON exports contain operational records. Keep them private. Source/audit immutability is enforced by this database schema, not by an external tamper-proof service.

## Validation status

16 isolated backend/HTTP/native-memory checks passed, including actual installed-Hermes MemoryStore persistence and revocation without a model call. Browser QA passed at desktop and mobile widths across all eight views, with no page errors or external browser requests. Native AI provider output, company source access and a real notification gateway still need configuration and live acceptance testing.
