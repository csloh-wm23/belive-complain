# BeLive: simple test guide

## Open the prototype

Keep the local server running. Open `http://127.0.0.1:8877/belive` for the tenant website or `http://127.0.0.1:8877/` for staff. These local addresses work on the computer running the server.

On a new installation, create your own admin account. There is no shared default password. Configure your model using `docs/AI_KEY_SETUP.md`, then sign in and open **Setup & knowledge**.

1. Choose **Prepare demo data**. This adds a fictional property, tenant and 36 approved demonstration knowledge entries. It does not replace existing company records or model settings.
2. Choose **Test AI connection**. Wait for a genuine successful result.
3. Choose **Enable routine automation**.
4. On the tenant website choose **Try demo tenant**. You do not need to copy an access key for this fictional account. Normal tenants still need their own verified private code.

## Test the complaint rules

Choose **New request**, enter a short title and one of these messages. Open **My requests** to see the status and conversation.

| Message | Expected behaviour |
|---|---|
| How can I check a Wi-Fi connection problem on my device? | A suitable SIMPLE answer can be sent automatically after knowledge and safety checks. |
| The fan is broken and needs a repair. What details should I send? | MODERATE: AI checks the details and prepares assistance. Staff reviews and sends the saved draft; no automatic AI reply. |
| Smoke and sparks are coming from the electrical socket. | HIGH: immediate staff handover before routine AI. This is only a fictional test. |
| The Wi-Fi suggestion did not work. | Use **Still unresolved**. The message and handover are saved; the case stays open for staff. |

An automatic reply is not proof that a repair happened. Model failure, missing knowledge and uncertainty also go to staff. Do not demonstrate with real danger or personal tenant information.

## What staff does

1. Open **Cases** and select the request title.
2. **AI assessment** shows whether it is a complaint or support question, its level, staff destination, actual agent runs and reviewed lessons used.
3. Read the conversation and **Response draft**. Edit it if needed and choose **Save edited reply**. Check the review box, then **Send saved reply to tenant**.
4. Expand **Staff actions and outcome checks** to accept ownership, record action, create a local work order and verify the result. Close a case only after checking evidence.
5. After a verified closure, **Teach future replies** can approve useful wording or save a correction. The next AI request retrieves current reviewed examples automatically. Rejection or reopening stops their reuse.

In **Setup & knowledge → Where should cases go?**, an admin enters BeLive's actual destinations for each topic. Blank topics go to Support team. AI chooses the topic; it does not invent departments. The staff queue is local. Gateway notifications remain separately reviewed and need a configured gateway; a queued alert is not confirmed delivery.

## Show learning with the real model

1. Open **Learning** and choose **1. Generate the first reply**.
2. Read the first reply and the suggested writing lesson. Approve the lesson, then generate the next reply.
3. Compare the two actual model outputs. Both use the same question and approved guide. The page checks: starts directly with two numbered points, asks exactly one question and uses no more than 90 words. It also shows the actual word counts.
4. The lesson is saved automatically if the reply passes more checks, or passes all three with at least 20% fewer words and at least 12 words. A same or worse result does not create a successful-learning claim.
5. Send a fresh Wi-Fi request as the demo tenant. In its staff case, **Reviewed lessons used** shows the retrieved lesson. **Stop using this lesson** prevents later reuse.

This demonstration changes future reply wording through approved feedback memory. It does not retrain the model, prove general accuracy or turn a previous reply into company policy. Demo lessons apply only to the fictional demo property. Actual property knowledge is added and maintained separately by staff.

## Find things quickly

- **Home:** start a demo, review cases or open learning.
- **Cases:** complaint status, AI assessment and staff responses.
- **Public posts:** configure selected authorised sources. Actual platform access is required.
- **Learning:** before/after comparison and reviewed feedback.
- **Setup & knowledge:** demo setup, routing, verified knowledge, AI check and accounts.
- **More tools:** Messages, Saved records and Reports.

No public social reply is automatically published. Live Google/Threads/Facebook access must be configured and tested separately.
