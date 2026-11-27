# Private Customer Support · official WhatsApp

## HTTPS authorisation entry

`scripts/whatsapp_https.py` serves a separate loopback listener (8878), intended for an approved HTTPS tunnel. It exposes only `/connect/*` onboarding assets/operations and the signed `/webhooks/whatsapp` proxy to localhost 8877. Unknown paths, dashboard APIs, files and documents are denied. HTTPS origin and verification token live in ignored `data/whatsapp-https.json`; verified account credentials live in ignored `data/whatsapp-credentials.json`. Keep both private.

In Meta's Facebook Login for Business settings, add the actual HTTPS origin to Allowed Domains for the JavaScript SDK, and its `/connect/whatsapp` URL to Valid OAuth Redirect URIs. Use the company App ID, Embedded Signup Configuration ID, Graph API version and App Secret in local `.env`. A Configuration ID is not an access token or a verified connection.

An administrator uses **Customer Support → Company connection checklist → Connect company WhatsApp with Meta** to generate a private, single-use, 30-minute setup link. HTTPS setup uses a Secure/HttpOnly cookie, same-origin/CSRF validation and exact Facebook message-origin checks. The authorization code is exchanged server-side, with app/permission checks; assets are verified against the approved public number. Existing-mobile-app onboarding is required, phone registration/deletion is never performed, and only that verified phone receives a webhook override. Existing app-wide and account webhook configurations are retained. Meta permissions/approval and a real customer message/delivery receipt remain required for live readiness.

Quick Tunnel addresses are temporary and change when the tunnel restarts. Keep the local server and tunnel running during testing, update Meta's allowlists if the hostname changes, and use a stable company-approved HTTPS endpoint for production. The tunnel must target 8878, never the dashboard port. Tokens are never written to source, logs, browser status or the encrypted knowledge export.


Official native Hermes `run_agent.AIAgent` executes the workflow with the configured GPT model. The website is the internal staff dashboard and contact entry. Once authorised live delivery is verified, customers receive support in the same WhatsApp chat; they should not need a website form to receive the reply.

## Contact entry and real connection

An administrator saves an approved public company number in **WhatsApp inbox → Tenant Report website entry**. The public contact website opens that configured chat with a short topic message. Opening a link alone sends nothing and creates no ticket. Do not include private contact details or account credentials in public documentation.

A contact link, model check, configured API fields, simulated run and observed live delivery are distinct states. The interface should not call the channel connected until actual authorised incoming/reply/delivery evidence exists. Current local rehearsals did not establish real company WhatsApp delivery.

## Keep the Business phone app

A number already used in the mobile Business app needs supported coexistence onboarding if that app is retained. Do not delete/unregister the mobile account, invent verification information or repeat codes to bypass onboarding. App permissions and approved business/number access must come from an authorised administrator.

The integration supports signed message handling and mobile-message echoes. Staff echoes are context, not new customer complaints; matching AI echoes deduplicate and history does not create fresh tickets. Staff phone replies supersede pending AI drafts. The implementation does not grant platform approval or technically lock the phone app to read-only.

## Local QA

1. Open **WhatsApp inbox → Test a conversation safely — never sends to WhatsApp**.
2. Use a new fictional customer reference for an independent test. Reuse it only to continue that conversation.
3. Send a generic enquiry or support complaint; an optional permitted image can test observation.
4. Read Complaint/Enquiry, category, level, **Why this level**, exact evidence and **Staff destination**.
5. Expand **AI activity and sources** for real native roles, tools, approved citations and delivery state.
6. When staff is needed, read **AI asks staff**, enter checked guidance, confirm it and select **Ask AI to reply**. Fictional test arrangements must remain labelled fictional.

Select prepared labelled `friday-` conversations by topic when available. Local account/case identifiers differ on another installation. SIMULATED never calls Meta, including when live credentials exist.

## Assessment and sending rules

Signed webhooks and simulator intake share one support-processing path. A native Complaint Analysis Agent produces report type, category, level, summary, reason and uncertainty; the application validates them and extracts exact customer evidence. Deterministic routing selects the administrator-configured department, falling back to Support team when blank.

| Result | Customer output | Staff evidence |
|---|---|---|
| Supported SIMPLE | Checked substantive answer may be automatic. | Current citations and native execution. |
| MODERATE/HIGH or uncertainty | Acknowledgement. | Substantive `staff_draft` held for review. |
| Verified internal staff solution | Hermes may adapt and relay checked guidance after review. | Actual relayed wording retained for the case. |
| Immediate danger | Safety acknowledgement and urgent staff handling before routine AI. | Deterministic action, not a model-generated answer claim. |

Physical-action or explicit staff requests cannot become automatic SIMPLE just because the model returned LOW. Queued delivery rechecks current case revision/status, severity policy and cited knowledge; escalation, closure, staff edits or withdrawal suppress stale replies. Immediate danger is screened before unrelated knowledge synchronisation. Work-order notifications use the configured destination, and a queue entry does not prove delivery.

## Knowledge, photos and research

Code updates do not distribute approved company knowledge. Before pulling an older installation, privately preserve/export the archive and matching recovery key outside the checkout; retain your own `.env`, data/database and credential key. On the receiving computer, copy the privately supplied archive to `knowledge/team-memory.enc.json` before importing its matching key under **Self-learning → Team knowledge backup → Restore on another computer**. Confirm the actual restored records. Never upload the archive or key to GitHub. See [private knowledge transfer](SHARED_MEMORY.md).

