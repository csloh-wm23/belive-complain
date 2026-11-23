# Knowledge backup travels with the project

The team chose **push/download backup**, rather than live GitHub synchronisation. No GitHub account login, VPN or private memory server is needed to read the backup.

The public project includes `knowledge/team-memory.enc.json`. It contains encrypted reviewed SOP, original reviewed redacted source PDFs, approved general complaint experiences, approved writing improvements, and disabled records retaining revocations. AES-256-GCM authenticates the package. Customer conversations, accounts, passwords, `.env`, model keys and unapproved feedback are excluded.

## Upload updates

Use **Push BeLive with memory.bat**, or:

1. Run `python scripts/knowledge_backup.py export`.
2. Commit your source changes and `knowledge/team-memory.enc.json`.
3. Run `python scripts/knowledge_backup.py check`, then push.

BeLive installs the project's pre-push check when started, if no different hooks path is already configured. Existing hooks are preserved. The check rejects a push if current knowledge is missing from the committed backup. A connector/API push bypasses local hooks, so anyone uploading that way must follow AGENTS.md and export/include/check the package explicitly.

The wrapper commits already staged changes plus the updated encrypted package. It does not automatically stage unrelated working files. Use normal source-code staging when updating the program. Git authentication for uploading is still needed, just as for any other project push; it is not needed for local AI operation or restoring an already downloaded backup.

## Restore on another computer

1. Download the latest project and start **Run BeLive Prototype.bat**. Retain your own `.env` and database when updating an existing installation.
2. Receive the team's **knowledge-backup.key** privately from the person preparing the backup. It lives beside that person's active database, under `data` by default. Never commit it or post it in a public chat.
3. In **Self-learning → Team knowledge backup → Restore on another computer**, choose that recovery-key file once.
4. Confirm the SOP and approved experience counts. No source customer cases are created by restoration.

After that, updated packages restore at app startup following a download/pull using the existing local key. Each computer still has separate customer conversations. New approvals are shared only after the approving person exports and pushes, and the other person downloads and restarts. They are not automatically shared in real time.

## Local changes and revoked experience

A withdrawn lesson stays disabled in the backup. Origin records do not silently reactivate it. If both people change the same knowledge before exchanging versions, the incoming version is loaded and the local proposal is preserved in the review panel. Review conflicts before publishing another backup. Different source files and local customer cases are not replaced.

Keep a private copy of the recovery key. GitHub has the encrypted knowledge, but cannot restore it without the key. A wrong key or damaged package does not replace local knowledge. The launcher installs the cryptography component into the ignored project-local `output/knowledge-runtime` directory when required.
