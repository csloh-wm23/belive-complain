# Connect BeLive to hosted Hermes

BeLive can use **Hermes 4 405B** through OpenRouter. The model runs in the cloud. The BeLive app, case database, routing rules and reviewed-reply memory run on your BeLive machine. This option needs Python, Internet access and an OpenRouter key with available credits. It runs without installing Ollama, model weights or the native Hermes Agent runtime.

## Set up the company key

1. Create a project key in the [OpenRouter API keys page](https://openrouter.ai/settings/keys) using BeLive's account.
2. Open the BeLive folder containing `server.py` and `.env.example`. Copy `.env.example` to `.env` if you are setting up a new copy. On Windows, show file extensions so you can confirm the file is named exactly `.env`.
3. Set these three lines in `.env`. Keep your existing database and other settings.

```dotenv
BELIVE_AI_PROVIDER=openrouter
BELIVE_AI_MODEL=nousresearch/hermes-4-405b
BELIVE_AI_KEY=PASTE_BELIVE_OPENROUTER_KEY_HERE
```

Keep the key in the machine's local `.env` or server environment. Git ignores the local file. The key is separate from the BeLive staff login.

## Check the connection

1. Restart BeLive with **Run BeLive Prototype.bat** or `python server.py`.
2. Sign in as an administrator and open **AI & knowledge**, then **AI & replies**.
3. Click **Test AI connection**. Wait for **PASSED** under the OpenRouter model name. The test makes one real call with a neutral prompt and no tenant records.
4. Try a fictional complaint. Check **AI assessment** for the classification, staff route and any draft. The same approval and safety rules apply with the hosted model.

If the check fails, confirm the key, account credits and model access. Missing or rejected credentials and unavailable endpoints leave cases with staff when AI is needed. For case analysis, the server sends relevant report text, guidance and reviewed wording to the hosted provider. It masks recognized email addresses and long numbers, drops internal case metadata where it is unnecessary, and requests a zero-data-retention endpoint. Use fictional data for acceptance testing.

[OpenRouter model and pricing](https://openrouter.ai/nousresearch/hermes-4-405b)

## Use the existing local setup

Existing deployments can keep their current AI provider settings. To use Qwen locally, see [the local Ollama rehearsal guide](THURSDAY_DEMO.md). The earlier [native Hermes and Ollama Cloud smoke test](LIVE_AI_SMOKE_TEST.md) describes a separate setup.
