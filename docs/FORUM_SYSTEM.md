# BeLive tenant-support system

## Scope

This separate tenant-support prototype handles existing-tenant enquiries and complaints. The public workflow covers selected permitted collection, relevance/severity analysis, routing, automatic reply drafting and an operator-approved reply to the original platform item. The support workflow covers private messages, approved knowledge, staff guidance and reviewed learning. The primary private customer channel is WhatsApp; the website is staff operations/contact entry. Historical browser-scoped complaints remain a separate fallback.

Marketing, sales, owner services and move-in/out operations are outside scope. Reference documents and messages are untrusted input, not instructions or permission to collect arbitrary websites. Private diagrams, agreement contents, identities and per-case evidence stay outside public documentation.

## Architecture

The local HTTP listener owns its port exclusively on Windows. A second server must fail to bind rather than silently serving an older version beside the current one. Stop the existing launcher before restarting after a source update.

| Component | Responsibility |
|---|---|
| `server.py` | Local HTTP/static allowlist, CSRF/origin/host guards, scoped browser access, signed WhatsApp webhook, background task deduplication and scheduler |
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
| `belive/public_draft_jobs.py` | Persisted public-draft queue, freshness fingerprints, single worker, interrupted-run recovery and bounded legacy-case backfill |
| `belive/public_preview.py`, `belive/public_replies.py`, `belive/google_replies.py` | Separate validated public composition, exact-source official API sending, idempotent attempts and confirmed or uncertain outcomes |
| `belive/whatsapp.py`, `belive/whatsapp_ai.py`, `belive/whatsapp_channel.py` | Passive WhatsApp conversation, photo/research agents, staff-guidance relay, company contact link and observed connection/delivery status |
| `belive/whatsapp_triage.py` | Native complaint assessment, exact customer-message evidence and deterministic SIMPLE-only substantive-reply policy |
| `belive/company_sop.py` | Reviewed source documents, page-grounded SOP selection and cited evidence |
| `belive/shared_memory.py`, `belive/repository_memory.py` | Approved general knowledge, revocation and privately transferred encrypted backup |
| `belive/experience_learning.py`, `belive/reply_learning.py` | Approved case-experience comparison, customer-reaction review, proposed tips and later reuse evidence |
| `assets/app.js`, `index.html` | Tenant-only operator dashboard, review dialogs, records, outbox, memory and reports |
| `portal.html`, `assets/portal.js` | Local tenant access, scoped conversations, tenant replies and resolution feedback |
| `tenant-site.html`, `assets/tenant-site.js`, `assets/tenant-site.css`, `assets/tenant-home.svg` | Separate BeLive tenant website with complaint, tracking and support-topic links |

Normal configured generation uses the real model. Test doubles live in automated tests. The explicit local WhatsApp simulator uses the same support workflow with labelled fictional intake and never calls Meta. Missing configuration produces an honest failure or staff handover; simulation is not live delivery.

## Current support workflow

The public and private entry points share saved complaint tickets, reviewed knowledge and staff handling. Draft generation never sends a public message. An operator reviews the draft and uses **Send reply** for an eligible exact platform target. Automated tests mock platform publishing and retain local previews. The primary reactive customer channel is WhatsApp. A working contact link, configured API fields and a successful local simulator are three different states; none alone proves that a customer received a WhatsApp reply.

The complaint workflow's Analysis Agent identifies COMPLAINT/ENQUIRY/NON_SUPPORT, relevance, topic, LOW/MEDIUM/HIGH/CRITICAL, exact evidence and uncertainty. The UI presents SIMPLE/MODERATE/HIGH. Uncertainty, handover or a human-required action cannot become SIMPLE merely because a model returns LOW. Physical/account/financial actions have a deterministic staff floor. Immediate danger is screened before normal troubleshooting. The fresh native rehearsal recorded SIMPLE, MODERATE and HIGH outputs with exact evidence and explained routes; the MODERATE/HIGH substantive assistance remained private while customer output was an acknowledgement. The sending records are explicitly SIMULATED. Current evidence and regression-test freshness are tracked in [FRIDAY_DEMO_CHECKLIST.md](FRIDAY_DEMO_CHECKLIST.md). Do not infer that an earlier OTHER / UNASSESSED ticket had already passed that check.

Only supported SIMPLE substantive replies may be automatic. MODERATE can receive AI assessment and assistance while staff retains review and operational decisions. HIGH requires staff priority. Acknowledgement, safe requests for missing details and relaying verified staff instructions are different from approving a repair, financial action or permission. Unknown facts and failed checks require staff; the model must not invent policy, fault findings or completed work.

