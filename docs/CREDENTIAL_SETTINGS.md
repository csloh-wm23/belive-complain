# Private connection settings

An administrator can open **System setup → AI & knowledge → Connection settings** to save the model provider, model ID and model API key. Optional platform fields cover Google Reviews, Facebook, Threads, WhatsApp and the notification gateway. Saved overrides belong to the active local database. Existing `.env` configuration still works when a field has no saved override.

Secret inputs are always blank. The interface reports only whether a value is configured and whether it comes from the database or the environment; it never returns any part of a key. Leaving a secret input blank keeps the existing value. **Use .env settings instead** removes the stored overrides and intentionally restores the environment fallback without modifying `.env`.

Select **Save connection settings**, then **Test AI connection**. The latter runs the existing genuine model connection check, so provider charges may apply. A saved key is not proof of a successful connection. Source permissions, company onboarding and real WhatsApp delivery remain separate checks. Changes are refused while AI, collection or delivery work is running. Changing the model does not switch away from native Hermes.

## Storage and recovery

Values are authenticated-encrypted with AES-256-GCM in a dedicated `private_credentials` SQLite table. A separate `.belive-credentials.key` file beside the active database holds the local encryption key. Neither the API, regular support snapshot, knowledge-only backup nor audit history contains the credential values. The database and key stay private and excluded from GitHub. Never send either file to a public repository.

A private full-database backup contains encrypted ciphertext, but not the separate key file. To restore credential access on another machine, preserve both privately; otherwise enter the credentials again in the restored installation. The SOP recovery key is a different file and cannot unlock local API credentials. The reviewed-knowledge archive and its matching SOP key must be exchanged privately; source-code pulls include neither. Place the archive at `knowledge/team-memory.enc.json` before importing the key in Team knowledge backup. Preserve both outside the checkout before updating an older installation that tracked the archive. See [private knowledge transfer](SHARED_MEMORY.md). A missing key or failed authentication locks stored credentials and does not silently fall back to an older environment token.

HTTP requests and background workers select the owning database before platform token reads. Standalone code can use `credential_scope(database)` or pass a database explicitly to `get_value`/`load_settings`. No process-wide environment values are replaced when settings are saved.

No existing keys are automatically imported from `.env`. Until an administrator explicitly saves a replacement, the installation continues using its current setup.

## Public guide boundary

Use placeholder configuration in shared guides. Keep account names, contact numbers, concrete case identifiers, private recovery material and actual provider settings in restricted local records. Public test results can report non-identifying counts without distributing the configuration that produced them.
