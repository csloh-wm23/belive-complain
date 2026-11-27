# Public-monitoring presenter guide

Your part starts with a selected permitted public source and ends with a saved complaint, an explained decision, a staff destination and a tailored reply preview. Private support continues through the same ticket workflow.

## Start

1. Launch BeLive and open [the staff dashboard](http://127.0.0.1:8877/).
2. Sign in using an account for this database. Obtain local account details privately; there is no shared default password.
3. Use **Connection settings → Test AI connection** and inspect official native Hermes with the configured GPT model.
4. Keep external platform replies in draft/preview throughout testing.

## Collect a permitted review

1. Open **Public reviews → Import a Google review from a link**.
2. Paste an individual Google review Share link from a source you are authorised to read. An individual link is different from the general Maps listing.
3. Select **Import review**. A new capture saves the visible source and queues assessment; an existing match opens without duplicating the case.
4. Select **Open original Google review** and check that it opens the intended individual review.
5. Inspect source evidence and activity. Preserve the difference between raw browser capture, a manual summary and a fresh assessment.

On a prepared installation, choose the labelled saved Google review by topic using your private runbook. Source-link correction preserves the saved case and does not itself rerun analysis. Show the actual saved assessment rather than copying a level from a separate test workspace.

If the page is unavailable, name saved evidence as saved evidence. **Record a public complaint** is a manual fallback; do not call it an automatic crawl.

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

## Show the separate reply agent

1. Open **Public reply preview** and choose **Prepare reply** (or **Rewrite reply** for an earlier saved draft).
2. Show **Public Reply Preview Agent** separately from **Complaint Analysis Agent**. Analysis and composition are distinct jobs.
3. Explain how the preview acknowledges the reported concern and asks a useful next question. An appliance complaint can ask for its exact brand/model and display code instead of repeating a generic contact-support sentence. Private details stay private and the draft promises no work or resolution.
4. Leave the public publish control disabled during testing.

The measured native run used four model calls across those two roles. It saved a tailored preview and did not send a public response or customer message. Detailed source identifiers and screenshots stay private.

## Continue after the customer provides details

Use **Customer answered? Add their reply** on the same case. Paste the observed customer text and, when available, its original same-platform link. Choose **Rewrite reply** once; it records the follow-up and then prepares the next draft. This is a staff-recorded observation, not automatic author identification or evidence that a previous draft was posted.

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

## Explain what is still blocked

Browser collection does not grant Google Business Profile API access. Scheduled Google, Facebook and Threads scans need permitted resources, credentials and live verification. A single imported review is not a live subscription to all future replies. A local alert is not a delivered notification. Public replies stay in preview.

See [the rehearsal checklist](FRIDAY_DEMO_CHECKLIST.md) for measured counts and [the results checklist](CHAPTER5_EVIDENCE.md) for non-identifying reporting.
