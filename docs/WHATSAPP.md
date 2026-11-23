# Passive WhatsApp support

The actual conversational executor is official native Hermes `AIAgent`, using the configured GPT model. Install it with **Install Hermes Agent.bat**; [engine details and execution evidence](NATIVE_HERMES.md) describe the boundary between the Agent, model, approved memory and delivery layer.

## Tenant Report on the BeLive website

In **Tenant reports · WhatsApp**, save the approved public company number under **Tenant Report website entry**. This requires an administrator; customers do not sign in or provide a tenant code. The public `/belive` site opens the company WhatsApp chat with a short topic message, and the customer presses Send in WhatsApp. Opening the link alone does not create a case or send a message. Existing website complaints remain accessible using Track complaint and the website form.

The link and the AI channel are separate: `wa.me` only opens a chat. The dashboard shows whether API setup is missing, whether a real incoming message was received, whether Meta accepted Hermes's reply, and whether delivery was confirmed for the same public business number. Configuring credentials, running a simulation or merely opening WhatsApp never counts as a verified live connection. Public visitors see that automatic replies are still being connected until real delivery is observed.

Once connected, signed customer messages create cases and run the existing conversational, SOP/experience retrieval, photo, research and staff-guidance agents automatically. A staff solution entered in the backend is private guidance; Hermes adapts and sends the customer-facing reply. Staff review of every ordinary answer is not required. The generic website intake route remains a fallback, rather than pretending to deliver a WhatsApp message.

## Keep the WhatsApp Business mobile app

An already-registered mobile Business app number needs Meta's supported **Coexistence** onboarding if the app is retained. The ordinary Cloud API number-registration screen can reject that number. Do not delete the mobile account, unregister the number, invent business verification details or repeat OTP attempts to work around this distinction. The current program has Cloud API message handling and coexistence mobile-message echo support; it does not claim to grant Tech Provider approval or complete Embedded Signup automatically. Meta approval/onboarding or an authorised coexistence provider and a live HTTPS webhook are still prerequisites for the real number.

Subscribe to `messages` and `smb_message_echoes` through the approved integration. Echoes of occasional mobile staff messages are recorded as staff context, not new customer complaints, and never trigger an unsolicited AI response. A matching AI message echo is deduplicated; historical sync events do not create fresh cases. Phone viewing does not create an echo. Mobile staff replies supersede pending AI drafts; the next customer message resumes the conversation with that context. This does not implement a technical read-only lock in the mobile app.

