# BeLive prototype architecture and workflow

## Independent project

This folder is a new project. Existing application concepts informed the design, but no code, database, credentials, runtime configuration or memory store is imported from the phone-services project. The original project remains separately runnable.

## Reference

User-provided flowchart: [belive.drawio](https://drive.google.com/file/d/1BRdI1kpsHiRGnWtCuAiOt1QkXtecpowc/view).

The overall diagram has external monitoring, internal intake, a Hermes complaint engine, follow-up/verification, learning and management visibility. The attached conversation calls for individual modules with shared memory. This prototype covers the complaints module; sales and marketing are not built or connected. Source-document instructions do not authorize external actions.

## Components

- `server.py`: standard-library localhost static server, serving only application assets. No POST endpoint or external connector.
- `index.html`, `assets/style.css`: responsive screens and forms.
- `assets/app.js`: navigation, browser persistence, export, dialogs and operator interactions.
- `core.mjs`: framework-independent case state machine, input checks, basic redaction, feedback and activity records.
- `tests/core.test.mjs`: transition gates, duplicate protection and memory revocation checks.

## State machine

Operator intake starts at NEW, or HUMAN_REVIEW for HIGH/CRITICAL priority. Staff acknowledgement moves either to IN_PROGRESS. A nonempty action note moves to FOLLOW_UP. An unresolved case returns to HUMAN_REVIEW. Verification evidence moves FOLLOW_UP to VERIFIED; only VERIFIED cases can close. Reopening a CLOSED case returns it to HUMAN_REVIEW and revokes its old memory example.

All priorities and evidence are operator assertions. There is no simulated AI response presented as live analysis, independent customer verification, notification, autonomous action or claimed external resolution.

## Learning contract

Feedback applies after local closure. APPROVED reuses saved wording; CORRECTED uses the operator's correction; REJECTED removes reuse. The most recent feedback entry per case controls inclusion. All previous entries remain in local state. Reusable content is masked for email addresses and phone/long number patterns, and labelled as style guidance. Other identifying details need operator review. Browser data can be changed outside the application; this is not a production integrity boundary.

## Storage and failure behavior

State writes are staged in a clone and committed to localStorage before replacing displayed state. If storage fails, the action reports an error. Corrupt or unsupported saved data triggers a read-only temporary sample view so the original stored string can be exported. A storage change from another tab blocks further editing until reload. Reset requires confirmation and affects only this project's localStorage key.

## Future integration boundaries

A real implementation would replace prototype data with a dedicated datastore, immutable source versions, validated structured AI output, native Hermes tool allowlists and isolated supported MemoryStore persistence. Staff notification, business actions and customer follow-up require separately implemented authorisation, idempotency and outcome recording. Cross-module memory would need scoped access and provenance; the current browser example list is not that service.
