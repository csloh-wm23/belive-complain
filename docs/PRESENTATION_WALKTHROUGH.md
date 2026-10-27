# BeLive complete presentation walkthrough

Existing-tenant support only. This guide covers the tenant website, tenant portal and all eight staff pages. Allow 12-15 minutes for the full tour, or use steps 1-4 and briefly describe the remaining pages for a shorter presentation.

## Before presenting

Open three tabs on the computer running BeLive:

- Tenant website: http://127.0.0.1:8877/belive
- Staff dashboard: http://127.0.0.1:8877/
- Tenant portal: http://127.0.0.1:8877/portal

Sign in as Admin to demonstrate records, access keys and configuration. Support accounts handle cases but cannot issue tenant keys or maintain Admin settings. Credentials are private and are not included in this guide. Keep the server running and refresh dashboard tabs after a restart. The GitHub repository shares the code; localhost is a website running on this computer.

Use a clearly fictional DEMO tenant and property, and have that tenant's private access key ready. Do not switch databases during the tour: accounts and records belong to their database. Show only fictional records on the projector.

Opening script:

> Our prototype focuses on BeLive's existing tenants. It connects complaint intake, AI assessment, staff action, tenant communication and verified closure. It does not cover marketing, sales, owners or move-in and move-out arrangements.

## 1. Tenant website: explain how a complaint enters the system (1 minute)

Open `/belive`. Point to the six support topics, **Make a complaint**, **Track my request** and **My requests**.

> This is the tenant-facing entry point. Tenants can report Wi-Fi, maintenance, cleaning, access, utilities and billing concerns. A staff-issued access key connects the request to the correct tenant.

Click **Make a complaint**, enter the DEMO access key and use a new, clearly fictional Wi-Fi enquiry:

- Title: `DEMO presentation: Wi-Fi disconnecting`
- Details: `Fictional demonstration: Wi-Fi drops each evening on both my laptop and phone. What information should I provide to support?`

Click **Submit complaint**. Wait for the saved case reference. Reusing an identical report may return an existing case because the app prevents duplicates.

> This reference comes from a saved case in the backend. The website and staff dashboard share the same complaint record.

Open **Staff: open this case in dashboard** in another tab. Keep the receipt available for the tenant tracking step.

## 2. Staff Overview: show the team's starting screen (45 seconds)

In the staff tab, click **Overview**.

> Staff start here to see open cases, cases needing a person, overdue actions and notifications awaiting approval. Recent cases and the staff-attention list provide shortcuts to the actual case. The workflow strip shows receive, assess, assist, verify and review.

Point to the metrics and recent case. Click **Support cases** to continue.

## 3. Support cases: demonstrate the main staff workflow (3-4 minutes)

Use search and the status or queue filters to find the new case, then open it. Explain the case from top to bottom:

| Area | What it means / what to do |
|---|---|
| Tenant conversation | Tenant reports, tenant replies and responses explicitly published by staff. Private notes and unsent drafts stay out. |
| Category, urgency and status | The type of problem, priority and current handling stage. Staff can correct category/urgency using an action note. |
| Source and immutable versions | Where the report came from and its retained versions. |
| Review reason | Why staff attention is required, including risk, uncertainty or an AI validation failure. |
| AI assessment & proposed assistance | Validated summary, exact evidence quote, uncertainty, cited support records and plan if available. |
| Case handling | Staff ownership, private notes, next action and local deadline. |
| Response draft | Proposed wording that must be reviewed and saved before publication. |
| Work orders | Internal tasks for the relevant department, with recorded completion evidence. |
| Internal case timeline | The case's recorded actions and changes. |

Click **Reload latest case details** after the AI finishes. For a routine case, **Run grouped support agents** can request a new assessment at the supported stages. High-risk cases go to staff instead.

> Hermes runs the bounded agents using our configured AI model. The AI classifies and summarises the issue, checks the provided tenant context and can suggest a cautious response. This is assistance, not a confirmed repair or an automatically sent reply. A valid assessment can still require staff handling.