Official requirements: [Coexistence onboarding](https://developers.facebook.com/documentation/business-messaging/whatsapp/embedded-signup/onboarding-business-app-users), [mobile message echoes](https://developers.facebook.com/documentation/business-messaging/whatsapp/webhooks/reference/smb_message_echoes).

Open **WhatsApp inbox**. The private conversation is the primary passive-support flow. Existing website cases and public-review features remain available with their data intact.

## Try locally now

1. Expand **Test a conversation safely**. Use a fictional customer reference. Send `bro the wifi so suck`, then explain what you already tried. Optionally attach a JPEG, PNG or WebP photo (up to 5 MB).
2. The same customer reference continues the same private thread. A different reference creates an isolated thread. Simulations are clearly labelled and **never call Meta**, even when real credentials are configured.
3. Paste verified company SOP under **Company-approved SOP**. Include the source/reviewer. Leave property blank for company-wide rules. A property-specific SOP is retrieved only when staff assigns that exact property in the conversation.
4. If AI needs staff, its internal question appears in the thread. Staff enter the verified solution, confirm it and click **Ask AI to reply**. The internal note is not copied directly to the customer: AI uses the conversation and verified instructions to compose a reply. AI continues acknowledging customer messages while staff guidance is pending.
5. Expand a reply's **AI activity and sources** to see research links, SOP/staff evidence IDs and delivery state. `SIMULATED` means local test only; `ACCEPTED` means Meta accepted the send; `DELIVERED`/`READ` require signed WhatsApp callbacks.

## Company connection required for real customers

Ask the authorised company administrator for access to its Meta app and WhatsApp Business Account, a Cloud API-enabled business phone number, its **Phone Number ID**, a server-side access token authorised for WhatsApp messaging, the app's **App Secret**, and the supported Graph API version. Do not paste secrets into chat. Put them in the project's ignored local `.env`, using the keys in `.env.example`. Generate a separate random verify token for webhook setup.

The company must also supply approved tenancy/SOP material, confirm its official website domain and nominate the staff/maintenance notification destination. Account and business verification, phone registration, token permissions and production access are configured in Meta by its authorised administrator.

Real inbound messages need a reachable **public HTTPS webhook** at `/webhooks/whatsapp`, plus `BELIVE_WHATSAPP_WEBHOOK_HOST` set to that exact host. This app intentionally remains bound to localhost. An authorised HTTPS reverse proxy must forward **only this webhook path** to the local service; never expose the operator dashboard, `/api`, media, `.env` or database. Use Meta's webhook verification screen and subscribe to WhatsApp `messages` events. The GET challenge checks the verify token; POST checks the raw-body `X-Hub-Signature-256` and business phone ID.

This change does not register a business account, create a public tunnel, or send a real WhatsApp test. Once the company credentials and HTTPS endpoint exist, test with an authorised company test number: send text/photo, inspect receipt callbacks, repeat the same webhook to verify deduplication, then give staff instructions and confirm the AI reply reaches the same number.

## Reply behaviour

AI uses conversation meaning and customer language/tone, without mirroring abuse. It requests location only when relevant, remembers provided details, and avoids repeating unsuccessful suggestions. Verified company SOP and staff instructions govern company responsibility, fees and commitments. Public website/manufacturer information cannot override those terms.

Photo analysis extracts visible brand/model/error text, marks uncertainty and does not itself diagnose a fault. Technical research uses the OpenAI Responses web-search tool with official-domain allowlists and cited sources. It uses generic appliance/topic queries rather than customer conversations/photos; unreadable model numbers or unclear error codes require clarification. If a source is unavailable or unsafe, AI acknowledges the customer and requests staff guidance. Online research and photo/text inference may consume OpenAI credits.

Maintenance requests queue a `STAFF_WORK_ORDER` in **Messages**. They are not proof a contractor has been contacted: the existing approved notification gateway must be configured and its delivery checked. Electrical/gas/hazard reports receive immediate safety acknowledgement and urgent staff escalation.

## Reliability and privacy

Each business/sender pair has an isolated thread. Meta message IDs are idempotent. A burst of incoming fragments is combined into the latest context. Inputs/SOP changes during generation supersede stale replies. Messages, verified SOP versions, photo observations and source links are persisted in the selected local database; photos are stored beside it in `whatsapp_media` and require staff login to view. Include both in company backup/retention procedures. Raw phone numbers and credentials are not returned in the dashboard snapshot.

Free-text replies are only sent within the 24-hour customer-service window. Outside it the reply is marked `NEEDS_TEMPLATE`; this prototype does not send approved templates. Uncertain sends are marked `UNKNOWN` and are not automatically retried. Reopen/retry only after checking Meta to avoid duplicate customer messages.

Existing feedback learning captures dissatisfied follow-ups after an actual AI reply. Reviewed, approved relevant writing tips can improve later WhatsApp replies; these tips cannot create new company policy or operational facts. This is retrieval and feedback learning, not model weight training.

## Company PDF references and house rules

Open **WhatsApp inbox → Company-approved SOP** to view imported company references. Each document shows its template status and points requiring clarification. Each knowledge section retains its original page excerpts, page numbers, clause references and version. **Download original PDF** requires staff authentication; the source is never a public static file.

Relevant sections are selected by conversation meaning, including short follow-ups. Normal rule questions can be answered without a tenant code, identity check or room number. Affected locations are requested only for an actual physical issue or property-specific information. General template guidance does not establish any particular customer's signed lease, rent, dates or liability.

Sections have three response policies: **General rule** (AI can explain), **Staff decides** (individual actions, approvals, fees and blame require verified staff direction), and **Needs company clarification** (conflicting clauses cannot be silently reconciled or resolved through public web search). AI still acknowledges the customer when seeking staff guidance. Replacement price tables do not prove tenant fault or create automatic bills; good-faith complaints remain accepted.

Verified staff instructions to collect customer details are relayed without immediately creating another staff request. The system waits for the customer's answer; genuinely new conflicting facts can reopen the staff task. Direct customer requests to speak to staff are honoured even while AI asks for missing details; informational questions that merely mention staff are not automatically handed over. A draft rejected by the evidence review gets one bounded revision using that feedback before falling back to staff.

**Disable document** excludes all its sections from future replies without deleting audit history. An individual section can also be disabled. Queued replies are checked against source versions and document status before delivery; revoked or changed knowledge supersedes an unsent reply. Existing sent messages retain their evidence snapshots. Polling does not collapse source excerpts while staff are reading them.

The reviewed import tool is `scripts/import_company_sop.py`. It requires a private PDF, a reviewed JSON manifest with exact page excerpts, and explicit confirmation. It verifies every excerpt against the extracted page and deduplicates the document/manifest. Use the bundled PDF Python runtime or install `pypdf` for this one-time import; the normal server has no extra PDF dependency. Raw PDF text is never treated as system instructions or automatically approved operational policy.

Documents are stored beside the selected database in `company_documents`; reviewed manifests and extraction files should remain in ignored private storage such as `data/knowledge_import`. Back up the database and its document/media directories together. A database-only recovery into another directory will not copy PDF/media files. Obtain permission to send selected support text to the configured model provider before live model testing or production use; do not send entire PDFs, account details or SOP excerpts to public web search.

References: [Meta webhook signature verification](https://developers.facebook.com/docs/graph-api/webhooks/getting-started/), [Meta media API](https://developers.facebook.com/documentation/business-messaging/whatsapp/reference/media/media-api), [OpenAI web search](https://developers.openai.com/api/docs/guides/tools-web-search), [OpenAI image inputs](https://developers.openai.com/api/docs/guides/images-vision).
