# BeLive tenant support

A separate university prototype for existing-tenant enquiries and complaints. Public monitoring and private support feed one ticket queue with approved knowledge, staff handover, outcome tracking and reviewed learning. Marketing, sales, owner services and move-in/out operations are outside this application.

Production AI executes through official native Hermes **`run_agent.AIAgent`**. **OpenAI GPT-6 Luna** is the configured model provider. A missing or failed native runtime never silently falls back to direct GPT generation. See [native setup](docs/NATIVE_HERMES.md) and [system behavior](docs/FORUM_SYSTEM.md).

## Start here

1. Run **Install Hermes Agent.bat** once on a fresh computer.
2. Run **Run BeLive Prototype.bat** and open [the local staff dashboard](http://127.0.0.1:8877/). Keep the server running.
3. Create an administrator for this database on first launch. There is no shared default username or password. Later installations need their own account and authorised model connection.
4. Open **System setup → AI & knowledge → Connection settings**, save the permitted model settings, then select **Test AI connection**. A configured indicator is not a passed connection test.
5. Obtain the reviewed-knowledge archive and matching recovery key privately. Place the archive at `knowledge/team-memory.enc.json` before using **Self-learning → Team knowledge backup → Restore on another computer** to import the key. The source repository supplies neither file, credentials nor customer data.

Native Hermes and encrypted local storage need the dependencies checked or installed by the launchers. An already configured installation can also run `python server.py`. See [AI setup](docs/AI_KEY_SETUP.md), [private connection settings](docs/CREDENTIAL_SETTINGS.md) and [private knowledge transfer](docs/SHARED_MEMORY.md).

Use the [plain-language operating guide](docs/FYP_DEMO_GUIDE.md), [public-monitoring guide](docs/LOH_PUBLIC_COMPLAINT_DEMO.md) and [rehearsal checklist](docs/FRIDAY_DEMO_CHECKLIST.md). Public documentation uses presenter roles and generic examples; detailed private evidence and account information must stay outside Git.

## Two entry points, one support queue

| Workflow | What happens | Limit |
|---|---|---|
| Public monitoring | A selected permitted public source is collected, assessed and routed. A separate agent prepares a source-specific reply preview. | Public responses remain drafts/previews during testing. Browser reads and scheduled official-API reads are separate. |
| Private support | A tenant messages the configured company WhatsApp channel. The website is the internal staff dashboard and contact entry. | Real messages and same-chat replies require authorised Meta onboarding and delivery evidence. The local simulator is QA only. |

The [contact website](http://127.0.0.1:8877/belive) opens the configured company chat. Opening the link sends nothing and does not prove the AI channel is connected. Retained website complaints use private browser-scoped tracking; that fallback is separate from WhatsApp support.

## Automatic replies and staff responsibility

- **SIMPLE:** supported informational assistance can be automatic after evidence and safety checks.
- **MODERATE:** AI assesses and prepares assistance; the customer receives an acknowledgement while substantive content remains a private staff draft.
- **HIGH:** staff takes priority. Immediate danger bypasses routine AI troubleshooting.
- **Uncertain, unsupported or failed:** hand over to staff without inventing policy, repair findings, appointments or completed work.

Verified internal staff instructions can be adapted and relayed by Hermes after review. Staff still performs physical work, supplies operational facts and verifies outcomes. Queued replies recheck current case and knowledge state before sending, so an old draft cannot ignore later escalation or withdrawal.

## Reviewed learning

After a case is checked and closed, staff can approve a redacted general lesson from its actual reply. A later matching request retrieves current approved experience and shows its citation. Rejection, reopening or source withdrawal revokes reuse. Customer dissatisfaction can also prompt a reviewed writing improvement, while unfinished service work still needs staff.

This is reviewed retrieval and reuse, not model-weight retraining. A different reply or a higher formatting score does not establish better support or customer satisfaction. Compare the same question, inspect the matched lesson and check whether the later reply actually uses it. Keep SAMPLE / TEST provenance visible.

## Rehearse safely

The following opt-in scripts use isolated labelled workspaces. They require an authorised native-model connection and can consume provider credits:

```sh
python scripts/rehearse_native_support.py --run-live --phase all
python scripts/rehearse_public_review.py --run-live --capture-ui
```

Without `--run-live`, they explain the operation without live work. The support rehearsal tests staff-guidance relay, completed-case learning, photo observation and bounded official-source research. The public rehearsal reads selected public content headlessly, checks duplicates and saves assessment/preview evidence without posting. `--review-url "INDIVIDUAL_GOOGLE_REVIEW_URL"` selects a different permitted source. A blocked page without a matching saved capture produces an honest blocked result, not invented review content.

Private model settings from the selected database are used in memory; credentials are not copied into rehearsal outputs. Reports, screenshots, customer text and local account details stay in ignored private storage. Use topic-labelled rehearsal conversations rather than assuming another computer has the same local case identifiers.

## Verification and current limits

The current regression suite passed **297 tests**, with zero failures, errors or skips. Headless checks passed for WhatsApp, company knowledge, connection settings, complaint handling and reviewed learning. Genuine native rehearsals separately recorded 15 model calls across three policy scenarios, 35 across learning/photo/research, and four across public analysis/preview. These are execution counts, not accuracy or satisfaction scores. See the [non-identifying results checklist](docs/CHAPTER5_EVIDENCE.md).

```sh
python -m unittest discover -s tests -p "test_*.py" -v
```

Browser QA requires Playwright and Chrome:

```sh
python -m pip install -r requirements-dev.txt
python tests/browser_check.py
python tests/browser_complaint_flow.py
```

Real company WhatsApp delivery remains unverified. Scheduled Google Business Profile, Facebook and Threads reads still need authorised resources, permissions, credentials and live scans. External staff notifications require a verified gateway receipt. Public replies stay in preview. The app listens on loopback; a public repository does not host it.

## Private configuration and recovery

Encrypted database overrides belong to that local database. A separate private credential key unlocks them; the team knowledge recovery key serves a different purpose. `.env` remains a field-level fallback. Neither keys nor customer databases belong in Git. See [connection settings](docs/CREDENTIAL_SETTINGS.md).

Before pulling an update, export reviewed knowledge and preserve the archive plus its matching recovery key outside the checkout: older source versions tracked the archive, while new source updates remove it. Retain your own `.env`, `data`, database and private credential key. After pulling, copy the private archive back to `knowledge/team-memory.enc.json`, then restore through **Self-learning → Team knowledge backup**. See [the migration and private transfer steps](docs/SHARED_MEMORY.md).

GitHub carries code only. Never commit or upload the archive or either key. Later approved knowledge is shared by exporting and privately transferring the archive, not by pulling code. This is manual exchange, not real-time synchronisation. Private full-database recovery remains a separate paused-workspace operation.
