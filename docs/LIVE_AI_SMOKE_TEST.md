# Real Hermes AI smoke test

Tested on **26 October 2026, 16:05 Malaysia time** using the installed native Hermes AIAgent runtime, **Ollama Cloud**, and **gemma4:31b**. This is a limited live smoke test, not the full 24-case evaluation.

Only clearly fictional property, tenant and support records were used in a separate test database. No real tenant information was sent. No external messages were delivered.

## Results

| Check | Actual result |
|---|---|
| Provider connection through Hermes | PASSED: real response passed the connection JSON/schema check. |
| Fictional recurring Wi-Fi enquiry | COMPLETED; WIFI category, MEDIUM urgency, tenant-response draft produced. |
| Two logical AI stages | Triage and Investigation/Response both returned real provider results. |
| Verified-record reference | The response cited version 1 of the fictional Wi-Fi support note. |
| Fictional electrical smoke/sparks report | CRITICAL and HUMAN_REVIEW before AI troubleshooting. |

## Real requests

| Stage | Provider calls | Elapsed seconds |
|---|---:|---:|
| Connection Check | 1 | 10.09 |
| Triage Agent | 1 | 7.82 |
| Investigation and Response Agents | 1 | 7.95 |

The runtime exposed only `read_case_context` and `read_reviewed_styles`. An allowlisted tool being available does not prove the model invoked it. These requests used inline fictional context; no reusable style examples were loaded.

## Fictional Wi-Fi input

> The Wi-Fi in my room drops every evening. What information should I provide?

## Actual generated draft

> I'm sorry to hear that your Wi-Fi has been dropping in the evenings. To help us investigate this, could you please provide the following information:
>
> 1. Is this happening to one device or several different devices?
> 2. Around what time does the connection usually drop?
> 3. Are there any specific error messages appearing on your screen when it happens?

The draft stayed in `AI_PENDING` for operator review. It was not sent, and the case was not claimed resolved.

## Reproduce locally

1. Configure this project's private `.env` with your authorised model access. On this machine only, the user-authorised old module AI settings were copied into BeLive's own `.env`. The application does not read the old module at runtime.
2. Restart **Run BeLive Prototype.bat**. Sign in as Admin and select **Tenant & property records > Test AI connection**, then refresh for the saved result.
3. In a practice database, add fictional property guidance and a fictional verified tenant, create the Wi-Fi case above and select **Create & assess**. Inspect the assessment, cited record and response draft.
4. For the separate 24-case evaluation, explicitly run `python scripts/evaluate_ai.py --run-live`. That broader evaluation has not been run for this smoke-test report.

## Evidence and limits

Raw local evidence is in ignored `artifacts/live-hermes-2026-10-26/result.json`; fictional test records are in the adjacent `fictional-smoke.db`. The normal operator database was not used or changed for these test cases. The `.env`, raw artifacts and databases are ignored by Git.

This checks real provider connectivity, one English support-generation path, schema/evidence validation and one deterministic safety handover. It does not establish overall accuracy, multilingual quality, production readiness, social-source access or external notification delivery. Other teammates must configure model access on their own machines.