`belive/routing.py` holds category destinations supplied and approved by administrators. The model identifies category; deterministic routing selects the saved destination. Blank categories use Support team. A local STAFF_ALERT or work-order entry is not proof that an external notification was delivered or a contractor was dispatched.

Current production roles execute through official native Hermes `run_agent.AIAgent`. OpenAI GPT-6 Luna is the model provider. The explicit direct engine is legacy regression transport, never an automatic fallback for missing Hermes. Executions record native class, version/commit, model-call count and actual tool names. Staff decisions and delivery remain application operations outside the Agent tool allowlist.

## WhatsApp assessment and reply handling

Real signed webhooks and the explicit local simulator call the same `process_thread` workflow. After safe photo observations, a native **Complaint Analysis Agent** returns complaint/enquiry/non-support, category, severity, summary, level reason, uncertainty and the index of an actual customer message. The application extracts that exact message as evidence and validates every allowed value. The ticket saves the analysis, category, severity and deterministic `staff_destination`. The conversation UI shows the decision, category, SIMPLE/MODERATE/HIGH, **Why this level** and **Staff destination**.

A supported SIMPLE response can be automatic after the existing evidence/safety review. MODERATE/HIGH substantive AI assistance is retained as `staff_draft`; the customer receives an acknowledgement and staff receives the request. Expanded activity labels it **AI assistance · staff review required** with **Draft evidence**. Staff can read/edit/check the operational guidance. When the latest message is a verified internal staff solution, Hermes may relay that guidance after review; this does not authorise unrelated new commitments. The actual relayed reply is retained as the case draft so later reviewed learning can trace the real wording.

Queued WhatsApp replies store the case revision. Delivery rechecks the current case revision, status and SIMPLE-only rule before and after shared-knowledge synchronisation; staff edits, escalation or closure suppress an old reply. Withdrawal of cited knowledge also prevents delivery. When the shared library is disabled, the application fingerprints the approved local tips and experiences supplied to generation, then rechecks them before saving or sending a draft. Revoked or corrected examples invalidate the old output; urgent deterministic acknowledgements carry no unrelated learning dependency. Work-order notifications use BeLive's configured Maintenance destination.

Immediate danger bypasses normal retrieval/reply generation and creates an urgent safety acknowledgement plus staff handling. Text danger is screened before shared-knowledge synchronisation; the deterministic acknowledgement has no unused SOP or lesson dependencies, so unrelated shared-memory unavailability does not hold it. The deterministic screen is not an AI agent/model-call result. An invalid/failed assessment becomes uncertain MODERATE staff handling and never a silent SIMPLE fallback. Existing in-flight case/knowledge revision checks, duplicate protection and separate simulated delivery are preserved.

## Reviewed learning and memory

`belive/experience_learning.py` compares the same actual question without and with a relevant current approved case experience or reviewed writing improvement. The operator inspects the matched source before generating the second reply. No match means no invented default lesson. Outputs retain the original question, source and actual model text. Compare relevance, supported facts, useful next steps and repetition; a changed answer is not proof of improvement.

Completed cases can contribute redacted general wording after staff review. Current approval/correction permits reuse; rejection, reopening or withdrawal revokes it. Company SOP stays separate from learned writing examples. A prior answer never becomes verified company policy merely because it was approved as useful wording.

`belive/reply_learning.py` links a customer follow-up to the actual preceding reply. Semantic analysis distinguishes dissatisfaction, appreciation, neutral follow-up and uncertainty, and separates communication problems from service action still needed. Proposed tips require staff approval and safety checks before later reuse. Usage counts and subsequent reactions are observations, not an automatic customer-satisfaction score or proof of causality.

Approved writing guidance is projected into isolated official Hermes MemoryStore. Current SOP and general complaint experience are supplied by the bounded evidence tool. A native memory count of zero does not mean no company evidence was retrieved; inspect the actual tool execution and source citations. Reuse is retrieval-based learning, not model-weight retraining.

The encrypted knowledge archive transfers reviewed SOP, general experiences/tips and reviewed source documents only through authorised private exchange. Source-code publication and Git pull do not carry knowledge. The local runtime path remains `knowledge/team-memory.enc.json`, but the archive and recovery key must never enter GitHub. The recipient places the private archive at that path before importing the matching key through Team knowledge backup. It excludes conversations, API keys and unreviewed customer feedback. Local conflicts and revocations are preserved; this is manual transfer, not live synchronisation. See [private knowledge transfer](SHARED_MEMORY.md).

