# Customer support operations

Customer Support now shows observed progress for each customer question, separately from message delivery and final resolution. A useful reply to a fault means waiting for the customer, not a repaired issue. Meta acceptance is shown as waiting for a delivery receipt. Staff and photo continuations retain their original-message references.

The active-work display follows actual processing stages: checking rules, reading a photo, assessing the question, checking official sources, drafting and independent review. A long-running operation shows elapsed time instead of asking the customer to resend. The official WhatsApp typing/read indicator is best effort while a real native-Hermes response is pending. It sends no answer text, is never used for simulation, stops after bounded time, and failure does not block a reviewed answer. Meta documents the mechanism at https://developers.facebook.com/documentation/business-messaging/whatsapp/typing-indicators .

Native processes can remain warm for subsequent requests, scoped by customer, agent role, runtime, credentials and tool allowlist. Each request constructs a fresh AIAgent and reloads current approved memory/tool evidence. This caches neither answers nor withdrawn knowledge, and keeps the independent reviewer. Online lookup and model time remain variable.

Automatically scheduled feedback analysis waits while current WhatsApp turns are pending or processing, then resumes during idle scheduler checks. This preserves learning without starting extra background model work ahead of a waiting customer. Already-running provider calls cannot be preempted. First use, process eviction and expiry of the bounded warm cache still incur startup time.

## Internal maintenance queue

1. Hermes records the physical issue, available property/room and priority. Routine work needs the location before internal acceptance. Urgent cases can be accepted while essential details are collected.
2. Open **Maintenance queue**. Accept internally to record ownership, then start work or record a blocker. Checked progress notes can be updated without pretending work is complete.
3. Record **Work done** only with checked evidence. This records the staff report, not customer satisfaction, final issue closure, external dispatch or a visit booking.
4. The customer can ask for progress. Hermes reads the checked update for that issue and cites it through its native evidence tool and independent reviewer. It must not request the same update again or treat a SOP as proof of a particular job's progress.
5. Use **Staff help** to give Hermes any further verified next steps or outcome. Confirm the customer's response before finishing a real issue. Use **Test completed** for rehearsals.

These commands do not contact an external maintenance service or send an automatic customer message. Real destinations and external delivery remain unconfigured. Internal reminders appear after 24 hours for routine work, 2 hours for urgent work and 15 minutes for emergencies without a checked progress update. They are internal attention flags, not customer appointment promises.

Work-stage updates require a fresh issue revision and checked note. Queued or unconfirmed sends prevent unsafe concurrent changes. Changes during generation force a fresh response against current staff evidence. A new unresolved report after recorded work can return that job to the internal queue, preserving its work history.

## Learning and connection evidence

Staff help includes the factual problem summary, original customer message, latest update and sources already checked. Staff instructions and work notes stay issue-specific; they do not become public SOP or reusable lessons automatically.

WhatsApp feedback uses an explicit quoted AI reply before chronological fallback. The selected reply's original customer question accompanies it into the existing learning-review process. An unresolved/unavailable quote is not guessed against another issue. Proposal, staff approval and revocation checks remain unchanged, and a repair failure can require service action rather than a writing tip.

Connection readiness and historical delivery remain separate. The startup live-test proof now requires a native Hermes reply delivered for a correlated real customer message received after startup on the configured company phone ID. A reply to yesterday's message, simulation, direct/test executor or unrelated receipt cannot satisfy that test. Latest delivery state and observed preparation time are shown separately.

Customer records remain empty until the company supplies data; these changes do not enable phone matching or populate that directory.
