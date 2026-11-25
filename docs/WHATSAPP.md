# Private WhatsApp support

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

Three support-policy scenarios made 15 genuine native calls with SIMPLE/MODERATE/HIGH gates passing. Separate reviewed-learning, synthetic-photo and bounded-research phases made 27, six and two calls. Staff outcomes were scripted test activity; sends were simulated. No real tenant satisfaction, physical resolution or Meta delivery is claimed.

The full regression suite passed 297 tests with no failures/errors/skips; relevant headless checks passed. See [the operating guide](FYP_DEMO_GUIDE.md) and [rehearsal checklist](FRIDAY_DEMO_CHECKLIST.md). Keep detailed evidence and private company references outside public reports.