If no safe draft is available, explain the staff route and write a reviewed clarification yourself. Do not present staff wording as AI-generated.

Click **Acknowledge as staff**. In the action note, enter `DEMO: review the reported Wi-Fi symptoms with the tenant.` Choose a next-action deadline and click **Save next action & deadline**. Use **Add internal note** to show a private staff note if time permits.

For the response, type or review:

> Could you tell us when the connection drops, whether both devices are affected at the same time, and any error message you see? Please do not send passwords or access codes.

Click **Save reviewed wording**, then tick **I checked the evidence / reviewed the exact saved response**, then click **Publish saved response to tenant portal**.

> Saving is separate from publishing. Only this explicit publication makes the reviewed reply visible to the tenant.

Explain **Queue for external gateway** as a separate route through the Notifications page. Do not click it for a portal-only demonstration.

For a maintenance example, explain that staff can enter a department and action note, then choose **Create work order from action note**. This saves a task; it does not prove the department received it or the repair happened. An open work order must be completed with evidence before case closure.

## 4. Tenant portal and follow-up: complete the communication loop (2 minutes)

From the website receipt click **Track this request**, or open `/portal`. Enter the same tenant access key and click **Open my support records**. Click **Refresh conversations** if needed.

> The tenant sees only their own support records and published conversation, not staff drafts, internal notes or other tenants' cases.

Read the staff reply. Send a fictional follow-up such as `DEMO: Both devices disconnect at the same time.` In the staff case, use **Reload latest case details** to show the tenant's reply.

In the tenant portal, point to **Issue resolved** and **Still unresolved**. These record feedback; they do not automatically close a case. **Close my support records** clears this browser view without revoking the access key.

Back in the staff case, explain the closure sequence. Demonstrate it only on a fictional case with clearly labelled simulated evidence:

1. Enter an action note and click **Record action & start follow-up** after staff acknowledgement.
2. Check tenant feedback or other outcome evidence. Complete any open work orders using a completion note.
3. Enter the verification evidence, tick confirmation and click **Record verified resolution**.
4. Click **Close verified case**.

> The case is closed only after staff verifies the outcome. If it remains unresolved, staff can reassess it; closed cases can be reopened. The AI never declares a repair completed on its own.

## 5. Notifications: explain approval and delivery (45 seconds)

Close the case dialog and click **Notifications**. Point to saved alerts, follow-ups or queued responses.

> This is the reviewable outbox. A saved notification is not the same as a delivered message. For external delivery, staff approves the exact message, then uses a configured gateway. An uncertain delivery stays UNKNOWN and is not automatically retried.

Point to **Check due follow-ups now**, which checks stored deadlines. Portal publication in step 3 is separate from this external gateway. Do not claim Discord, WhatsApp or another channel is connected unless that gateway is actually configured and tested.

## 6. Tenant & property records: explain the Admin setup (1-2 minutes)

Click **Tenant & property records**. Show these areas in order:

1. **Property support guidance**: records checked property-specific support rules. This is not move-in scheduling.
2. **Verified tenant**: links an internal tenant reference to a property and unit after staff checks an authorised record. The checkbox is a staff assertion, not an automatic identity check.
3. **Verified support context**: stores relevant facts and a source reference for this tenant. These are the records the AI can cite.
4. **Issue tenant portal access key**: select the DEMO tenant and choose **Issue seven-day key** if a new demonstration key is needed. Share keys privately. **Revoke all keys for this tenant** invalidates existing keys, so only demonstrate it on a spare DEMO tenant.
5. **AI connection check**: **Test AI connection** makes a real provider request without tenant records. A saved PASSED result is a check at its shown time, not continuous proof every case will succeed.
6. **Operator accounts**: Admin manages accounts; Support handles cases. These logins are separate from tenant access keys and the AI provider credential.

> Verified records supply context; the AI must not invent tenancy policies or repair outcomes. Admin access controls who maintains these records and issues portal access.

