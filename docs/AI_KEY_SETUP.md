# Connect BeLive to GPT-6 Luna

GPT-6 Luna is the default for a new BeLive setup. The model runs on OpenAI. BeLive runs the complaint workflow and stores cases and reviewed replies in its own database. The hosted setup uses Python, Internet access and an OpenAI API project with available credits.

## Set up the project key

1. Create a key in your [OpenAI API project](https://platform.openai.com/api-keys). For the company handover, use BeLive's own API project.
2. Open the BeLive folder containing `server.py`. Copy `.env.example` to `.env` if there is no `.env` yet. On Windows, show file extensions to confirm the file is named exactly `.env`.
3. Set these four lines in `.env`. Keep the other entries.

```dotenv
BELIVE_AI_PROVIDER=openai
BELIVE_AI_MODEL=gpt-6-luna
BELIVE_DECISIONS_ENABLED=true
BELIVE_AI_KEY=PASTE_YOUR_OPENAI_PROJECT_KEY_HERE
```

Store the key in the machine's local `.env` or server environment. Git ignores the local file. Use your existing BeLive staff credentials to sign in to the app.

## Check the connection

1. Restart BeLive with **Run BeLive Prototype.bat** or `python server.py`.
2. Sign in as an administrator and open **AI & knowledge**, then **AI & replies**.
3. Click **Test AI connection**. Look for **PASSED** under `openai / gpt-6-luna`. The check sends a neutral prompt with no tenant records and may use API credits.
4. Submit a fictional complaint and open **AI assessment**, then **Decisions assessment** to see the message type, topic, level and model estimates. The response agent writes a draft using approved knowledge. Safety and staff-routing rules apply before any automatic SIMPLE reply.

## Learn from customer responses

Open **Self-learning** and find **Improve replies from customer feedback**. When a customer replies after a support answer, Luna checks the exchange for frustration, dissatisfaction or positive feedback. It proposes a writing tip when the exchange shows a problem. Staff can edit and approve the tip, then select **Test improved reply** to compare the original with an unsent new draft. Future matching replies retrieve the approved tip automatically. Each card shows how many replies received the tip and how many later received positive or dissatisfied feedback. Check the source conversation to verify what happened.

If the check fails, confirm the key, project credits and model access. BeLive sends cases that require unavailable AI to staff. The model receives relevant complaint text, guidance and reviewed writing examples during case analysis. Use fictional reports to verify the setup.

[GPT-6 Luna model and pricing](https://developers.openai.com/api/docs/models/gpt-6-luna)

## Other model setups

The hosted OpenRouter setup uses `BELIVE_AI_PROVIDER=openrouter`, `BELIVE_AI_MODEL=nousresearch/hermes-4-405b` and an OpenRouter key in `BELIVE_AI_KEY`. To run Qwen on this computer, follow the [local Ollama guide](THURSDAY_DEMO.md).
