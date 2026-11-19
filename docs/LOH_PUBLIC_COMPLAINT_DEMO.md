# BeLive public complaints demo

**Loh Chee Seng**

Present in this order.

1. **Public reviews** → import a real one-star Google review.
2. **Complaints** → show the AI assessment, staff route and reply preview.
3. **Self-learning** → show how reviewed feedback changes a later reply.

## 1. Open and check BeLive

1. Open the [staff dashboard](http://127.0.0.1:8877/) and sign in as `presentation-admin` on the presentation computer. The password is in the local `artifacts/presentation/admin-login.json` file. A fresh installation uses the administrator created on that computer.
2. If the dashboard is down, open PowerShell in the BeLive project folder. Run `python scripts/start_demo_ollama.py`, then `python server.py`. Leave the server running for the demo.
3. Open **System setup → AI & knowledge → AI & replies → Test AI connection**. Check for **PASSED**. This demo uses Hermes with the local Qwen3.5 4B model.
4. If **Self-learning** asks for demo data, open **System setup → AI & knowledge → Demo → Prepare demo data** first.

## 2. Import the real review

1. Open [Public reviews](http://127.0.0.1:8877/#sources) and find **Import a Google review from a link**.
2. Copy the [individual one-star BeLive Google review link](https://www.google.com/maps/contrib/114279446675905798536/place/ChIJf2EBIq8fMiARfTvF7ZZhmsM/@4.2663822,100.919621,8z/data=!4m6!1m5!8m4!1e1!2s114279446675905798536!3m1!1e1?hl=en&entry=ttu&g_ep=EgoyMDI2MTExNS4wIKXMDSoASAFQAw%3D%3D) into **Google review link**. On Google Maps, the right link comes from **Share** on the review itself.
3. Select **Import review**. A new import saves the visible review and starts the assessment. If the review is already saved, the app opens the existing case. On this computer that case is [BL-126E3EF141](http://127.0.0.1:8877/?case=BL-126E3EF141#cases).
4. In the case, select **Open original Google review** to show the individual review. The reviewer reported a water dispenser without cold water for almost three months, a broken washing machine, and little follow-up.

If the import stalls, open the saved case on this computer. On a fresh copy you can use **Public reviews → Record a public complaint**, paste the same link, enter a short title and add the anonymized summary above. Select **Save complaint and assess**. Describe that route as manual intake. For browser import on a fresh machine, install the project's Playwright dependency with `python -m pip install -r requirements-dev.txt` and have Chrome available.

**Say:** “My part starts outside BeLive. I collect a public review and bring it into our complaint queue. This review is already in our database, so the app opens the existing case.”

**Collect a batch.** In [Public reviews](http://127.0.0.1:8877/#sources), select **Collect up to 10 reviews** with the BeLive Google Maps listing filled in. The app saves visible written 1–2 star reviews, skips existing cases and queues new ones for assessment. If Maps stalls at the filter, an admin can use **Google sign-in for collector** to open its separate Chrome window. Sign in directly with Google, close that window, then retry collection. Individual **Share** links can also be pasted one per line. The result shows how many were saved or already present.

## 3. Show the assessment and staff route

1. In the complaint, scroll past **Conversation** to **AI assessment**. A new case can show **Assessment is running in the background**. Wait for it to finish.
2. Point to the **Complaint Analysis Agent**, the **Message** decision, the category, the level at the top, and the **Staff destination**. Open **Source evidence and activity** to show the evidence quote and history.
3. The saved case is **Maintenance** and **HIGH**. It went to **Needs staff** and now shows **Staff handling** because someone acknowledged it. Open **Source evidence and activity**, just above **Public reply preview**, and look for **Staff took ownership** and **Escalated after waiting for staff**. The escalation row records an overdue acknowledgement. To show where the case first went, point to **Assigned team** and the case status. Show the actual result when assessing a fresh copy. Explain the rating using the reported duration, the two appliance issues and the lack of follow-up. Read the case's actual team name. BeLive configures team routing by category.
4. Open the **Alerts** button to find the saved HIGH case. For cases awaiting a person, open **Complaints → Needs staff**.

| Decision | What happens |
| --- | --- |
| Outside support | Praise or unrelated feedback can be marked outside the support queue. |
| SIMPLE | A clear routine complaint with matching approved guidance and passing checks can get an automatic draft inside BeLive. Look for **Approved SIMPLE guidance · saved as a draft**. |
| MODERATE | Staff handles the complaint. AI can help prepare wording for review. |
| HIGH | Staff takes priority. An immediate danger signal can go to staff before normal AI runs. |

The appliance review demonstrates staff handover. To explain the SIMPLE rule, quote the fictional test example “My phone will not connect. What can I check?” Automated tests checked that approved SIMPLE wording creates a local draft and leaves the outbox empty. A fresh AI run can go to staff if the guidance or certainty checks fail.

**Say:** “The first agent decides whether this is a complaint and reads the details. The level controls what happens next. Here two appliances were reported faulty and the problem had been outstanding, so staff need to investigate.”

## 4. Show the tailored reply and explain a request for staff

1. In the appliance case, scroll to **Public reply preview**. Select **Generate tailored preview** or show the saved wording. An existing preview has **Regenerate preview**.
2. Point to **Public Reply Preview Agent**. The analysis agent assessed the report. This second agent writes a short acknowledgement based on what the reviewer reported. The draft invites them to contact BeLive privately. Keep public replies in preview throughout the demo.
3. If someone replies on Google or Threads, “I want staff to help me,” staff can record the relevant follow-up in the existing case. Enter it under **Case progress → Internal note / work completed**, then choose **More options → Add private note**. Direct the reviewer to BeLive's private tenant support. Staff can verify tenancy there and keep the original review or post link as a private reference. The current one-review importer reads the specified review. Ongoing public conversation capture is manual in this demo.
4. Once the customer is in BeLive support, Jackson's intake and staff workflow continue in the shared queue. You can leave **More options** collapsed while presenting the assessment and reply preview.

**Say:** “The second agent drafts a reply specific to this review. If the customer asks for a person on Google or Threads, we direct them to private support. Staff can verify who they are there and use the original review as a reference.”

### Close a complaint

**For an imported review or an older case without browser tracking**, open the case and select **Take ownership**. When staff have checked the outcome, record the evidence under **Case progress**, tick **I checked the evidence and confirmed the outcome**, and select **Close complaint**.

**For a private complaint**, the customer opens [Make a complaint](http://127.0.0.1:8877/portal?view=make), submits the form and uses [Track complaint](http://127.0.0.1:8877/portal?view=track) in the same browser. The receipt includes a BL reference for staff.

1. Staff open the case, select **Take ownership**, record the work and click **Mark handled · ask customer to confirm**.
2. The customer opens **Track complaint** and selects **Issue resolved** or **Still unresolved**.
3. After confirmation, staff check the evidence, enter an outcome note and select **Close complaint**. **Still unresolved** returns the case to staff.

If the customer changes browser or clears its site data, they can give BeLive the BL reference so staff can locate the complaint.

## 5. Show self-learning

### Start with a reply from a solved complaint

Use this example of a message to BeLive: "The shared washing machine stopped working and I still haven't heard back. Can someone check it?"

1. Open [the completed demo complaint](http://127.0.0.1:8877/?case=BL-210E56891B#cases). Under **Conversation**, show the staff reply asking when the cycle stopped and whether the display showed an error. This fictional rehearsal used a simulated completed repair and customer confirmation.
2. The case was closed after staff recorded the outcome. Under **Teach future replies**, selecting **Use saved wording as a lesson** saved the reply sent in step 1. Open **Self-learning** to see it in **Reviewed lessons from completed cases**.
3. Open [the later demo complaint](http://127.0.0.1:8877/?case=BL-B4C4EF383F#cases), then **AI assessment > Approved replies sent to the agent**. Show the approved reply and click **Source case BL-210E56891B** to trace it back.
4. In the later case, show **Reply to customer**. The draft reused the apology and the question about the washer display. It also added an unsupported 24-hour turnaround, so staff would edit that out before sending. The later case remained **MODERATE** and **Needs staff** because the washer needs inspection.

Both cases were run using the local Qwen3.5 4B model. These case links refer to the demo records on this computer.

### Optional comparison with measured formatting checks

1. Open [Self-learning](http://127.0.0.1:8877/#memory). Under **Practice topic**, choose **Wi-Fi** and use “How can I check a Wi-Fi connection problem on my device?” Select **Generate first reply**.
2. Read **Review the writing tip**. Select **Use this tip & generate second reply**. Both replies use the same question and approved facts. The second also uses the tip that you reviewed.
3. Show the two replies and their actual scores. The checks are two numbered points, one clarifying question and at most 90 words. The app can save the style tip after measurable improvement. If scores tie and the screen reports no measured improvement, say that.
4. For previously measured proof, the Wi-Fi run `LEARN-05A95A9FC2` went from **2/3 to 3/3**, 58 words to 40. The later demo case [BL-0D8885D88D](http://127.0.0.1:8877/?case=BL-0D8885D88D#cases) retrieved the saved lesson and scored 3/3 in 36 words. These are earlier rehearsal results. For the later case, show **AI assessment → Reviewed lessons provided to the reply agent** and compare the actual wording with the tip if the case is present on your computer.
5. If asked how learning applies to public complaints, explain that after verified closure, **Teach future replies → Save corrected lesson** can store general, customer-safe wording with a matching question for later SIMPLE guidance. When used, **Source evidence and activity** records **PUBLIC_LESSON_USED**. The measured Wi-Fi example is from the demo reply workflow. The appliance preview shows the separate tailored drafting step.

**Say:** “We compare two real replies and measure whether the tip helped. When it helps, BeLive can save the reviewed tip and use it for matching future replies. The model stays the same.”

## 6. Explain collection access if asked

- The live Google demo uses **Import review** on one real review link. It works without a Google API token.
- **Scheduled collection with API access** is the separate Google Reviews and Threads feature. Once an administrator configures an authorised source and token, **Collect reviews now** starts a manual check, or the configured schedule checks for new items while BeLive is running.
- The Google and Threads scheduled paths were tested with simulated API responses. Live scheduled Google collection requires an approved Business Profile project, verified location resource and an authorised token. Live scheduled Threads collection needs an authorised post with reply-read access and a token.
- Optional closing screen is **System setup → Reports & activity → Complaint outcomes**. Point to human handovers and verified closures if asked how the team tracks follow-up.

## Prof Lim's checklist and what to show

| Requirement | Evidence to show |
| --- | --- |
| Collect Google Reviews and Threads automatically | Import the real one-star Google review by its own link and show the saved case. For scheduled Google Reviews and Threads, show the automated scheduler test. It checked both enabled sources and skipped a paused Threads source using simulated responses. Live scheduled collection is pending authorised platform access. |
| Decide whether the text is a complaint | Open **AI assessment → Message** on the real review. It says **Complaint**. In a local Qwen rehearsal, “The shared kitchen is clean and the support team has been helpful” was marked outside support and skipped. |
| Explain SIMPLE, MODERATE and HIGH | Show the exact message, the tag and the next action. The verified examples below cover all three levels. BeLive also sends immediate danger to staff before routine assessment. |
| Reply automatically to SIMPLE | Show **Approved SIMPLE guidance · saved as a draft** after assessing the practice Wi-Fi complaint. The model chose approved guidance and BeLive saved the draft automatically. The rehearsal outbox stayed empty. Public publishing stays in preview for this demo. |
| Send MODERATE and HIGH to staff | The practice washing-machine report entered **Needs staff** with **Support team** as the destination. The real HIGH appliance review's history shows **Escalated after waiting for staff** and **Staff took ownership**. A new case labelled **Needs staff** is still waiting for ownership. Show the local queue or **Alerts**. |
| Show two agents doing distinct jobs | In the real case, show **Complaint Analysis Agent** in **AI assessment**, then **Public Reply Preview Agent** under the saved tailored preview. The first assessed the complaint. The second wrote the case-specific acknowledgement. |
| Show learning and improvement | Go to **Self-learning → Past comparisons** and pick the saved **Wi-Fi** comparison from **18 November 2026 at 2:43 AM** Malaysia time. Show 2/3 to 3/3 and 58 to 40 words. Then open [the later demo case](http://127.0.0.1:8877/?case=BL-0D8885D88D#cases) and show that the reply agent received two reviewed examples, including the saved Wi-Fi lesson. This is evidence of reviewed feedback reuse and clearer formatting in the tested demo replies. |

### Verified severity examples

Use the real review for HIGH. Use clearly labelled fictional inputs in a practice database for the other levels. Local Qwen3.5 4B produced these results in an isolated rehearsal.

| Input | Assessment and outcome |
| --- | --- |
| “My phone will not connect to the Wi-Fi, but my laptop still works. What can I check on my phone?” | **SIMPLE**. A general device check is available. BeLive saved approved guidance as a local draft. |
| “The washing machine in the shared laundry stopped working today. Please arrange for staff to inspect it.” | **MODERATE**. Staff needs to inspect the machine. BeLive routed the case to the Support team. |
| The real one-star review about two appliances and a prolonged lack of follow-up. | **HIGH** on the saved case. Show the reported details and the escalation history. |

For the automated evidence, run `python -B -m unittest discover -s tests -p test_public_connectors.py -v` in the BeLive folder. Four tests passed in rehearsal, covering repeat collection, the scheduler, approved SIMPLE drafts and keeping the MODERATE preview local.

## If you only have two minutes

Open the real case → point to the **HIGH** tag and the staff ownership history → show **AI assessment** and the saved **Public reply preview** → open **Self-learning** and explain the earlier **2/3 to 3/3** result and later reuse.