Older formatting-only comparisons remain under **Legacy demo writing tips**. Their numbered-point and word-count checks are historical style exercises, not the current support-quality metric. The fictional demo preparation remains available for isolated tests and does not establish actual tenancy, company policy or a shared administrator password.

Staff navigation contains Command center, Complaints, Public reviews, WhatsApp inbox and Self-learning; advanced functions remain under System setup. The current operating guide is [FYP_DEMO_GUIDE.md](FYP_DEMO_GUIDE.md).

## Tenant website entry and internal complaints

`GET /belive` serves the public contact website; staff use `/`. The configured company WhatsApp entry opens the approved number with a short topic message. Opening the link sends nothing and creates no complaint ticket. Customers send their message and continue support in WhatsApp. The website identifies whether automatic replies have actually been verified instead of presenting a contact link as a connected AI channel.

Signed Meta inbound messages create a scoped WhatsApp thread and ticket. The local **Test a conversation safely** path is explicitly simulated and never sends through Meta, even if credentials exist. Customer photos are private support inputs. SOP, photos, web pages and messages are untrusted data; the Agent receives only allowed evidence and tools. Different senders use isolated conversation profiles. Staff can enter checked internal guidance; Hermes adapts it into a reply for the same conversation.

The retained website complaint form creates a private browser-scoped conversation without requiring a customer-entered portal key or Complaint Code. **Track complaint** in the submitting browser shows its messages and outcome controls. The application still uses private session credentials internally; retiring key-entry fields does not remove customer isolation. Staff links require login. Historical verified-tenant integrations and demo sessions remain distinct from ordinary browser intake.

For Google, Facebook and Threads, the Complaint Analysis Agent runs before matching approved public guidance. Every eligible confirmed SIMPLE, MODERATE or HIGH public complaint receives an automatic draft from the separate Public Reply Preview Agent. The SIMPLE-only rule governs the legacy internal selection of approved substantive guidance; it does not restrict public drafting to SIMPLE or authorise posting. MODERATE/HIGH retain staff responsibility, while the public draft can acknowledge the issue, gather useful details or present safe assistance for operator review. The reply agent uses the source report, assessment summary and recorded public follow-ups. It has no mandatory thanking opener, first-sentence truncation or fixed contact footer. A fault draft can ask for a missing error code, exact brand/model or observable symptom instead of merely telling the customer to contact staff. It acknowledges prior unsuccessful reports and avoids asking for details already supplied. Public replies remain local drafts until an operator deliberately sends them.

Staff can record an observed customer reply against the selected public case, optionally with its same-platform source link. This is an explicitly recorded follow-up, not automatic identity matching, a verified tenancy or proof that an earlier draft was posted. Intake is revision-checked, idempotent and auditable; the original source snapshot is unchanged. New danger in a follow-up keeps urgent staff handling. The next draft uses the latest recorded details. Google review edits and new Facebook/Threads comments are not silently treated as the original customer's answer.

For appliance/router faults, a conditional Public Diagnostic Details Agent extracts only literally supplied brand/model/code (or an explicit report of no code). Missing manufacturer details require clarification without a search. A bounded generic lookup then reuses the existing native Hermes Official Source Research Agent and its allowlisted search_official_support tool. Queries contain device details, not customer records. Only matching permitted manufacturer HTTPS citations with model/code evidence can support a draft, and a separate Public Diagnostic Safety Agent must confirm grounding, model compatibility, safety and no uncertainty. Routine research is skipped for HIGH/danger. Missing or incompatible sources produce clarification rather than an invented fix. Internal/electrical repair, interlock bypass, promises of staff work and claims of resolution are excluded. Sources are retained beside the local draft. This reuses the shared research mechanism without calling the WhatsApp delivery workflow.

Saved public previews carry a format version and fingerprint of their actual inputs. Source, category, level, assessment-summary or follow-up changes mark the earlier draft outdated. Eligible confirmed public complaints are queued for drafting after assessment; existing cases can obtain a missing or outdated draft through the same background coordinator. Repeated status refreshes do not start duplicate generation for unchanged inputs. The case displays the observed drafting state. A failed or stale run retains the earlier artifact and never overwrites a newer case decision. Full-body validation applies at every complaint level, including later sentences, private information and unsupported repair/refund/dispatch claims. Automatic drafting does not approve publication, alter severity or remove staff handling.

### Send a reviewed public reply

The public case shows the draft, original-source link and intended destination. Staff can edit the reply before selecting **Send reply**. That click approves the exact displayed text for the selected current case; there is no automatic social posting and no separate model publishing tool. The server rechecks the case revision, saved preview freshness, authorised source and platform target. Manual or browser-only identifiers cannot be substituted for an official API target.

