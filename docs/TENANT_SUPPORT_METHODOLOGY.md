# Proposal: AI-assisted tenant support for BeLive

## Objective and current scope

Connect tenant onboarding, rental-related enquiries, complaints, staff coordination and verified follow-up in one support workspace. Reduce repetitive information gathering and drafting while keeping company decisions and physical interventions under staff control.

The current users are **tenants and BeLive's support staff**. New tenants receive move-in coordination; existing tenants receive enquiry/complaint assistance, and departing tenants receive move-out coordination. Owner support, acquisition, marketing content, lead collection, sales engagement, property recommendation and booking are outside this phase. A confirmed tenancy may be entered from an authorised record; this project does not automate the preceding sales process.

## Business grounding

BeLive's public website describes furnished co-living rentals and services including Wi-Fi, cleaning, smart access and maintenance. These support categories inform the prototype, but individual rent, fees, access permissions, tenancy terms and condo rules must come from verified operational records. See [company research](COMPANY_RESEARCH.md).

## Workflow A: new-tenant and move-out coordination

1. Staff verifies the tenant/unit reference against an authorised record and records the evidence reference.
2. Staff records the condo's permitted move days/hours, operational rules and required inspection checklist. Weekend-only movement is supported when it is the actual recorded rule, not imposed on all condos.
3. Staff records PIC availability and eligible condos. A requested move must pass the condo window, date and availability checks.
4. The coordinator randomly selects among eligible available PICs. No eligible PIC means no confirmed arrangement; staff must resolve availability. The prototype reserves one PIC per move date.
5. The system saves the move, assigned PIC and a snapshot of the rules/checklist, then queues a tenant notice for review and delivery.
6. At/after the scheduled time, staff completes every required inspection item and records evidence. The system does not fabricate an inspection outcome, damage finding, deposit deduction or key handover.

## Workflow B: existing-tenant support

1. **Receive:** accept a private tenant request, an operator-entered enquiry or a report from a selected authorised public source. Preserve source identity and redacted content versions; reuse duplicate intake results.
2. **Verify and protect:** public feedback does not prove tenancy. Invite private contact and let staff verify identity before accessing tenant-specific records. Screen immediate safety risks before routine AI.
3. **Classify:** a logical Triage Agent returns support relevance, category, urgency, an evidence excerpt, summary and uncertainty. Invalid or uncertain output requires staff.
4. **Investigate:** logical Investigation/Response Agents use the case, relevant tenant updates, that tenant's verified records, condo rules and reviewed wording examples. Missing facts become questions, not invented account information.
5. **Assist:** prepare a response and proposed action. Staff reviews wording and handles physical repairs, billing/refund decisions, security-access changes and exceptions. In this prototype all external notifications require approval.
6. **Handover:** failed/uncertain AI, elevated risk or unsupported actions create a staff review case with the reason. Staff acknowledges ownership; missed acknowledgement queues escalation to backup and management.
7. **Track:** work orders retain department, description and completion evidence. A follow-up stage gathers tenant feedback; reminders keep the case open. An unresolved or newly risky case is reassessed by staff.
8. **Verify and close:** require explicit outcome evidence, verified tenancy and no outstanding work order. AI never declares resolution by itself, and customer silence is not proof of resolution.
9. **Improve:** after verified closure, staff approves, corrects or rejects reusable response wording. Only the latest approved/corrected version is retrieved. Rejection/reopening revokes reuse; learning here means reviewed retrieval, not model training.

## Logical responsibilities and implementation

| Responsibility | Mechanism | Authority |
|---|---|---|
| Intake, duplicate detection and risk pre-screen | Deterministic Python/SQLite | Record and route |
| Relevance, category and urgency | Native Hermes Triage Agent | Propose structured assessment |
| Case investigation and response | Native Hermes Investigation/Response Agents | Read bounded context and draft |
| Move coordination | Deterministic condo/availability checks and random eligible PIC | Record an arrangement satisfying entered rules |
| Staff coordination and follow-up | Deterministic state machine, timers and outbox | Queue, track, require approval/evidence |
| Reviewed memory | Staff feedback plus isolated native MemoryStore | Current redacted style guidance only |

Logical agents do not require separate models or servers. The current implementation uses sequential agent stages and one local application server. AI has two read-only project tools and cannot send messages, run shell commands, browse unrestricted sites or mutate business records.

## Information required from BeLive

These are implementation inputs for a pilot, not assumptions to fill with fictional company facts:

- Authorised tenant/unit references and a reliable identity-verification procedure.
- Actual condo move windows, checklists, inspection requirements and exception process.
- PIC eligibility/availability, departments, backup contacts and escalation ownership.
- Approved support guidance, verified maintenance records and which actions may be automated.
- Confirmed urgency definitions, acknowledgement/follow-up targets and business hours.
- Approved communication channels, company API access and a gateway with delivery receipts.
- Model/provider selection, language expectations, privacy/retention rules and staff roles.

## Evaluation plan

Use fictional test cases first, then an authorised pilot with human supervision. Evaluate relevance/category/urgency agreement against staff labels; explicitly track missed high-risk cases, unsupported factual claims, cross-tenant leakage and incorrect closure. Measure handling time, staff acceptance/editing of drafts, acknowledged handover time, repeat complaints, unresolved follow-ups and tenant feedback. Compare with a manually recorded baseline; do not claim savings without measurement.

Acceptance requires correct tenant isolation, no action before its required approval, no closure without evidence, enforcement of condo/PIC rules, truthful delivery outcomes and immediate exclusion of rejected memory. The repository currently verifies these local controls through isolated tests. Live provider quality, company API access, gateway delivery, production identity/roles and operational targets still require BeLive validation.

## Decisions for the next meeting

Confirm tenant-support scope; agree on the verified source of tenant/condo data; select one supported communication channel for the pilot; define staff escalation ownership and timing; identify a small evaluation set and acceptance criteria. Keep owner, marketing and sales modules outside this pilot.
