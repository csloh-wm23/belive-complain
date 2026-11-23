# Publishing this project

Production AI uses the official NousResearch Hermes `run_agent.AIAgent`, with GPT/OpenAI as its model provider. Do not bypass Hermes based on a model ID. The explicitly selected `direct` engine exists only for legacy transport tests; it must never be silently used when native Hermes is missing or fails. Verify native executor identity, version, model calls and tool executions before claiming Hermes ran. WhatsApp connection readiness is separate from native Agent readiness. Retain the phone Business app; do not unregister the number to bypass coexistence onboarding.

Before every source-code push (including connector/API pushes that bypass Git hooks), run `python scripts/knowledge_backup.py export` in the active installation. Include `knowledge/team-memory.enc.json` in the commit and run `python scripts/knowledge_backup.py check` after committing. If export, validation or conflict checks fail, stop the push and preserve local records. Do not claim knowledge was backed up merely because source code was pushed.

The encrypted package contains reviewed SOP, reviewed source documents, approved general experiences/writing tips, and disabled records needed to retain revocations. Never upload the local database, customer conversations, `.env`, credentials, recovery keys, raw PDF folders or unreviewed learning into the public repository. The recovery key is supplied privately to authorised users once. Do not reveal its contents in chat or logs.

This is a push/pull knowledge backup, not automatic multi-computer synchronisation. Different local edits are preserved for review; do not force overwrite a friend's work. When the package changes after pulling, BeLive restores it at startup using the local recovery key.