The Agent retrieves relevant current approved knowledge and general reviewed experience. Staff decisions govern private policy and commitments; generic online information cannot override them. Ask only for details needed by the current issue and avoid repeating unsuccessful suggestions.

Photo observation records visible facts and uncertainty, without assuming equipment identity or diagnosing a fault. Native official-source research uses a bounded tool and allowed domains. Only generic technical queries enter public search; customer conversations and private company text must not. Unclear evidence, unsupported facts or failed checks request staff guidance.

After checked closure, staff can approve a redacted general lesson. Later matching replies show actual use. Customer dissatisfaction can prompt reviewed writing guidance but does not itself prove AI failure or a solved service problem. Rejection, reopening or source withdrawal revokes reuse. Learning is retrieval-based, not model training.

## Live setup requirements

Ask the authorised administrator for app/business/number access, Phone Number ID, permitted server token, App Secret, supported API version and a separate verify token. Enter secrets only under private **Connection settings → Platform API access → WhatsApp** or the ignored environment fallback. See [connection settings](CREDENTIAL_SETTINGS.md).

Real inbound messages need an authorised public HTTPS endpoint for `/webhooks/whatsapp` and the configured expected host. The local app remains loopback-only. Any proxy must expose only the webhook path, not the staff dashboard, API, media, configuration or database. Verify signatures, business phone ID, reply transport and signed delivery callbacks with an authorised test.

Free-text delivery is limited to the customer-service window. Outside it, this prototype records the template requirement rather than sending an unapproved template. Uncertain sends are UNKNOWN without automatic retry. Confirm external state before a deliberate retry to avoid duplicates.

## Measured results and limits

### One-click demonstration startup

Double-click **Run BeLive Prototype.bat**. Keep its status window open and the computer online. It checks/reuses the selected local BeLive database, the restricted WhatsApp HTTPS gateway and any working tunnel; if needed it starts them. A changed temporary tunnel is verified publicly before the launcher verifies the existing App, company number, coexistence and account subscription, then updates only that phone/account's callback overrides. It never changes the App-wide callback, registers a number or starts a new Embedded Signup. Saved authorisation is required; expired/revoked access or missing company permissions is reported, not bypassed.

In **Customer Support → Live connection · this startup**, BeLive, official native Hermes runtime, public HTTPS and Meta callback have separate checks. READY means these checks passed, not that a model answered a customer. The launcher checks the connection periodically and reconnects after failure. Old receipts remain historical; a real inbound message and delivered reply after this launch are needed for this startup's live-delivery confirmation. If the launcher stops, its status expires after 90 seconds. Duplicate launches do not create duplicate supervisors. Cloudflared must be installed or available locally at `output/tools/cloudflared.exe`; its binary and all runtime logs/credentials remain private.

Pure greeting conversations use a bounded short path: deterministic eligibility and risk checks, genuine native Hermes generation, then an independent native reply review. Greetings mixed with a question, photos, staff instructions, a pending staff request or an existing support issue retain the full support path. Signature verification, duplicate protection and delivery freshness checks remain mandatory.

Successful greeting workers remain warm for up to five idle minutes, with at most four cached customer/role profiles. Each request creates a fresh official AIAgent and reloads current approved memory; responses are never cached. Provider/key/tool changes invalidate that profile's worker. Execution records include elapsed time, queue time and worker reuse. Cold starts and provider latency still affect response time; measure live webhook-to-delivery separately from isolated rehearsals.

Three support-policy scenarios made 15 genuine native calls with SIMPLE/MODERATE/HIGH gates passing. Separate reviewed-learning, synthetic-photo and bounded-research phases made 27, six and two calls. Staff outcomes were scripted test activity; sends were simulated. No real tenant satisfaction, physical resolution or Meta delivery is claimed.

The full regression suite passed 297 tests with no failures/errors/skips; relevant headless checks passed. See [the operating guide](FYP_DEMO_GUIDE.md) and [rehearsal checklist](FRIDAY_DEMO_CHECKLIST.md). Keep detailed evidence and private company references outside public reports.

### Photo intake and independent device context

A signed image message is downloaded through Meta, validated and stored in the private media folder. The authenticated inbox shows a download state until photo_ready is true, then loads the preview while native vision runs. A missing preview returns a controlled unavailable response. No media URL, token or image bytes are exposed in the status snapshot.

The genuine Hermes Photo Agent records visible observations and tentative brand/model/code. The native assessor decides whether the customer explicitly linked an earlier device. Otherwise, the reply and reviewer receive the current photo context without older device identifiers or unrelated staff instructions; the other cases themselves remain unchanged. An explicitly linked device retains relevant history. Ambiguous characters such as E/F still require customer confirmation before code-specific guidance; clear typed corrections take priority. Missing brand/model does not block an official identification lookup using visible product-family badges and panel labels. Candidate matches remain tentative. If the customer cannot provide a label or clearer photo, Hermes should use the existing clues, ask a different useful symptom question, or pass the actual unresolved obstacle and checked sources to the responsible team instead of repeatedly requesting identification.

`tests/rehearse_photo_context.py IMAGE_PATH` is a manual real-Hermes/OpenAI rehearsal using simulated WhatsApp delivery. Run only with explicit permission for the deidentified test image. Results and source images stay private under ignored data paths.
