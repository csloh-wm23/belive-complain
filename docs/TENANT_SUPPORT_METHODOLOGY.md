# Proposal: AI-assisted tenant support for BeLive

## Objective and current scope

Connect existing-tenant rental-related enquiries, complaints, staff coordination and verified follow-up in one support workspace. Reduce repetitive information gathering and drafting while keeping company decisions and physical interventions under staff control.

The current users are **existing tenants and BeLive's support staff**. This module receives rental-related enquiries/complaints, assists with common questions, routes unresolved cases to staff and tracks follow-up through verified closure. Move-in/out arrangements, inspection checklists and random PIC assignment belong to another part of the overall proposal and are outside this team's current scope. Owner support, acquisition, marketing, sales, property recommendation and booking are also excluded. Staff enters existing tenancy references from authorised records; the system does not automate onboarding.

## Business grounding

BeLive's public website describes furnished co-living rentals and services including Wi-Fi, cleaning, smart access and maintenance. These support categories inform the prototype, but individual rent, fees, access permissions, tenancy terms and condo rules must come from verified operational records. See [company research](COMPANY_RESEARCH.md).

## Tenant enquiry and complaint workflow

1. **Receive:** accept a private tenant request, an operator-entered enquiry or a report from a selected authorised public source. Preserve source identity and redacted content versions; reuse duplicate intake results.
2. **Verify and protect:** public feedback does not prove tenancy. Invite private contact and let staff verify identity before accessing tenant-specific records. Screen immediate safety risks before routine AI.
3. **Classify:** a logical Triage Agent returns support relevance, category, urgency, an evidence excerpt, summary and uncertainty. Invalid or uncertain output requires staff.
4. **Investigate:** logical Investigation/Response Agents use the case, relevant tenant updates, that tenant's verified records, verified property house rules and reviewed wording examples. Missing facts become questions, not invented account information.
5. **Assist:** prepare a response and proposed action. Staff reviews wording and handles physical repairs, billing/refund decisions, security-access changes and exceptions. In this prototype all external notifications require approval. Reviewed responses can be published to the tenant portal, with a separate conversation from internal notes.
6. **Handover:** failed/uncertain AI, elevated risk or unsupported actions create a staff review case with the reason. Staff acknowledges ownership; missed acknowledgement queues escalation to backup and management.
7. **Track:** work orders retain department, description and completion evidence. The tenant portal records replies and resolved/unresolved feedback. A follow-up stage gathers tenant feedback; reminders keep the case open. An unresolved or newly risky case is reassessed by staff.
8. **Verify and close:** require explicit outcome evidence, verified tenancy and no outstanding work order. AI never declares resolution by itself, and customer silence is not proof of resolution.
9. **Improve:** after verified closure, staff approves, corrects or rejects reusable response wording. Verified support context retains immutable versions and can be corrected, expired or deactivated. Only the latest approved/corrected writing-example version is retrieved. Rejection/reopening revokes reuse; learning here means reviewed retrieval, not model training.

## Logical responsibilities and implementation

| Responsibility | Mechanism | Authority |
|---|---|---|
| Intake, duplicate detection and risk pre-screen | Deterministic Python/SQLite | Record and route |
| Relevance, category and urgency | Native Hermes Triage Agent | Propose structured assessment |
| Case investigation and response | Native Hermes Investigation/Response Agents | Read bounded context and draft |
| Staff coordination and follow-up | Deterministic state machine, timers and outbox | Queue, track, require approval/evidence |
| Reviewed memory | Staff feedback plus isolated native MemoryStore | Current redacted style guidance only |

Logical agents do not require separate models or servers. The current implementation uses sequential agent stages and one local application server. AI has two read-only project tools and cannot send messages, run shell commands, browse unrestricted sites or mutate business records.

## Information required from BeLive

These are implementation inputs for a pilot, not assumptions to fill with fictional company facts:

- Authorised tenant/unit references and a reliable identity-verification procedure.
- Relevant property house rules and verified tenant-support guidance.
- Support departments, backup contacts and escalation ownership.
- Approved support guidance, verified maintenance records and which actions may be automated.
- Confirmed urgency definitions, acknowledgement/follow-up targets and business hours.
- Approved communication channels, company API access and a gateway with delivery receipts.
- Model/provider selection, language expectations, privacy/retention rules and staff roles.

## Evaluation plan

Use fictional test cases first, then an authorised pilot with human supervision. Evaluate relevance/category/urgency agreement against staff labels; explicitly track missed high-risk cases, unsupported factual claims, cross-tenant leakage and incorrect closure. Measure handling time, staff acceptance/editing of drafts, acknowledged handover time, repeat complaints, unresolved follow-ups and tenant feedback. Compare with a manually recorded baseline; do not claim savings without measurement.

Acceptance requires correct tenant isolation, no action before its required approval, no closure without evidence, absence of move/inspection/PIC operations, truthful delivery outcomes and immediate exclusion of rejected memory. The repository currently verifies these local controls through isolated tests. Live provider quality, company API access, gateway delivery, production identity/roles and operational targets still require BeLive validation.

## Decisions for the next meeting

Confirm tenant-support scope; agree on the verified source of tenant/condo data; select one supported communication channel for the pilot; define staff escalation ownership and timing; identify a small evaluation set and acceptance criteria. Keep move-in/out coordination, inspections, PIC assignment, owner support, marketing and sales outside this pilot.

## Demonstration and evaluation readiness

The repository includes local Admin/Support login, a tenant conversation/outcome loop, critical/overdue queue views, versioned support context and consistent backup/recovery. The 24-case English/Malay/Chinese evaluation set is kept separate from the application database. The connection probe and opt-in evaluator require actual model configuration; their results must be reported as unmeasured until a real run is completed. Human reviewers should judge language quality, factual grounding and the appropriateness of handover, not only automated category checks.
