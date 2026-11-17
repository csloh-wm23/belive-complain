# BeLive Thursday demo

## Start on the demo computer

1. In the BeLive folder, run `python scripts/start_demo_ollama.py`, then `python server.py` if the dashboard is down.
2. Sign in to the [staff dashboard](http://127.0.0.1:8877/) using an account for this database. On a fresh copy, the first person creates the administrator. In **System setup → AI & knowledge → AI & replies**, select **Test AI connection** and wait for **PASSED**.
3. In **AI & knowledge → Demo**, select **Prepare demo data** once. In **AI & replies**, enable routine automation if it is off. Open the [tenant site](http://127.0.0.1:8877/belive) in another tab. Open the complaint form and select **Try demo tenant**.

For a new Windows machine, install Ollama and Hermes, run `ollama pull qwen3.5:4b`, and set these values in the local BeLive `.env` file. Restart BeLive after changing the file.

```
BELIVE_AI_PROVIDER=ollama
BELIVE_AI_MODEL=qwen3.5:4b
BELIVE_OLLAMA_URL=http://127.0.0.1:11435
BELIVE_OLLAMA_KEY=
```

## Loh Chee Seng · public complaints

1. Open **Public reviews**. Select **Collect reviews now** to read recent items from the enabled sources. The result under the button shows each platform's outcome. The scheduler uses the same saved sources and runs while BeLive is open.
2. For the real Google Maps example, expand **Record a public complaint**. Enter the listing link, title and anonymized notes below, then select **Save complaint and assess**. On the rehearsal computer, open the saved case `BL-126E3EF141`.
3. Open **AI assessment** and show the complaint decision, category, supporting report and team. A **SIMPLE** complaint with matching approved guidance can get a draft. **MODERATE** goes to staff for investigation, with AI assistance where appropriate. **HIGH** gets urgent staff attention. An immediate safety signal can enter the staff queue before AI troubleshooting. In rehearsal the Google case was tagged Maintenance / HIGH. Show the actual result if you assess a fresh copy.
4. In **Public reply preview**, select **Generate tailored preview**. The **Complaint Analysis Agent** assessed the report. The **Public Reply Preview Agent** writes a tailored acknowledgement for staff to review. All public replies stay in preview.

Browser-collected example from the [BeLive Google Maps listing](https://www.google.com/maps/place/?q=place_id:ChIJf2EBIq8fMiARfTvF7ZZhmsM).

- **Title** — Google Maps demo - appliance maintenance
- **Link** — `https://www.google.com/maps/place/?q=place_id:ChIJf2EBIq8fMiARfTvF7ZZhmsM`
- **Notes** — A one-star reviewer reported that a water dispenser had no cold water for almost three months, a washing machine was broken, and maintenance complaints received little follow-up.

Live collection depends on a saved, enabled resource and platform access. Google uses an approved Business Profile API project, a verified location resource such as `accounts/ACCOUNT_ID/locations/LOCATION_ID`, and `BELIVE_GOOGLE_TOKEN`. Threads uses a permitted post resource such as `POST_ID/replies` and `BELIVE_THREADS_TOKEN` with reply-read access. Set tokens locally and use **Configure platform sources** as an administrator. The rehearsal computer had zero configured sources. Automated tests exercised one-click and scheduled collection against simulated API responses. The Google example above was collected manually.

## Jackson Tsai Jia Sheng · tenant support

1. In the tenant portal, submit “How can I check a Wi-Fi connection problem on my device?” Show the automatic private SIMPLE reply. Open the staff case and expand **AI assessment** to show **Complaint Analysis Agent → Support Response Agent → Safety Review Agent**. Expand **Source evidence and activity** to show the approved guide/version cited. The tenant can accept the answer or select **Still unresolved** to request staff help.
2. Submit “The fan is broken and needs a repair. What details should I send?” Open the case under **Complaints**. Show the MODERATE rating, assigned team and cautious AI draft. As staff, review the draft before any reply to the fictional tenant. In **AI & knowledge → Staff routing**, show that the category-to-team mapping is approved by the administrator and that blank entries use Support team. Use a fictional team when testing changes on the demo database.
3. Submit “Are pets allowed in my building?” The fictional property has no approved answer for that question. Show the staff handover and absence of an automatic tenant answer. An immediate danger example is “Smoke is coming from my electrical socket.” Open the staff alerts to show the priority.
4. In an administrator account, open **AI & knowledge → AI & replies**. Select the fictional property, add an approved fictional answer and record its source. Open **Manage saved knowledge → Edit knowledge**, correct the wording, reconfirm it and save. Show that the version increases from 1 to 2. Support accounts can handle cases and run collection. Administrators approve knowledge, routing and source settings.

## Both presenters · learning

1. Open **Self-learning → Open the before/after learning lab**. Select **Generate the first reply** using the default Wi-Fi question. Review and confirm the writing lesson, then generate the second reply with the same question and guide.
2. Compare the recorded scores and word counts. The three checks are two numbered points, one clarifying question and at most 90 words. State the actual outcome if a run improves, ties or fails. Measured improvement can keep the reviewed writing lesson for the fictional demo property.
3. Submit a new Wi-Fi question as the demo tenant. In the staff case's **AI assessment**, show **Reviewed lessons used** and the response. The count shows retrieval. Check the wording separately to see whether the reply followed the lesson. The comparison measures reply style and uses the same model.

### Rehearsal evidence

- Local Hermes with Qwen3.5 4B passed the model check. The Wi-Fi question received a private SIMPLE reply, the fan request went to the configured fictional maintenance desk, the unknown pet policy went to staff, and the smoke example went directly to staff. The fictional knowledge entry advanced from version 1 to 2.
- Local comparison LEARN-05A95A9FC2 improved from 2/3 to 3/3 clarity checks, with 58 words before feedback and 40 after. It saved LEARN-05A95A9FC2-STYLE. Later tenant case BL-0D8885D88D retrieved that lesson and another active lesson. Its draft passed all three checks in 36 words and remained in staff review.
- The browser button test imported one simulated Google review and one simulated Threads reply. The scheduler test checked the same two platforms and left a paused source alone. The real one-star Google review was used for AI triage and preview.
