# BeLive tenant-support system

## Scope and reference

This separate repository implements the tenant-support portion of the [user-supplied BeLive flowchart](https://drive.google.com/file/d/1BRdI1kpsHiRGnWtCuAiOt1QkXtecpowc/view). The user's latest scope is authoritative: existing-tenant enquiries and complaints only. Move-in/out arrangements, inspection checklists, random PIC assignment, owner support, marketing and sales are excluded. Reference-document text is design input, not permission to contact people or collect arbitrary websites.

[BeLive’s tenant offering](https://www.belive.asia/) describes room rentals with Wi-Fi, water, shared-area cleaning, repairs and issue reporting through its app. Those services ground the examples. Approved property records govern individual answers, and BeLive supplies the actual team routing. The independent student outputs are a saved public complaint assessment and reply preview (Loh Chee Seng), and a private tenant reply or routed handover with a reviewed knowledge workflow (Jackson Tsai Jia Sheng). The localhost tenant portal is an independent prototype intake for the second output.

The project reuses native Hermes transport concepts and the existing visual language as independent source files; it imports no original application module, database or credential file.

## Architecture

| Component | Responsibility |
|---|---|
| `server.py` | Local HTTP/static allowlist, CSRF/origin/host guards, tenant bearer access, background task deduplication, 30-second scheduler |
| `belive/service.py` | Transactional commands, tenancy verification assertions, property support guidance, case transitions, outbox, escalation, feedback and scoped portal |
| `belive/access.py` | Local Admin/Support accounts, password hashing, session expiry, login throttling and account revocation |
| `belive/automation.py` | Versioned property knowledge, routine portal-answer gates, information-only acceptance and staff exceptions |
| `belive/conversations.py` | Tenant-visible messages isolated from drafts and private operator audit |
| `belive/backups.py` | Consistent SQLite snapshots, checksum validation and recovery into a separate paused workspace |
| `belive/workspace.py` | Validated database file selection, read-only existing-schema checks and persisted next-launch preference |
| `belive/store.py` | SQLite objects, immutable source/record versions, append-only audit, persisted command idempotency; email/number masking |
| `belive/ai.py` | Separate Complaint Analysis, Support Response and conditional Safety Review agent calls; complaint/enquiry classification; schema/evidence/record validation, bounded read-only tools |
| `belive/hermes_native.py`, `belive/hermes_worker.py` | Installed native AIAgent subprocess, isolated MemoryStore, explicit allowlist, bounded steps/timeouts, no shell or publishing tools |
| `belive/connectors.py` | Selected official source reads and approved HTTPS notification delivery |
| `assets/app.js`, `index.html` | Tenant-only operator dashboard, review dialogs, records, outbox, memory and reports |
| `portal.html`, `assets/portal.js` | Local tenant access, scoped conversations, tenant replies and resolution feedback |
| `tenant-site.html`, `assets/tenant-site.js`, `assets/tenant-site.css`, `assets/tenant-home.svg` | Separate BeLive tenant website with complaint, tracking and support-topic links |

No live action is simulated in the normal workflow. Test doubles live only in tests. Missing configuration produces explicit failure/handover.

## FYP workflow, 2 November 2026

Complaint Analysis Agent identifies COMPLAINT/ENQUIRY/NON_SUPPORT, relevance, topic, LOW/MEDIUM/HIGH/CRITICAL, exact evidence and uncertainty. The UI maps LOW to SIMPLE, MEDIUM to MODERATE and HIGH/CRITICAL to HIGH. Handover/uncertain cases cannot present as SIMPLE merely because a model returned LOW. The separate Support Response Agent retrieves up to eight current property knowledge entries and five current reviewed styles. A conditional Safety Review Agent separately checks adapted guidance. Actual role, status and timestamps are stored; these are logical agents using the configured native Hermes model with read-only tools.

**Only SIMPLE replies send automatically**, and only through the private verified tenant portal after knowledge/language/confidence/version/safety gates. MODERATE is always handed to staff, while safe AI assessment and a private draft reduce staff work. Physical/account/financial requests are queued immediately and may get background AI assistance; a LOW model result cannot lower this deterministic MODERATE floor. HIGH danger bypasses routine response generation. Unknown facts stay questions or require staff; Hermes never invents property facts when prior knowledge is missing.

`belive/routing.py` holds admin-approved category destinations. The AI supplies category, deterministic routing supplies destination, and handover queues a local STAFF_ALERT. Unconfigured categories use Support team. This does not claim an external message reached a department. Work orders and gateway delivery remain separately reviewed.

`belive/learning.py` runs isolated real-model before/after comparisons against the same immutable question and approved guide. The demo offers Wi-Fi, maintenance, cleaning, access, utilities, billing, house rules and general support when each topic has current approved English guidance. The practice drafting agent uses the same selected guide in both runs, and the separate Safety Review Agent checks each draft. The approved redacted style lesson affects only the second run. Clarity checks require a reply starting directly with points 1 and 2, exactly one question mark, and at most 90 whitespace-separated words. Word counts are also recorded. Adoption requires more checks, or all checks passing with at least 20% fewer words and at least 12 words. Only an actually measured improvement automatically creates an active learned_style scoped to the fictional demo property and selected category. After classification, the reply agent receives matching topic lessons. The assessment and safety review use the report and current guidance. Earlier Wi-Fi demo lessons keep their Wi-Fi scope. Revoke excludes it immediately and stale in-flight results are discarded. Provider failure, interruption, changed guidance and equal/worse output never create fabricated improvement. These are narrow writing checks, not factual accuracy, causality proof or retraining. Normal support also automatically retrieves latest approved/corrected redacted styles from verified closed cases, excluding rejection/reopening. Company knowledge remains separately reviewed and versioned.

`belive/demo.py` prepares an explicit fictional property/tenant and missing tracked demonstration knowledge entries without replacing normal records. One-hour demo sessions are scoped to these reserved demo_only records; supplied tenant IDs cannot select a different tenant. Disabling demo revokes its sessions. Recovery disables demo access, automation and learned styles and interrupts pending comparisons; no withdrawn lesson is revived.

Staff navigation presents Command center, Complaints, Public reviews and Self-learning, with advanced screens under System setup. Public reviews offers one-click collection for all enabled sources, per-platform outcomes and collapsed source and schedule settings. Collection is available to Support and Admin accounts. Source configuration stays with administrators. Tenant navigation is New request / My requests with one selected conversation. `docs/THURSDAY_DEMO.md` documents the live walkthrough.

Self-learning opens directly to the comparison form with the configured model and an example for each approved topic. The operator generates the first reply, reviews or edits a writing tip, and approves it by selecting Use this tip & generate second reply. Past comparisons remain available below the form. The learning lab shows the stored topic and question with each reply comparison. Editing the practice input clears the displayed comparison until a new run is accepted or a saved run is explicitly selected. A rejected request stays visible as a form error during status refresh. Use the Complaints workflow for unresolved repairs; the lab uses approved guides for safe informational exercises. On a later staff case, AI assessment lists any current approved wording examples provided to the response agent and links to their source cases. Compare the actual draft with the example to see what wording was applied.

## Tenant website entry and internal complaints

`GET /belive` serves the tenant-facing website; staff dashboard remains `/`. Report/support-topic links open `/portal`, with an optional topic prefill. The portal sends authenticated, idempotent intake to the backend. Normal access uses a verified tenant's private code. **Try demo tenant** calls `POST /api/demo/session`, available only after explicit fictional setup. Host/origin guards apply; it cannot open arbitrary tenants. Keys stay in memory, never URLs or browser storage. Sign out clears all rendered case titles/messages, in-page keys and drafts.

The backend resolves tenancy from the bearer key and ignores supplied tenant/entrypoint values. The existing `/api/website/complaints` API remains supported for independent form integrations with the same checks; the redesigned main website uses the simpler portal entry. Both use immutable source versions, risk screening, background AI, actual saved case IDs and the same scoped staff queue. `/portal?case=CASE_ID#conversations` focuses a case only if it belongs to the authenticated tenant. Operator case links still require staff login.

For Google, Facebook and Threads, the Complaint Analysis Agent runs before matching approved public guidance. Only a certain SIMPLE complaint can get an automatic local guidance draft. MODERATE and HIGH complaints route to staff. Staff can generate a separate tailored draft with the Public Reply Preview Agent. Its redacted source context and saved text are kept separate from tenant conversations and the delivery outbox. The same case revision must still be current before saving the preview. HIGH previews open with an apology that names the reported issues and acknowledges the impact. The preview asks the reviewer to share unit and contact details privately in the BeLive tenant app so staff can follow up.

SIMPLE replies can be automatic after all checks; all other AI drafts remain private. Tenant feedback cannot verify physical repairs or close maintenance cases. Still unresolved gives inline confirmation and staff handover. No public social posting or Internet hosting is introduced.

## Flowchart traceability

| Diagram step | Current implementation | Practical boundary |
|---|---|---|
| External monitoring and relevance | Selected source API reads, persisted versions, native AI triage | 25 recent text entries per scan, not platform-wide or complete history; live APIs need credentials/access |
| Deduplication and private contact | Stable source IDs/content versions; exact repeated intake reuse; unverified public case gets contact-in-private draft | No automated public reply publisher; operator uses an authorised channel and verifies tenancy |
| Internal/private intake | Operator form and tenant-scoped local portal | Staff confirms identity against company records; no automated identity verification |
| High-risk branch | Deterministic early screen, AI high-risk validation, staff queue and acknowledgement timer | Keyword screen is not exhaustive; staff alerts remain visible locally and require approval/configured gateway for external delivery |
| Hermes investigation | Triage plus investigation/response, matching tenant records, verified house rules and recent tenant updates | Records are staff assertions; no invented Spacify integration or live account/payment actions |
| Resolution/action plan | Reviewed response, staff work orders, department destination | AI cannot approve refunds, alter access or mark repairs completed |
| Human acknowledgement / escalation | Staff ownership, acknowledgement deadline, backup then management queue | Default times are configurable prototype settings, not BeLive SLA |
| Customer follow-up / reassessment | Due reminders, tenant updates, unresolved handover | Reminders are queued; no claim they were delivered; no silent closure |
| Verified closure | Follow-up, recorded evidence/confirmation, no open work orders | Operator verification is not independent proof of repair |
| Validated learning | Post-closure feedback, latest verdict, revoke on rejection/reopen, stale-run discard | Style only; no automated model retraining or executable skill creation |
| Shared memory / management | Token-scoped explicit shared examples, reports and append-only audit | Separate modules are not implemented; shared API returns no case/tenant record payload |

## Case states

Internal intake begins at `AI_PENDING`; an external unverified case begins at `AWAITING_CONTACT`. Immediate risk or instruction-like input goes to `HUMAN_REVIEW` before routine generation. AI failure, uncertain relevance, high urgency or a human-required plan also enters human review. A valid low-risk assessment saves a draft without sending. An open staff case shows background assessment progress and updates when the result is ready, while leaving unsaved staff input alone. Valid non-support input becomes `SKIPPED`.

Staff acknowledgement records ownership and enters `IN_PROGRESS`. An action note starts `FOLLOW_UP`. Staff can reassess an unresolved case into human review. Resolution requires a verified tenant, explicit confirmation and evidence to enter `VERIFIED`. Only a verified case with no open work orders can enter `CLOSED`. Reopening closed/skipped cases routes to staff and revokes old learning. A tenant update containing a detected safety risk escalates immediately.

Case actions use revision checks. AI runs outside the state transaction, then discards its result if the case, public conversation, verified support context/property version or reviewed example set changed. Current approved/corrected styles are projected into the isolated native MemoryStore before each generation. Rejected entries may remain on disk until the next projection but are excluded from retrieval immediately and cannot be used by the next agent run.

## AI evidence and diagnostics

Triage evidence must be an exact, case-sensitive, bounded quote from the tenant's complaint **title or description**. The application records the matching `evidence_field` itself and displays it beside the quote; this identifies a tenant report, not a verified repair finding. Paraphrases, invented quotes and excerpts found only in support records or conversations are rejected. This fixes a false rejection where the model quoted a valid title while the validator previously checked only the description.

Failed analysis jobs preserve fixed, allowlisted error codes (for example `AI_UNGROUNDED_EVIDENCE`, `AI_INVALID_SCHEMA` or `HERMES_TIMEOUT`), with a plain-language explanation on the staff case. Unexpected errors retain the generic `AI_FAILED_OR_INVALID` fallback. Raw provider exceptions, credentials and response bodies are never copied into case errors or audit events. Failures still go to staff; no response is published or repair claimed. A successful operator-triggered retry replaces the old failure explanation with its current assessment or human-handover reason, while previous failed jobs remain in the audit history. Validation failures are not automatically retried.

## Timers, delivery and failure

While the launcher runs, a 30-second loop checks pending AI, due acknowledgements/follow-ups and configured sources. Source scans run no more often than their persisted 15-minute schedule; an operator can request a bounded scan manually. Saving an authorised source starts its checks by default. Existing paused sources remain paused across restarts. Operators can pause/resume checks for an individual source; there is no server-enable setting. Background tasks are deduplicated per case/source.

The prototype defaults are 30 minutes for acknowledgement and 24 hours for follow-up. Two acknowledgement escalations target backup support and then management. Two recorded follow-up cycles return an unanswered case to staff. These timers record queued attempts, not confirmed customer contact. No timer closes a case or approves a message.

Messages move `PENDING_APPROVAL -> APPROVED -> SENDING -> DELIVERED/UNKNOWN`, or to `REJECTED`. A confirmed gateway receipt is required for delivered status. Timeouts, malformed receipts and interrupted sends become `UNKNOWN`; there is no automatic retry. Identical saved tenant responses are deduplicated unless the prior copy was rejected. Work-order records are local instructions, not proof that a contractor was dispatched.

For public review assessment, a reported fault remains a complaint even if the reviewer also asks a question. Praise alone is outside support. If the model returns conflicting complaint and relevance labels, analysis asks for a single corrected classification. A second conflict leaves the case for staff review. Approved public SIMPLE drafts use public-facing wording with private next steps rather than tenant-portal conversation controls.

In a Google public case, **Source evidence and activity → Save review link** stores the link copied with Share on the individual review or the Maps URL for that contributor’s review at the selected place. The reviewed link takes priority in the case and discovery list. The original intake URL, case status and evidence versions remain intact. Listing-only links are labelled as listings and a review share link does not trigger any automated Google request.

**Public reviews → Import a Google review from a link** reads one individual written review in a fresh, signed-out Chrome session using open-source Playwright. Install the project’s Playwright dependency with `python -m pip install -r requirements-dev.txt`. This operator-triggered import needs a review Share link and creates a redacted public case for assessment. It reopens an existing case when the contributor/place permalink or captured review ID matches. Unavailable or ambiguous pages can be recorded manually. The separate scheduled collection uses its configured platform API.

**Public reviews → Collect up to 10 reviews** opens the selected Google Maps listing in Chrome and reads visible written 1–2 star reviews. The admin can open Google sign-in for collector, sign in manually in its separate Chrome profile, then close that window. Listing scans reuse that profile locally. Individual review imports continue to use a fresh signed-out session. Staff can also paste several individual review Share links into the same field. New cases are queued together and assessed one at a time. Repeat captures use the existing case for the same review ID. A listing capture uses the Maps listing as its source, and the case can later store the exact Share link. If Google exposes fewer matching reviews, the app shows the count collected. The collector tries to sort by lowest rating, then scrolls the review panel as soon as it is visible, even when Maps displays its loading indicator. It checks review IDs after each scroll so it can handle reused rows. If Maps exposes no readable reviews, try the individual review Share links. Private complaints support customer confirmation from the submitting browser. Staff can close an imported public case after taking ownership and recording checked outcome evidence.

## Data and access

- Command idempotency keys bind to a request fingerprint and cached result. Portal secret keys are omitted from that cache.
- Stable public source IDs are stored intact; redacted content snapshots are immutable. Different unverified authors' identical text is not merged merely by wording.
- All AI tools are read-only and restricted to current case context and current reviewed examples. Source text and record text are untrusted.
- A private browser session is stored as a hash and grants access to complaints submitted in that browser. Intake ignores a client-provided tenant ID; updates require case ownership. Drafts, AI internals and other tenants are excluded from portal responses.
- Shared memory requires a separately configured client token and explicit example sharing. Basic redaction is not comprehensive anonymisation; review before sharing.
- Operator data APIs require a valid login session and CSRF token. Admin-only operations are rejected for Support accounts at the server. This remains a loopback service, not a publicly hosted identity platform.
- JSON exports contain operational records. Keep them private. Source/audit immutability is enforced by this database schema, not by an external tamper-proof service.

## Database interface and launch behavior

**More tools → Saved records** displays the active SQLite file and searchable property, verified-tenant and support-context tables from the server snapshot. Reloading the browser reads the same database; there is no browser-local record store. Cases, outbox, sources and audit remain in their respective operational views.

The operator can choose a SQLite file with the local native picker. The protected endpoint validates the idempotency key before opening the picker. Cancellation makes no change. Selection stores only the next-launch path in ignored `data/workspace.json`, while the current connection continues using the active file. Existing unrelated databases are rejected using read-only schema inspection. A new file is created only when the application next opens it. No live database file is moved, copied or deleted. The explicit CLI `--database` option overrides the saved preference for that launch. The default selection is `data/belive.db`.

The Windows batch launcher opens Python in a dedicated console and immediately exits. The server starts automatically. Ctrl+C is handled by Python for clean shutdown; no batch process remains waiting to request “Terminate batch job”, and there is no pause after a normal shutdown.

## Conversations, ownership and deadlines

In review mode, publishing to the tenant portal is an explicit operator action on the saved response. Optional routine automation uses the separate approved-knowledge gate described below. Manual publication requires verified tenancy, an active case and confirmation that the exact wording was reviewed. Automatic publication follows the EXACT or GUIDANCE controls below. Identical published wording is deduplicated per case. It creates a real local portal message and does not claim email/social/gateway delivery. Drafts, analysis, citations, work orders and internal notes remain private.

The portal returns only the current tenant's public conversation. Tenant updates are persisted and included in future AI context. Outcome feedback records the tenant's assertion; it does not verify or close the case. An unresolved outcome can reopen a closed case and revoke its previous style example. Safety flags in an update or outcome feedback override routine processing and require critical staff handling, even if the tenant selected resolved.

Acknowledgement records the signed-in operator name. Operators can record a manual category/urgency assessment, private note and future action deadline. Detected safety flags cannot be downgraded through that assessment. The queue places active critical cases first, then overdue work and remaining urgency/deadline order. Closure clears the active due-state display. Default timers are still prototype settings, not claimed BeLive SLAs.

## Versioned support context

Support records carry a version, active state, optional expiry, source reference and correction reason. A correction requires source verification and the expected current version; deactivation stops future AI retrieval. Every version is retained in `record_history`, with database triggers prohibiting history updates/deletions. Property guidance also retains versions. Legacy records are treated as version 1 and acquire history on their next edit.

AI context contains only the matching tenant's current active, unexpired verified support records. Saved citations capture the exact ID/version/source/text used. A context change during generation discards the result. Historical citations remain evidence of what was used at the time and do not establish that the guidance is still current; operators must review before publication.

## Operator access and revocation

First-run setup creates one local administrator using the chosen password; it is disabled after an account exists. Passwords are salted PBKDF2-HMAC-SHA256 hashes with 600,000 iterations, following the algorithm/work-factor guidance in [OWASP Password Storage](https://cheatsheetseries.owasp.org/cheatsheets/Password_Storage_Cheat_Sheet.html). The API never returns password hashes in its snapshots or user list. Login failures are throttled after five attempts for the same username.

An operator session lasts eight hours; the browser cookie is HttpOnly and SameSite=Strict, and only a hash of the random session secret is stored. Logout/deactivation revokes sessions. Support accounts can handle cases and reviewed responses. Admins manage accounts, verified records, source configuration, AI connection checks, memory projection and database recovery. Both roles can read operational case context; this is a small support-team permission model, not property-by-property access control. Password recovery/MFA, external identity providers and public TLS hosting are outside this local implementation.

Tenant keys remain separate bearer credentials and can be revoked by an admin without deleting the conversation. Revocation and session expiry are checked on subsequent requests; hidden controls are not the authorization boundary.

## Consistent backups and recovery

Backup uses the [SQLite connection backup API](https://docs.python.org/3/library/sqlite3.html#sqlite3.Connection.backup), verifies integrity and records a checksum. Files are created with unique names and existing files are not overwritten. Recovery validates the saved checksum and schema, then creates a separate database for the next launch. The active database stays intact.

The recovered copy revokes staff and customer browser sessions, pauses source reads, holds outstanding gateway messages, clears due timers, routes active cases to staff, deactivates recovered support context and appends rejection verdicts for recovered style examples. Property guidance is marked for revalidation. This prevents an older snapshot from silently re-enabling a subsequently rejected example or replaying old external actions. Restored account credentials are those present in the backup. Source/audit/history evidence is retained.

## Real connection checks and evaluation

The admin connection test runs a genuine configured-provider probe through native Hermes, with neutral context and a separate isolated check-memory directory. Only a valid actual response records success; missing configuration/failures are reported. A prior successful check is dated evidence, not continuous provider health.

`evals/tenant_support.json` contains 24 clearly fictional English/Malay/Chinese cases. `scripts/evaluate_ai.py` makes no provider calls unless explicitly invoked with `--run-live`. Live evaluation uses a temporary database, captures schema/category/handover results and requires human review for factual and language quality. It does not insert examples into the normal workflow or claim a measured score without a run.

## Scope correction and existing data

Move scheduling, move completion and PIC availability commands have been removed. The command allowlist rejects those actions before reading cached idempotency results, so a legacy successful request cannot reactivate them. The dashboard/portal no longer return move arrangements or PIC availability. Property records retain only identity and verified support guidance in the current API.

Existing arrangement objects and append-only activity are retained for history. Legacy move notices are excluded from the active outbox and cannot be approved or sent, even by direct delivery requests. Scheduling-specific property rules are excluded from AI context until staff records current support guidance. The removed `MOVE_IN_OUT` category is rejected in new AI output; historical category values display as `OTHER` and their old examples are excluded from reuse. A restart is required to replace an already running older server.

## Validation status

45 isolated backend/HTTP/native-memory/database checks passed, including actual installed-Hermes MemoryStore persistence and revocation without a model call. Browser QA passed at desktop and mobile widths across all eight views, with no page errors or external browser requests. Database persistence, read-only rejection of unrelated files, next-launch selection, protected picker cancellation and source pause/resume are covered; browser tests substitute the native picker result rather than opening a real dialog. A separate Windows smoke check started the real batch launcher against a temporary database and confirmed that one Ctrl+C stopped its isolated Python console without a batch prompt. The new authenticated browser walkthrough additionally verifies portal replies/privacy/outcomes, record correction, backup controls and Support role restrictions. A limited real Hermes/Ollama Cloud smoke test passed on 26 October 2026, as recorded in `LIVE_AI_SMOKE_TEST.md`. Broader provider quality, company source access and external gateway delivery still require live acceptance testing.

An earlier tenant-website walkthrough passed at 1440px and 390px before browser-based tracking: complaint and tracking links, topic prefills, invalid/valid access keys, intake saved to the operator queue, reviewed reply, tenant follow-up, return navigation and clearing in-page records. It uses a temporary database and explicit test-only AI. During this walkthrough, the portal intake handler was corrected to capture form values before disabling controls; operator-reviewed responses and private internal notes remain isolated.

Direct website submission is covered by scoped-tenant, cross-origin, idempotency and immediate-risk HTTP checks. The updated browser walkthrough loses a committed receipt and retries it without a duplicate, opens the same case after staff login, follows its reviewed reply through the private tracking link and checks desktop/mobile layouts. These UI checks use fictional records, a temporary database and explicit test-only AI.

The title-evidence regression adds seven checks for exact title/description provenance, rejected paraphrases and unrelated excerpts, schema enforcement, safe error diagnostics, retry recovery and human-required repairs. The complete staff browser walkthrough passed after the evidence label change. A user-authorised live Hermes/Ollama retest on 27 October 2026 completed a validated maintenance assessment with HIGH urgency and staff handover; no response was published. See `LIVE_AI_SMOKE_TEST.md` and `PRESENTATION_WALKTHROUGH.md`.


## Property knowledge and optional routine automation

See [the setup and operating guide](AI_KNOWLEDGE_AND_AUTOMATION.md). Admins approve versioned, property-scoped informational answers with language, source and optional expiry. Both reviewed AI drafts and optional routine automation retrieve relevant current knowledge. Knowledge is verified context, not response-style memory or model retraining.

Automation defaults off for existing databases and affects only new private tenant requests after enablement. It uses the existing grouped native Hermes stages. The model selects an approved answer with confidence, request language and case evidence. Deterministic gates require a certain, supported response matching the verified tenant's property and language. EXACT knowledge preserves approved wording and requires LOW urgency. GUIDANCE knowledge supports automatic adapted information or safe clarification only at LOW (SIMPLE) urgency; MEDIUM (MODERATE) assistance is held for staff review, only after a separate native Hermes groundedness/safety review passes and the selected guide is cited. HIGH/CRITICAL, uncertainty, failed review and human-required actions cannot publish automatically. The reviewer is an additional safeguard, not a correctness guarantee. It rechecks case, record, policy and knowledge versions inside the commit transaction.

Portal follow-ups schedule a fresh assessment automatically. A maximum of three automatic answers prevents endless loops. Explicit human requests, failed answers, missing knowledge, policy/record uncertainty, dangerous content and unsupported actions go to staff. Handover creates a private portal receipt and the existing local staff alert, without claiming external delivery or staff acknowledgement.

The ANSWERED state means a tenant accepted an informational answer. It is separate from CLOSED, physical repair completion and verified-closure metrics. Unresolved feedback reopens staff handling. Customer-facing follow-up cases now close after 7 days without a reply by default, with an unconfirmed inactivity reason rather than a verified resolution. This does not create learning examples, and the customer can reopen the case from Track complaint in the submitting browser. Automatic check-ins remain private portal messages. Recovery pauses automation and deactivates knowledge pending review. No live company facts or automatic public/external messages were seeded or sent by this change.

## Tenant feedback visibility and fresh requests

The portal displays plain-language case status and an explanation beside each conversation. A pending automatic assessment is identified separately from a saved request awaiting staff review. Choosing Still unresolved saves the entered note and requests staff handling; it does not start another automatic FAQ cycle. Confirmation and errors appear beside the clicked controls and move into view. Subsequent tenant messages remain visible to staff while the case awaits review.

If a response is lost after the server commits a tenant update, the portal retains the text and reuses the same idempotency key for an unchanged retry. A new private request after ANSWERED, CLOSED or SKIPPED receives a new case instead of inheriting that old outcome. Replays of the original submission, active duplicate protection and stable public-source identity remain unchanged.

Demo knowledge may include low-risk device-side Wi-Fi checks based on a named public technical source. It remains scoped to the fictional demo property and does not establish BeLive equipment instructions, permission to alter shared equipment, an outage diagnosis or a repair result. Missing approved knowledge and physical-action requests continue to require staff.

## Reusable guidance validation, 2 November 2026

The demo property contains 24 GUIDANCE entries across all eight tenant-support categories and three target answer languages, alongside 12 EXACT portal FAQs. General intake playbooks describe the local support process; they do not supply real property rules or tenant account facts. The Wi-Fi guide cites Microsoft Support for device-side connectivity checks. Exact replies remain available when fixed wording is appropriate.

The full isolated suite passed 70 checks. An additional regression for retaining the current approved style projection also passed with the affected guidance and native-memory tests. Browser checks passed for tenant handover at desktop/mobile sizes, a lost confirmation retried without duplicate feedback, a fresh request after acceptance, and admin guidance save/edit controls. Browser AI is an explicit test double.

Separate real configured-model checks passed for naturally worded Wi-Fi guidance, a contextual follow-up and cleaning-report intake. The selected guides passed the native knowledge/safety review before publication. Unknown pet rules, financial action and a danger report went to staff. These fictional checks establish specific workflows, not general AI accuracy, real company integration or autonomous repair completion. Private reports remain outside versioned project data.


## FYP update verification

88 automated checks passed after the FYP workflow update, including complaint classification, SIMPLE-only publication, MODERATE assistance without sending, safety bypass, approved routing, demo isolation/revocation, measured learning, future retrieval and paused recovery. A real configured Hermes/Ollama run sent one SIMPLE private answer, held a broken-fan MODERATE draft and screened smoke/sparks directly to staff. Browser checks at 1440px and 390px covered tenant navigation, unresolved feedback, private MODERATE drafts, actual agent display, routing, comparison and revocation. Test doubles are explicitly labelled in browser tests; native results use the real configured model. Private raw reports stay in ignored artifacts. These are limited tests, not general accuracy or production readiness claims.

The installed local app's real-model comparison `LEARN-6FD369679E` improved from 2/3 to 3/3 declared writing checks and from 74 to 25 words, using the same question and approved guide. Its approved style lesson was adopted automatically. A fresh ordinary demo request retrieved that lesson, recorded all three actual agent stages and published one SIMPLE private response. This demonstrates specific feedback retrieval and writing improvement; it does not establish general accuracy or that repairs were completed. Existing accounts and all 11 pre-update cases were verified unchanged during installation. Staff navigation now preserves the selected page in the URL and across refresh.


The staff alert button opens urgent, overdue and unassigned staff-review cases. Support operators see their assignments first within each priority and can filter to their own cases. Admins can use the same overdue filter across teams. The reply editor shows the latest tenant message alongside the draft. Reports count newly published staff replies, how many tracked AI drafts were sent unchanged, and distinct previously answered, verified or closed cases reopened after a reply. Older cases contribute only when a tracked action happens after the update.

The local Ollama path asks Hermes to request JSON with thinking disabled. For response drafting, it requests the expected JSON fields explicitly and still validates values and citations. For local triage, the model may select the source field and the server extracts the exact text, preserving source traceability. See [demo rehearsal](THURSDAY_DEMO.md) for local startup and test coverage.
