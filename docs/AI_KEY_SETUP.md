# Add the AI key and test BeLive

This guide is for the independent BeLive tenant-support prototype. The verified setup uses **Ollama Cloud**, **gemma4:31b** and the installed native **Hermes** runtime. The API key is separate from the BeLive operator username/password.

## What your friend needs

- The latest [BeLive repository](https://github.com/csloh-wm23/belive-complain), downloaded and extracted, or an updated clone.
- Python 3.11 or newer.
- Native Hermes installed, with the `hermes` command available on PATH and its Python runtime present. The key alone does not install Hermes. You can check command availability with `Get-Command hermes` in PowerShell.
- Internet access and an authorised Ollama Cloud API key. If the owner shares their key, calls use that owner's account access/quota.

## Easiest method: use the private settings file

1. Ask the owner to send **BeLive-AI-settings.env** through a private channel. It contains the real key. It is deliberately absent from this public repository.
2. Open the extracted BeLive project folder containing **server.py**, **.env.example** and **Run BeLive Prototype.bat**.
3. In File Explorer, enable **View > Show > File name extensions** so you can check the full filename.
4. If this folder has no `.env` file, copy the private settings file here and rename that copy to exactly **.env**. It must sit beside `server.py`, not inside `belive/`. Do not leave it named `.env.txt`.
5. If `.env` already exists, open both files in Notepad and replace only the five `BELIVE_...` AI settings shown below. Keep your other settings.
6. Save and close the file. The API key goes in `.env`, not the Resource field, operator password box or tenant portal.

## Manual method: paste the key

Copy `.env.example` in the project folder and rename the copy to `.env`, or edit your existing `.env`. Set these five entries; replace the placeholder with the real key received privately:

```dotenv
BELIVE_AI_PROVIDER=ollama
BELIVE_AI_MODEL=gemma4:31b
BELIVE_AI_KEY=
BELIVE_OLLAMA_URL=https://ollama.com
BELIVE_OLLAMA_KEY=PASTE_THE_REAL_OLLAMA_KEY_HERE
```

- Keep `BELIVE_AI_KEY` empty for this Ollama setup. The secret belongs in **BELIVE_OLLAMA_KEY**.
- Keep the URL exactly `https://ollama.com`; the application adds `/v1` itself.
- Paste the key on one line, without the placeholder, extra quotes or spaces.

## Run and confirm

1. Stop any running BeLive Python server with **Ctrl+C**, then double-click **Run BeLive Prototype.bat**. Keep its Python window open.
2. Open **http://127.0.0.1:8877** on the same computer. On an empty database, create your own admin username, display name and password. No default account is supplied.
3. Sign in as Admin. Open **Tenant & property records > Test AI connection**.
4. Wait and select **Refresh** to see **PASSED** or **FAILED**. The check makes a real model request and may use provider credits/quota. The configured badge alone does not prove a successful call.
5. If it passes, follow the [teammate quick guide](TEAMMATE_GUIDE.md) to add fictional DEMO records and create a Wi-Fi support case. Check its **AI assessment & proposed assistance** and response draft.

## If it fails

- **AI setup required / AI_NOT_CONFIGURED:** check that `.env` is beside `server.py`, that the file extension is correct, the model/key entries are populated and Hermes is available. Restart after editing.
- **AI_CONNECTION_FAILED:** check the key, model access, account quota and Internet connection. The presence of a key does not prove it is valid. The prototype intentionally shows a generic error rather than leaking provider details.
- **Records missing:** each computer uses its own local database. Sharing an API key does not share tenant records or login accounts.

The [live smoke-test report](LIVE_AI_SMOKE_TEST.md) records a real successful check on 26 October 2026. Each teammate still needs to verify their own connection. Never upload the private settings file, `.env`, API key or tenant database to the public repository.
