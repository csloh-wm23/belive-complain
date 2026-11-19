# Add knowledge and enable routine AI support

The configured model reads approved property knowledge when answering. This is retrieval from the local database, not model retraining. Keep actual tenancy/account facts in verified tenant records. Keep response-style feedback in Reviewed memory. These have different purposes.

## One-time setup

1. Sign in as Admin and open **Setup & knowledge**.
2. Find **AI knowledge & automatic replies**. Select an existing property.
3. Enter a topic or problem, category and language. Choose **Exact approved reply** for fixed wording, or **Reusable support guidance** for verified facts, safe steps and useful intake questions that the AI can adapt. Enter its source/version/reviewer. Add an expiry when the information needs rechecking. All eight tenant-support categories are supported; a category does not grant permission to perform real-world actions.
4. Check the verification box and choose **Save approved knowledge**. Repeat for each FAQ and each language you support. Use actual verified company guidance. Do not paste passwords, access codes, personal tenant details or unapproved policy promises.
5. Choose **Enable routine automation**. Your existing provider/model configuration remains in `.env`. Enablement requires a configured model and at least one active approved answer.

Knowledge remains useful for staff-reviewed AI drafts while automatic mode is off. Model configuration alone does not populate company knowledge. An empty knowledge base cannot reliably answer BeLive-specific questions.

## What happens without a staff click

For a **new private tenant request after enablement**, the backend screens risk, retrieves up to eight matching current answers for the verified property, then runs the native Hermes triage and investigation/response stages. The model must choose a directly applicable answer in the tenant's language with sufficient match confidence. The server validates the case, category, urgency, uncertainty, answer ID/version and current configuration again before publishing.

**Exact approved reply** entries preserve their reviewed wording and require low urgency. **Reusable support guidance** entries can support an adapted response for a suitable SIMPLE request only; MODERATE assistance remains a private staff-reviewed draft. The model must cite the selected guidance, preserve its facts, use the current conversation and ask only relevant clarifying questions. A separate native Hermes review checks groundedness, safety and uncertainty before publication. Missing or invalid review, unsupported claims, high urgency and human-required actions cause staff handover. A model review is an additional check, not a guarantee of correctness. The conversation labels the message **AI SUPPORT**, and the staff timeline records its knowledge version and message ID. A tenant follow-up automatically starts a new analysis for that turn without a Run AI or Publish click. Replays and concurrent stale results do not duplicate replies.

The tenant can select **This answers my question**. This records **Answer accepted** for the information request. It does not assert a repair happened, verify maintenance completion, count as staff-verified closure or add an automatically approved memory example. Portal check-ins follow the configured follow-up interval. Customer-facing follow-up cases now close after 7 days without a reply by default, rather than escalating merely for silence. This is an unconfirmed inactivity closure, excluded from verified-resolution metrics and learning. Customers can reopen through Track complaint in the submitting browser. See [daily handling steps](COMPLAINT_STEPS_ZH.md).

## When humans still act

The workflow remains AI-first with urgency-based prioritisation and staff handover if AI cannot resolve the request. Urgent danger, explicit staff requests, physical repairs, account/access changes, financial decisions, uncertainty, missing/expired knowledge, unmatched language, model failures, unresolved feedback and repeated automatic turns require staff. A handover receipt tells the tenant that the case is in the staff queue. It does not claim a person acknowledged it or promise a response time.

A Support operator can select **Take over as staff**, which stops automatic handling for that case. **Pause routine automation** stops future automatic publication. Correcting or deactivating knowledge prevents future reuse, including discarding results generated against an older version. Recovery disables automation and requires renewed knowledge review. No automatic public social reply or external gateway delivery was added.

Staff must initially verify tenancy, approve the support knowledge and maintain it. Maintenance personnel still perform actual repairs. After setup, a covered routine informational request can finish without staff handling. The system does not promise fully autonomous handling of every complaint.

## Verification

Automated tests use isolated fictional databases and explicit test-only AI. They cover property isolation, automatic first/follow-up replies, tenant acceptance, unresolved/danger handover, review mode, staff takeover, version changes during generation, model failure, reply limits and access control.

The separate live smoke check used the configured native Hermes/Ollama model with a fictional tenant and fictional approved FAQ. It produced an exact approved answer, then recorded tenant acceptance with zero staff case actions. This is a narrow connectivity and workflow test, not a general accuracy result, company integration test or production-readiness claim. Private reports stay in ignored `artifacts/`.


## Latest navigation and learning demonstration

Use the [simple test guide](FYP_DEMO_GUIDE.md) for the fictional tenant and before/after comparison. Admins can choose category destinations in Setup & knowledge. Normal reviewed styles are retrieved automatically after verified closure and approval/correction; latest rejection or reopening revokes reuse. The comparison automatically adopts only measured writing improvements for the fictional demo property. No model weights change, prior responses do not become company policy, and public social replies are not automatically published.