## 7. Database & records: explain persistence and recovery (45 seconds)

Click **Database & records**. Show the current file location and search the saved records for the DEMO tenant.

> Data is saved in SQLite, so refreshing or restarting preserves this workspace. Staff can inspect saved records, and Admin can correct or deactivate support context while retaining previous versions.

Point to **Correct, deactivate or view versions**. Explain **Create verified backup** and recovery into a separate copy. A backup verifies a saved database copy, not the truth of its tenant facts.

Point to **Choose database for next launch** without switching during the presentation. Choosing another file takes effect after restarting; it does not move the current records.

## 8. Public monitoring: show the optional external intake route (45 seconds)

Click **Public monitoring**.

> This optional route reads selected authorised Google Business Profile reviews, Facebook Page posts/comments or Threads replies using official APIs. It is bounded monitoring, not a search of the whole platform. API credentials and access are required.

Explain **Resource** using format examples only:

- Google: `accounts/123/locations/456`
- Facebook Page feed: `123456789/feed`
- Facebook post comments: `123456789_987654321/comments`
- Threads replies: `123456789/replies`

These example IDs are not live company resources. Do not save them as if they work. Configured sources can be paused/resumed or scanned manually. Automatic checks run no more often than every 15 minutes while the app runs, at most 25 recent text entries per scan. Public, unverified people need private tenancy verification before personal assistance. This page is intake for tenant support, not marketing lead generation.

## 9. Reviewed memory: explain what the system learns (45 seconds)

Click **Reviewed memory**. If empty, explain the workflow without claiming a saved example exists.

> After staff verifies and closes a case, they can approve its response wording or save a corrected version as a style example. Rejecting the example or reopening the case stops future reuse. The system reuses reviewed wording style; it does not retrain the model or treat old case facts as true for another tenant.

To show an example, reopen a CLOSED fictional case's details, use **Approve saved wording** or **Save corrected example** under **Review reusable style**, then return here. **Refresh native Hermes memory** updates the isolated style store. Sharing a redacted style example through the authenticated API requires its separate explicit checkbox.

## 10. Reports & activity: show traceability and finish (45 seconds)

Click **Reports & activity**. Show category counts, human handovers, verified closures and the activity timeline. **Export support snapshot** downloads the current support snapshot as JSON; it is operational data, not a public report.

> The reports summarise what was stored, and the audit history shows who recorded actions. A verified closure is a staff decision, not an AI success-rate measurement.

Closing script:

> The main benefit is a connected tenant-support workflow: one recorded case from the tenant website through AI assistance, staff responsibility, tenant updates and evidence-based closure. Routine work is assisted, and risk or uncertainty stays with people.

## If something unexpected happens

- **Needs staff / HIGH urgency:** this can be a successful safety handover. Open the assessment and review reason; it does not itself mean the AI failed.
- **AI_FAILED_OR_INVALID or another validation code:** no usable result was accepted. Read the explanation and use staff handling; do not claim it is a successful AI response.
- **No draft on a high-risk case:** expected; staff writes the appropriate response.
- **No records in a page:** show its purpose. Do not pretend an integration or saved example exists.
- **Administrator access required:** sign in with Admin for records, keys and configuration; Support is for case handling.
- **Invalid/expired tenant key:** issue a new key for the correct verified DEMO tenant as Admin.
- **Portal reply not visible:** save reviewed wording, tick confirmation, publish to the portal, then refresh the tenant conversation.
- **Cannot close:** the case needs follow-up, recorded verification and completion of open work orders first.
- **A friend cannot open your localhost link:** they need to run their own local copy, or the app needs a separately authorised deployment.

## Short presentation order

Website complaint -> Overview -> Support case -> reviewed portal reply -> tenant reply -> verified closure -> briefly show Notifications, Records, Database, Monitoring, Memory and Reports. For a shorter talk, describe optional integrations and configuration instead of filling every form live.
