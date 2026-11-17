# BeLive demo rehearsal

## Start on the demo computer

1. Run `python scripts/start_demo_ollama.py` from the BeLive folder. This checks that local Ollama has Qwen3.5 4B and starts the demo inference endpoint if needed.
2. Start BeLive with `python server.py` if it is not running. In **AI & knowledge**, use **Test AI connection** and wait for **PASSED**. Have the model loaded before the audience arrives.
3. Open the local tenant site at `http://127.0.0.1:8877/belive` and staff dashboard at `http://127.0.0.1:8877/`. Use the fictional demo tenant and an existing local operator account.

To reproduce on another Windows PC, install Ollama and Hermes, download the model with `ollama pull qwen3.5:4b`, and configure these entries in the local BeLive .env file:

```
BELIVE_AI_PROVIDER=ollama
BELIVE_AI_MODEL=qwen3.5:4b
BELIVE_OLLAMA_URL=http://127.0.0.1:11435
BELIVE_OLLAMA_KEY=
```

## Show the tenant and staff workflow

1. Submit a routine question: “How can I check a Wi-Fi connection problem on my device?” Show the automatic private reply and the tenant feedback controls.
2. Submit “The fan is broken and needs a repair. What details should I send?” Open the MODERATE case in staff view, show the private AI draft, review the wording, and send it as staff.
3. Submit a fictional immediate safety report involving smoke from an electrical socket. Open **Alerts** and show that it enters the staff queue immediately.
4. Open **Reports & activity**. Explain that the unchanged-draft ratio counts reviewed AI drafts actually sent, and verified closure is recorded by staff. Show the **My assigned cases** filter if presenting staff ownership.
5. In **Self-learning**, open the before/after learning lab. Show a saved comparison, then explain when a reviewed lesson is reused. If running a new comparison, report the actual result, including a tie or a failed check.

The Google, Facebook and Threads regression tests use simulated API responses. A live scan requires authorized source IDs, platform credentials and the matching API permissions. Manual intake from a link can demonstrate case handling, but it does not show an API read. External notifications require their configured delivery service. Use the in-app staff alerts for the local walkthrough.

## Google Maps complaint walkthrough

This is an anonymized paraphrase of a one-star review collected in a browser from the [BeLive Google Maps listing](https://www.google.com/maps/place/?q=place_id:ChIJf2EBIq8fMiARfTvF7ZZhmsM). Use the public complaint link intake in the staff dashboard.

- Title: Google Maps demo - appliance maintenance
- Source: https://www.google.com/maps/place/?q=place_id:ChIJf2EBIq8fMiARfTvF7ZZhmsM
- Complaint: A one-star reviewer reported that a water dispenser had no cold water for almost three months, a washing machine was broken, and maintenance complaints received little follow-up.

Open the imported case after assessment. In rehearsal the local AI identified Maintenance and rated the case HIGH, routing it to staff. The model's rating can vary, so show the actual assessment on screen. The HIGH route uses a standard private-contact draft. To show a tailored response, enter and save this staff draft in the case:

> Thanks for reporting the washing machine and water dispenser issues. Could you send us a private support request with your building name and the affected appliances? That will help our team look into it. Please leave your unit number and contact details out of the public review.

This walkthrough uses a browser-collected sample and a staff draft preview. The dashboard saves each imported case in the local database. Jackson should import the sample on his own copy.
