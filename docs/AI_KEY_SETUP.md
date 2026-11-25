# Configure native Hermes and its model

Production support uses official native Hermes `run_agent.AIAgent` with OpenAI GPT-6 Luna as the model provider. Internet access, an authorised API project and provider credits are required. Private customer data, credentials and reviewed company documents are not distributed through source code.

## Install once

Run **Install Hermes Agent.bat**, then **Run BeLive Prototype.bat**. The installer checks official Agent/MemoryStore imports in the project runtime. See [native setup](NATIVE_HERMES.md). Missing native Hermes must fail honestly rather than silently use direct GPT transport.

## Save a private connection

1. Sign in as an administrator for the active database.
2. Open **System setup → AI & knowledge → Connection settings**.
3. Choose provider `openai`, model `gpt-6-luna`, and enter an authorised model key privately.
4. Select **Save connection settings**, then **Test AI connection**.
5. Wait for the actual result and inspect native execution evidence. A configured field alone is not a passed test.

Secret fields are blank on readback. Leaving a secret blank preserves it. **Use .env settings instead** removes database overrides without editing the private environment file. Changes require idle background work. Expand **Platform API access** only for the services you are authorised to configure. A token does not grant missing platform permissions.

The existing `.env` fallback remains supported beside `server.py`:

```dotenv
BELIVE_AGENT_ENGINE=hermes
BELIVE_AI_PROVIDER=openai
BELIVE_AI_MODEL=gpt-6-luna
BELIVE_AI_KEY=YOUR_AUTHORISED_PRIVATE_KEY
```

Keep the file ignored and restart after changing it. Never paste a key into chat, screenshots or a repository. See [connection settings](CREDENTIAL_SETTINGS.md) for encryption, fallback and recovery.

## Understand what passed

A genuine native-model connection check passed in the measured preparation. It recorded the native executor separately from the model and kept direct Decisions classification off. Each installation still needs its own authorised key and check.

Native mode deliberately disables the direct Decisions API classification path, including when an older environment flag is set. The explicit legacy direct transport is retained for regression testing; it is not an automatic fallback.

A model check does not connect WhatsApp or enable platform monitoring. Real company support needs authorised onboarding, webhook and delivery evidence; official scheduled sources require their own permissions/resources/tokens. See [WhatsApp support](WHATSAPP.md).

## Knowledge and reviewed learning

A code-only download has no team knowledge archive. Obtain that archive and its matching recovery key privately; place the archive at `knowledge/team-memory.enc.json` before choosing the key under **Self-learning → Team knowledge backup → Restore on another computer**. Before pulling an older installation, export/preserve both files outside the checkout and retain your own `.env`, data and separate credential key. Never upload either knowledge file to GitHub. See [the migration and restore order](SHARED_MEMORY.md).

Inspect approved knowledge and current citations in the staff dashboard. A past reply is not verified policy. A reviewed completed-case lesson can be reused on a later matching request, while customer-reaction feedback requires review before a writing improvement is activated. Keep SAMPLE / TEST labels and compare actual replies without inventing quality scores.

For safe opt-in rehearsal commands and non-identifying results, use [the checklist](FRIDAY_DEMO_CHECKLIST.md). Existing model alternatives are preserved, but the measured workflow uses native Hermes with GPT-6 Luna.