| Platform | Exact destination and prerequisites |
|---|---|
| Google | The original `accounts/.../locations/.../reviews/...` resource from an authorised Business Profile API source. A Maps listing or review Share link alone cannot enable direct replies. Company access, a verified location and the locally enabled Google reply connection are required. |
| Facebook | A comment on the captured Page post, or a reply under the captured comment, using that exact object ID and an authorised Page token. The action does not create a new Page feed post or choose a different complaint. |
| Threads | A text reply with `reply_to_id` set to the captured complaint/reply ID. The media container and publish receipt remain linked to that attempt. It does not create an unrelated top-level post or reply to the root post instead of the selected item. |

`POST /api/public-reply` receives the case ID, revision, exact text and the operator's confirmation, with an idempotency key. The saved `public_reply` records the target, attempt and observed outcome. `POSTED` requires a platform receipt; a configured token or successful read is not publishing proof. `PENDING` is a platform operation still awaiting completion. `SENDING` or `UNKNOWN` does not permit a blind duplicate send. Inspect an unconfirmed result on the original platform before reconciling it. Publishing a reply leaves the complaint's severity and operational staff route intact.

Platform access remains specific to the authorised account and resource. Facebook comment publishing requires a Page token with the appropriate Page task and `pages_manage_engagement`; read-only access is insufficient. Threads reply creation uses the official reply container/publish workflow and needs the current account's applicable publishing/reply permissions. Google review replies need the Business Profile OAuth scope and a verified location. The application must report rejection or unavailable access honestly, rather than changing platforms or claiming delivery. See [Meta comments](https://developers.facebook.com/docs/graph-api/reference/object/comments/), [Meta's Threads reply example](https://www.postman.com/meta/threads/request/34203612-7abb4419-a216-4e06-8027-f9f4fcf8bee9), [Threads authorisation](https://www.postman.com/meta/threads/documentation/dht3nzz/threads-api) and [Google review replies](https://developers.google.com/my-business/reference/rest/v4/accounts.locations.reviews/updateReply).

Tenant feedback records what the customer reports. It does not independently verify a repair or close a physical issue. **Still unresolved** records feedback and requests/reopens staff handling. Staff checks outcome evidence before a verified closure. A local or mocked test does not establish actual public posting or production Internet hosting.

## Flowchart traceability

| Diagram step | Current implementation | Practical boundary |
|---|---|---|
| External monitoring and relevance | Selected source API reads, persisted versions, native AI triage | Google/Facebook and selected Threads posts read up to 25 recent text entries. Threads account monitoring checks up to 25 recent parent posts and up to 25 top-level replies per parent, importing at most 25 new or changed replies per run. Live APIs need credentials/access; these bounds do not provide complete history. |
| Deduplication and public reply | Stable source IDs/content versions, background draft preparation and one operator-approved Send action for the exact source | Drafting does not publish. Sending requires current source identity, platform access, revision checks, duplicate protection and a stored outcome; public text does not verify tenancy |
| Internal/private intake | Signed WhatsApp messages, explicit local simulator and retained browser-scoped complaint form | Simulator is QA only; individual tenancy/account decisions require appropriate verified records |
| High-risk branch | Deterministic early screen, AI high-risk validation, staff queue and acknowledgement timer | Keyword screen is not exhaustive; staff alerts remain visible locally and require approval/configured gateway for external delivery |
| Hermes investigation | Triage plus investigation/response, matching tenant records, verified house rules and recent tenant updates | Records are staff assertions; no assumed external property integration or live account/payment actions |
| Resolution/action plan | Reviewed response, staff work orders, department destination | AI cannot approve refunds, alter access or mark repairs completed |
| Human acknowledgement / escalation | Staff ownership, acknowledgement deadline, backup then management queue | Default times are configurable prototype settings, not BeLive SLA |
| Customer follow-up / reassessment | Due reminders, tenant updates and unresolved handover | Queued reminders are not delivered proof; inactive-customer closures are labelled unconfirmed and are not learning sources |
| Verified closure | Follow-up, recorded evidence/confirmation, no open work orders | Operator verification is not independent proof of repair |
| Validated learning | Reviewed general case experience and writing feedback, source trace, latest verdict, revoke on rejection/reopen, stale-run discard | Knowledge reuse and reviewed writing adaptation; no model retraining or verified-policy promotion from a past reply |
| Shared memory / management | Reviewed general memory, privately exchanged archive, conflict/revocation handling, reports and audit | Code-only updates do not carry knowledge; both archive and recovery key stay private |

## Case states

Internal intake begins at `AI_PENDING`; an external unverified case begins at `AWAITING_CONTACT`. Immediate risk or instruction-like input goes to `HUMAN_REVIEW` before routine generation. AI failure, uncertain relevance, high urgency or a human-required plan also enters human review. A valid low-risk assessment saves a draft without sending. An open staff case shows background assessment progress and updates when the result is ready, while leaving unsaved staff input alone. Valid non-support input becomes `SKIPPED`.

Staff acknowledgement records ownership and enters `IN_PROGRESS`. An action note starts `FOLLOW_UP`. Staff can reassess an unresolved case into human review. Verified closure requires staff ownership, explicit checked outcome evidence and no open work orders. Public/WhatsApp cases do not require a customer-entered portal key or Complaint Code to close. Customer-reported resolution alone is not staff verification. Reopening closed/skipped cases routes to staff and revokes old learning. A tenant update containing a detected safety risk escalates immediately.

Case actions use revision checks. AI runs outside the state transaction, then discards its result if the case, public conversation, verified support context/property version or reviewed example set changed. Current approved/corrected styles are projected into the isolated native MemoryStore before each generation. Rejected entries may remain on disk until the next projection but are excluded from retrieval immediately and cannot be used by the next agent run.

## AI evidence and diagnostics

Triage evidence must be an exact, case-sensitive, bounded quote from the tenant's complaint **title or description**. The application records the matching `evidence_field` itself and displays it beside the quote; this identifies a tenant report, not a verified repair finding. Paraphrases, invented quotes and excerpts found only in support records or conversations are rejected. This fixes a false rejection where the model quoted a valid title while the validator previously checked only the description.

Failed analysis jobs preserve fixed, allowlisted error codes (for example `AI_UNGROUNDED_EVIDENCE`, `AI_INVALID_SCHEMA` or `HERMES_TIMEOUT`), with a plain-language explanation on the staff case. Unexpected errors retain the generic `AI_FAILED_OR_INVALID` fallback. Raw provider exceptions, credentials and response bodies are never copied into case errors or audit events. Failures still go to staff; no response is published or repair claimed. A successful operator-triggered retry replaces the old failure explanation with its current assessment or human-handover reason, while previous failed jobs remain in the audit history. Validation failures are not automatically retried.

## Timers, delivery and failure

While the launcher runs, a 30-second loop checks pending AI, due acknowledgements/follow-ups and configured sources. Source scans run no more often than their persisted 15-minute schedule; an operator can request a bounded scan manually. Saving an authorised source starts its checks by default. Existing paused sources remain paused across restarts. Operators can pause/resume checks for an individual source; there is no server-enable setting. Background tasks are deduplicated per case/source.

### Threads account monitoring

In **Public reviews → Configure platform sources**, choosing Threads monitors the connected account. The form submits `me/threads`; the server reads the saved Threads user's API identity and saves the exact numeric `USER_ID/threads` resource. The saved source is therefore pinned to the authorised account. The operator does not need to paste a new post ID whenever that account publishes another post. The retained `POST_ID/replies` resource continues to support an explicitly selected single post.

Every manual or scheduled account check discovers up to 25 recent parent posts from that account and reads up to 25 top-level replies under each parent. Only reply text becomes complaint intake; the parent post is discovery context. A run imports at most 25 new or changed reply versions. Remaining discovered reply versions are deferred for a later check, and the interface distinguishes discovered items, new cases and deferred work. Repeating a check does not create another case for the same source ID and text. An edited reply remains an immutable new source version. These bounded reads do not search the whole Threads platform, paginate complete history or guarantee that every old reply will be recovered. The local server must remain running for scheduled checks.

The connector sends read-only requests to the fixed official `https://graph.threads.com` host with the saved token in the Bearer header. Redirects remain blocked. Tokens stay in the private encrypted connection settings or local environment fallback and do not enter public source-code exports. API-provided reply permalinks and timestamps are retained as source provenance; the app does not manufacture a review/post URL from a share code.

Collected replies enter the existing complaint queue and native Hermes assessment workflow. This addition changes collection scope, not the SIMPLE/MODERATE/HIGH rules, staff approval or model execution engine. Public responses remain drafts or previews during testing; a successful read, a collected case or a saved response does not establish that a reply was sent on Threads.

The prototype defaults are 30 minutes for acknowledgement and 24 hours for follow-up. Two acknowledgement escalations target backup support and then management. Two recorded follow-up cycles return an unanswered case to staff. These timers record queued attempts, not confirmed customer contact. Timers never approve a message or claim a repair. The separate configurable inactivity policy can close a case waiting for a customer reply after seven days by default, recording an unconfirmed outcome rather than verified resolution.

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

In review mode, publishing to the retained private complaint conversation is an explicit operator action on the saved response. Optional routine automation uses the approved-knowledge gate described below. Staff publication requires an active case and confirmation that the exact wording was reviewed. Account/tenancy-specific claims require appropriate verified context; a customer-entered key or Complaint Code is not a general sending or closure gate. Automatic publication follows the EXACT or GUIDANCE controls below. Identical published wording is deduplicated per case. It creates a real local portal message and does not claim email/social/gateway delivery. Drafts, analysis, citations, work orders and internal notes remain private.

The portal returns only the current tenant's public conversation. Tenant updates are persisted and included in future AI context. Outcome feedback records the tenant's assertion; it does not verify or close the case. An unresolved outcome can reopen a closed case and revoke its previous style example. Safety flags in an update or outcome feedback override routine processing and require critical staff handling, even if the tenant selected resolved.

Acknowledgement records the signed-in operator name. Operators can record a manual category/urgency assessment, private note and future action deadline. Detected safety flags cannot be downgraded through that assessment. The queue places active critical cases first, then overdue work and remaining urgency/deadline order. Closure clears the active due-state display. Default timers are still prototype settings, not claimed BeLive SLAs.

## Versioned support context

Support records carry a version, active state, optional expiry, source reference and correction reason. A correction requires source verification and the expected current version; deactivation stops future AI retrieval. Every version is retained in `record_history`, with database triggers prohibiting history updates/deletions. Property guidance also retains versions. Legacy records are treated as version 1 and acquire history on their next edit.

AI context contains only the matching tenant's current active, unexpired verified support records. Saved citations capture the exact ID/version/source/text used. A context change during generation discards the result. Historical citations remain evidence of what was used at the time and do not establish that the guidance is still current; operators must review before publication.

## Operator access and revocation

First-run setup creates one local administrator using the chosen password; it is disabled after an account exists. Passwords are salted PBKDF2-HMAC-SHA256 hashes with 600,000 iterations, following the algorithm/work-factor guidance in [OWASP Password Storage](https://cheatsheetseries.owasp.org/cheatsheets/Password_Storage_Cheat_Sheet.html). The API never returns password hashes in its snapshots or user list. Login failures are throttled after five attempts for the same username.

An operator session lasts eight hours; the browser cookie is HttpOnly and SameSite=Strict, and only a hash of the random session secret is stored. Logout/deactivation revokes sessions. Support accounts can handle cases and reviewed responses. Admins manage accounts, verified records, source configuration, AI connection checks, memory projection and database recovery. Both roles can read operational case context; this is a small support-team permission model, not property-by-property access control. Password recovery/MFA, external identity providers and public TLS hosting are outside this local implementation.

Ordinary website complaint access uses a private scoped browser session; old customer-entered tenant keys and Complaint Codes are retired from that workflow. Historical verified-tenant credentials remain separate. Staff deactivation and session expiry are checked on subsequent requests; hidden controls are not the authorisation boundary.

## Consistent backups and recovery

Backup uses the [SQLite connection backup API](https://docs.python.org/3/library/sqlite3.html#sqlite3.Connection.backup), verifies integrity and records a checksum. Files are created with unique names and existing files are not overwritten. Recovery validates the saved checksum and schema, then creates a separate database for the next launch. The active database stays intact.

The recovered copy revokes staff and customer browser sessions, pauses source reads, holds outstanding gateway messages, clears due timers, routes active cases to staff, deactivates recovered support context and appends rejection verdicts for recovered style examples. Property guidance is marked for revalidation. This prevents an older snapshot from silently re-enabling a subsequently rejected example or replaying old external actions. Restored account credentials are those present in the backup. Source/audit/history evidence is retained.

## Code-only update and private knowledge migration

Before pulling the version that removes the formerly tracked knowledge archive, export reviewed knowledge and copy both archive and matching recovery key outside the checkout. Preserve the installation's `.env`, data/database, documents and separate credential key. After pulling code, place the private archive back at `knowledge/team-memory.enc.json`, then restore via Team knowledge backup. Key-only import cannot restore an absent archive; a fresh installation without an archive starts empty. Later reviewed changes require a new private export/transfer, not a code pull. The [transfer guide](SHARED_MEMORY.md) provides the exact order.

## Private connection settings

Administrators manage model and optional platform settings under **System setup → AI & knowledge → Connection settings**. Database overrides are authenticated-encrypted in the dedicated `private_credentials` table using AES-256-GCM; the separate `.belive-credentials.key` beside that database is local private configuration. APIs, support snapshots, audit and knowledge-only export return no secret values. Secret inputs remain blank and configured/source status is shown instead. Existing `.env` values remain field-level fallback until explicit stored overrides are saved. No environment key is silently migrated.

Changes require idle background work. Native Hermes remains the executor when changing models. Missing/authentication-failed credential keys lock the stored configuration rather than silently reverting to an older token. Full private database backups contain encrypted values but not the separate key; restoration needs that key privately or fresh credential entry. The team SOP recovery key does not unlock credentials. See [CREDENTIAL_SETTINGS.md](CREDENTIAL_SETTINGS.md).

## Real connection checks and evaluation

The admin connection test runs the official native Hermes AIAgent with the configured GPT model and neutral context. The native engine is independent of the model provider: a GPT model name never bypasses Hermes. The dashboard records native class, version, API-call count and tool execution separately from the model name. Approved style guidance is loaded through official Hermes MemoryStore; current SOP and complaint experience are retrieved through bounded evidence tools. Missing or failed native execution never silently falls back to direct model calls. See NATIVE_HERMES.md for installation, memory isolation and the explicitly labelled legacy transport used only by regression tests.

`evals/tenant_support.json` contains 24 clearly fictional English/Malay/Chinese cases. `scripts/evaluate_ai.py` makes no provider calls unless explicitly invoked with `--run-live`. Live evaluation uses a temporary database, captures schema/category/handover results and requires human review for factual and language quality. It does not insert examples into the normal workflow or claim a measured score without a run.

## Scope correction and existing data

Move scheduling, move completion and PIC availability commands have been removed. The command allowlist rejects those actions before reading cached idempotency results, so a legacy successful request cannot reactivate them. The dashboard/portal no longer return move arrangements or PIC availability. Property records retain only identity and verified support guidance in the current API.

Existing arrangement objects and append-only activity are retained for history. Legacy move notices are excluded from the active outbox and cannot be approved or sent, even by direct delivery requests. Scheduling-specific property rules are excluded from AI context until staff records current support guidance. The removed `MOVE_IN_OUT` category is rejected in new AI output; historical category values display as `OTHER` and their old examples are excluded from reuse. A restart is required to replace an already running older server.

## Validation status

The current regression suite passed **297 tests**, zero failures, errors or skips. Headless support, knowledge, settings, complaint and learning checks passed. Detailed execution records and identifying screenshots remain private. The public [rehearsal checklist](FRIDAY_DEMO_CHECKLIST.md) and [results/methodology checklist](CHAPTER5_EVIDENCE.md) contain non-identifying counts and limits.

Three simulated support-policy scenarios recorded 15 genuine native calls with SIMPLE/MODERATE/HIGH and sending gates passing. A separate isolated rehearsal recorded 35 calls: 27 across reviewed completed-case learning, six for a synthetic photo and two for bounded official research. A later matching reply cited the newly approved general lesson. Staff facts/outcomes were scripted, baseline and lesson-assisted answers were both useful, and no satisfaction or overall improvement score is claimed.

Headless signed-out public collection read two distinct low-rated written reviews with duplicate-input protection. Separate native analysis/preview roles used four calls and produced a MODERATE staff-handling result plus tailored preview. Public publication stayed disabled and no customer message was sent. Original links, text, source hashes and local identifiers remain in restricted evidence.

The public rehearsal supports a permitted individual `--review-url`, optional matching immutable fallback, empty installations and honest BLOCKED results without invented content. Active-database model settings are used in memory; secrets are not copied into the isolated credentials table or report. Current connection testing passed through native Hermes/GPT-6 Luna, with direct Decisions off. This is separate from live platform permissions or delivery.

Real WhatsApp, scheduled company platform reads and external staff notification delivery remain unverified until their authorised acceptance checks pass. Historical models, test doubles and formatting-only comparisons must not be presented as current quality evidence. Reviewed reuse is retrieval-based learning, not model-weight training.

## Property knowledge and optional routine automation

See [the setup and operating guide](AI_KNOWLEDGE_AND_AUTOMATION.md). Admins approve versioned, property-scoped informational answers with language, source and optional expiry. Both reviewed AI drafts and optional routine automation retrieve relevant current knowledge. Knowledge is verified context, not response-style memory or model retraining.

Automation defaults off for existing databases and affects only new private tenant requests after enablement. It uses the existing grouped native Hermes stages. The model selects an approved answer with confidence, request language and case evidence. Deterministic gates require a certain, supported response matching the verified tenant's property and language. EXACT knowledge preserves approved wording and requires LOW urgency. GUIDANCE knowledge supports automatic adapted information or safe clarification only at LOW (SIMPLE) urgency; MEDIUM (MODERATE) assistance is held for staff review, only after a separate native Hermes groundedness/safety review passes and the selected guide is cited. HIGH/CRITICAL, uncertainty, failed review and human-required actions cannot publish automatically. The reviewer is an additional safeguard, not a correctness guarantee. It rechecks case, record, policy and knowledge versions inside the commit transaction.

Portal follow-ups schedule a fresh assessment automatically. A maximum of three automatic answers prevents endless loops. Explicit human requests, failed answers, missing knowledge, policy/record uncertainty, dangerous content and unsupported actions go to staff. Handover creates a private portal receipt and the existing local staff alert, without claiming external delivery or staff acknowledgement.

The ANSWERED state means a tenant accepted an informational answer. It is separate from CLOSED, physical repair completion and verified-closure metrics. Unresolved feedback reopens staff handling. Customer-facing follow-up cases now close after 7 days without a reply by default, with an unconfirmed inactivity reason rather than a verified resolution. This does not create learning examples, and the customer can reopen the case from Track complaint in the submitting browser. Automatic check-ins remain private portal messages. Recovery pauses automation and deactivates knowledge pending review. No live company facts or automatic public/external messages were seeded or sent by this change.

## Tenant feedback visibility and fresh requests

The portal displays plain-language case status and an explanation beside each conversation. A pending automatic assessment is identified separately from a saved request awaiting staff review. Choosing Still unresolved saves the entered note and requests staff handling; it does not start another automatic FAQ cycle. Confirmation and errors appear beside the clicked controls and move into view. Subsequent tenant messages remain visible to staff while the case awaits review.

If a response is lost after the server commits a tenant update, the portal retains the text and reuses the same idempotency key for an unchanged retry. A new private request after ANSWERED, CLOSED or SKIPPED receives a new case instead of inheriting that old outcome. Replays of the original submission, active duplicate protection and stable public-source identity remain unchanged.

Demo knowledge may include low-risk device-side Wi-Fi checks based on a named public technical source. It remains scoped to the fictional demo property and does not establish BeLive equipment instructions, permission to alter shared equipment, an outage diagnosis or a repair result. Missing approved knowledge and physical-action requests continue to require staff.

## Demonstration fixtures and reports

The optional fictional demo property contains informational knowledge across tenant-support categories and languages. Demo preparation does not replace normal records or claim those entries are company-approved property facts. Use a fresh labelled test customer for each independent scenario. Tests and real-model rehearsals must identify simulated staff arrangements and tenant outcomes explicitly.

Support reports count saved actions and outcomes, including staff replies, AI drafts sent unchanged, reopened cases, handovers and checked closures. The alert button exposes urgent, overdue and unassigned staff-review cases. Operators can filter to their own assignments; administrators can inspect the wider queue. Count definitions must distinguish queued messages, accepted delivery and confirmed receipts, and separate customer claims from verified outcomes.

Before/after comparisons preserve the same question. Review usefulness and factual grounding directly. Only show numerical scores that were actually defined and measured by that test; there is no automatic general support-quality or satisfaction score. A solved-case learning demonstration must show the actual source reply, review, saved lesson and later matching retrieval/citation. The model stays the same.

The current demo model is hosted GPT-6 Luna through the native Hermes executor. The local Ollama transport is a preserved alternative, not the currently measured setup.

## Decisions triage and customer reactions

The explicit legacy direct transport can use /v1/decisions for message type, topic and severity when BELIVE_DECISIONS_ENABLED=true with OpenAI gpt-6-luna. Native Hermes mode deliberately disables that direct Decisions path; the production classification must run through AIAgent. It stores the returned option probabilities and the selected criteria alongside source evidence. A selected-option probability below 0.85 or a margin below 0.20 marks the assessment uncertain. These initial prototype thresholds need broader calibration. Uncertain, invalid or unavailable assessments go to staff. Immediate danger, the MODERATE staff floor, approved knowledge checks and SIMPLE-only publication gates still apply. The response and safety agents use normal model generation.

New post-reply messages are queued for semantic reaction analysis. Luna checks the original question, the published reply and the follow-up for dissatisfaction, appreciation, a neutral follow-up or uncertainty. It records the apparent tone and distinguishes a communication problem from service work still needing action. Positive or neutral observations contribute to outcome counts without creating a writing lesson. Staff review proposed tips and the safety agent checks them before reuse. The Self-learning screen shows the source conversation, tone, diagnosis, reviewed tip, reuse count and subsequent positive or dissatisfied reactions. Those counts describe observed customer responses. This process does not train the model weights.
