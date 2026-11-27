# Public-monitoring presenter guide

Your part starts with a selected permitted public source and produces a saved complaint, an explained decision, a staff destination and a tailored reply draft. An operator can review and send that draft to the exact original item through an authorised official API connection. Private support continues through the same ticket workflow.

## Start

1. Launch BeLive and open [the staff dashboard](http://127.0.0.1:8877/).
2. Sign in using an account for this database. Obtain local account details privately; there is no shared default password.
3. Use **Connection settings → Test AI connection** and inspect official native Hermes with the configured GPT model.
4. Use an isolated fixture workspace for testing. The browser integration checks mock every platform request; they do not send real replies.

## Collect a permitted review

1. Open **Public reviews → Import a Google review from a link**.
2. Paste an individual Google review Share link from a source you are authorised to read. An individual link is different from the general Maps listing.
3. Select **Import review**. A new capture saves the visible source and queues assessment; an existing match opens without duplicating the case.
4. Select **Open original Google review** and check that it opens the intended individual review.
5. Inspect source evidence and activity. Preserve the difference between raw browser capture, a manual summary and a fresh assessment.

On a prepared installation, choose the labelled saved Google review by topic using your private runbook. Source-link correction preserves the saved case and does not itself rerun analysis. Show the actual saved assessment rather than copying a level from a separate test workspace.

If the page is unavailable, name saved evidence as saved evidence. **Record a public complaint** is a manual fallback; do not call it an automatic crawl.

## Collect Facebook customer comments

1. Save the authorised test Page's token and compatible Graph API version in **System setup → AI & knowledge → Connection settings → Platform API access → Facebook**.
2. Open **Public reviews → Configure platform sources**, select **Facebook customer comments**, and enter `PAGE_ID/feed`. **Look back (days)** starts at 30 and accepts 1–365. If a Facebook source already exists, the form prefills its resource and saved days. Change the days here, confirm this selected source is authorised, and use the same **Save source & start checks** button to update it. The source follows comments under recent posts from that Page; you do not need to enter each new post ID or create another source for a new history window.
3. Use a clearly labelled student test post on the authorised Page. Place the fictional complaint as a comment from a permitted test account, using that account's identity rather than the Page's identity. A Page-authored comment is excluded, as are confirmed replies previously sent by BeLive.
4. Open **Scheduled collection with API access** and press **Collect feedback now**. The same source is also checked on the saved interval while BeLive runs.
5. Under **Discovered complaints**, open a case labelled **Facebook comment**. Inspect its actual comment text and stable source ID. **Open original Facebook comment** opens the exact API-provided comment permalink when available. **Open parent post** is a separate context link. If an exact comment link is unavailable, say so; the parent link is not proof that an individual-comment link was captured.
6. Show the saved **AI assessment**, reason for SIMPLE/MODERATE/HIGH, staff destination and tailored draft on that comment's case. The author is a public commenter whose tenancy is not automatically verified. Keep the reply in preview for a read-only demo; **Send reply to Facebook** is a separate deliberate action that writes publicly.
7. Collect again and compare case IDs/counts. An unchanged comment should reuse its case. The results distinguish items seen, new or changed cases and comments queued for the next check.

The Page check discovers up to 25 Page-owned posts within your chosen number of days and up to 25 top-level comments per post, importing at most 25 new or changed comments per run. Comments must also be within the selected window. Remaining discovered comments wait for another check. Increasing the days does not remove these collection limits or provide complete historical or nested-reply coverage. To monitor one specific post, use `POST_ID/comments`; that selected-post source permits an older parent but reads up to 25 comments within the selected days. **Collection schedule** separately controls how often checks run.

The earlier washing-machine Page-post test remains an earlier **Page post**, not evidence of collecting a customer's comment. Use the newly labelled **Facebook comment** case to demonstrate this corrected workflow. A fictional comment read from the live Facebook API proves collection wiring; it does not prove a real tenant complaint or completed repair.

## Set API collection history for Google and Threads

Use **Public reviews → Configure platform sources → Look back (days)** for any of the three platforms. Enter 1–365 days; 30 is the default. Each platform retains its own entered value when you switch the Service selector. Change the value on the existing source and use the same **Save source & start checks** button. The history window and the interval under **Collection schedule** are separate settings.

- **Google Business Profile reviews:** select the official Google service, use the authorised `accounts/ACCOUNT_ID/locations/LOCATION_ID` resource and choose the days. BeLive reads up to 25 recent reviews and retains those updated within that window, using creation time if an update time is absent. A saved window does not provide API approval or authorisation; verify a real read only after the company connection is available. An individual review-link import remains age-independent, and this setting does not promise a date filter for browser bulk collection.
- **Threads connected account:** select Threads, choose the days and save. The form uses the account already connected by its token, so it does not ask for each new post ID. The account scan covers up to 25 parent posts and 25 top-level replies per parent within the selected days, with up to 25 new or changed replies imported per run. Your account’s own replies are excluded. Existing selected-post sources can retain an older parent; their replies must still fit the chosen window.

The source card shows the saved days and collection limits. Collect twice to check that the same source IDs/text reuse their saved cases. Changing the days does not delete older saved cases or prove that all history was retrieved. Missing or invalid dates are not invented. Keep external replies in preview during the collection test.

An earlier **Threads account reply · earlier test/capture** case came from the connected account itself. Keep it labelled as earlier evidence. Current monitoring excludes that account's own replies, so the next scan can correctly find zero new customer items while the historical case is still visible. Use a permitted different account's comment to test new customer-reply collection; the comment still does not establish a verified tenancy.

## Optional batch collection

**Collect up to 10 reviews** reads visible written low-rated reviews from the selected listing, or individual review links entered one per line. It may return fewer than ten. Repeated content should reopen existing cases rather than create duplicates.

Collection runs in headless Chrome, including when a saved collector profile is used. The measured signed-out test read two unique low-rated reviews from duplicate input. This does not promise every listing is readable or always returns ten. If Google blocks the page, report the limitation; do not bypass login challenges or access controls.

## Explain the assessment

Open **AI assessment** and show:

- Complaint/Enquiry/non-support and relevance.
- Category, SIMPLE/MODERATE/HIGH, and the reason supported by the source.
- Actual agent status, uncertainty and configured staff destination.
- Exact source evidence and immutable history, viewed privately.

| Result | Action |
|---|---|
| Outside support | Exclude praise/unrelated content from the complaint workflow. |
| Supported SIMPLE | Prepare allowed local guidance after checks; no external posting in the rehearsal. |
| MODERATE | AI can assist, while staff reviews substantive handling. |
| HIGH | Staff priority; immediate danger bypasses routine troubleshooting. |

The current measured public rehearsal produced MODERATE and staff handling. That is one actual result, not a required label for every negative review. A low star rating alone does not determine severity.

## Show the automatic reply draft

1. Open **Public reply** after assessment. An eligible confirmed public complaint at SIMPLE, MODERATE or HIGH queues its draft automatically. Show the queued/running status and wait for the current editable draft; no Prepare click is needed. Staff responsibility remains unchanged.
2. Show **Public Reply Preview Agent** separately from **Complaint Analysis Agent**. Analysis and composition are distinct jobs.
3. Explain how the preview acknowledges the reported concern and asks a useful next question. An appliance complaint can ask for its exact brand/model and display code instead of repeating a generic contact-support sentence. Private details stay private and the draft promises no work or resolution.
4. Open **More reply options** to show **Rewrite reply** and **Copy reply**. A failed generation displays **Retry draft**. An earlier saved draft remains labelled as earlier evidence and cannot be sent as the current response.

The measured native run used four model calls across those two roles. It saved a tailored preview and did not send a public response or customer message. Detailed source identifiers and screenshots stay private.

## Review the exact destination before sending

The main action is **Send reply to Google**, **Send reply to Facebook**, or **Send reply to Threads**, according to the selected case. Review the original-source link and editable text before pressing it. That click approves the displayed text; there is no second approval checkbox. Automatic assessment and draft generation never press Send.

- Google requires the exact official review resource, an authorised verified Business Profile location and reply-enabled credentials. A Maps browser import alone cannot enable sending.
- Facebook replies under the exact saved customer comment after checking its configured Page binding, parent-post ownership, recent comment membership and current source text. Earlier explicitly captured Page-post targets retain their separate legacy handling; collection now produces customer-comment cases.
- Threads creates a reply container whose `reply_to_id` is the exact saved complaint, then publishes that container after it is ready. It does not create an unrelated root post or reply to a different parent.

The outcome is saved with an idempotency key. A platform receipt is required for **POSTED**. **PENDING** means a saved Threads container is still processing and can be continued without creating another container. **FAILED** records a rejected or blocked attempt. **UNKNOWN** requires checking the original platform; do not repeat an uncertain write. Sending a public reply does not close the case, change its severity or mark staff work complete.

For a live demonstration, use only an authorised test resource and press Send deliberately. Configured tokens and successful reads do not by themselves establish current write permissions. The automated demonstration harness uses synthetic API receipts and verifies the destination without contacting a platform.

## Continue after the customer provides details

Use **Customer answered? Add their reply** on the same case. Paste the observed customer text and, when available, its original same-platform link. Choose **Update draft with this answer** once. The application records the follow-up, queues the next draft and updates its status automatically. This is a staff-recorded observation, not automatic author identification or evidence that a previous draft was posted.

With an exact supported appliance brand/model and customer-typed error code (or an explicit statement that there is no code), Hermes can search the configured official manufacturer sources. The source-backed draft must pass a separate native safety and model-compatibility check. Open **Manufacturer sources used** to inspect the evidence. Missing details or unavailable matching evidence lead to a focused question rather than an invented fix. HIGH/danger bypasses routine diagnostics. MODERATE cases remain visible to staff while AI gathers details or prepares safe assistance.

The collector does not yet attach an arbitrary later Google/Facebook/Threads item to a customer conversation automatically. Real private WhatsApp support uses its existing same-conversation research workflow. Keep public drafts in preview during testing. These current workflow steps do not replace or rescore the historical four-call rehearsal above.

## Demonstrate reviewed learning

Show a completed test case's reply, checked outcome and reviewed general lesson. Then show the matching lesson in a later request's actual citation and wording. The solved-case rehearsal proves this trace with genuine model replies and explicitly fictional staff outcomes. Same-question baseline and lesson-assisted answers were both useful; no quality percentage is claimed.

Use the [shared operating guide](FYP_DEMO_GUIDE.md) for staff review and closure. Legacy formatting exercises are separate from completed-case knowledge reuse.

## Reproduce safely

```sh
python scripts/rehearse_public_review.py --run-live --capture-ui
```

This deliberately performs real headless reads and native-model calls using an isolated workspace. Provider charges may apply. The default permitted example may change; use `--review-url "INDIVIDUAL_GOOGLE_REVIEW_URL"` to select another authorised source. No old local case IDs are required. If live content is unavailable and no matching saved capture exists, the result is blocked without inventing text or ratings. Without `--run-live`, no live work occurs.

## Explain connection limits

Browser collection does not grant Google Business Profile API access. Scheduled Google, Facebook and Threads scans need permitted resources, credentials and live verification. Connected-account Threads monitoring discovers replies under recent posts in the configured account; it is not platform-wide discovery. A selected-post connection monitors that selected post. A single imported review is not a live subscription to all future replies. A local alert is not a delivered notification. Public sending is available only when the exact-source, current-draft and connection checks pass; actual delivery is established by the saved API result.

See [the rehearsal checklist](FRIDAY_DEMO_CHECKLIST.md) for measured counts and [the results checklist](CHAPTER5_EVIDENCE.md) for non-identifying reporting.
