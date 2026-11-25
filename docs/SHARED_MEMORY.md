# Private knowledge backup and transfer

**GitHub carries source code only.** The reviewed-knowledge archive and its recovery key must be kept and transferred privately. Pulling code does not deliver the team's SOP, source documents or approved lessons.

Removing the archive from the current tree does not erase previously committed encrypted copies from older Git history; no history rewrite is performed by this update.

The runtime still reads `knowledge/team-memory.enc.json` locally. This file can contain encrypted reviewed company material and must not be committed or uploaded, even though it is encrypted. Customer databases, conversations, API credentials and unreviewed feedback are not part of this transfer.

## Existing installation: protect knowledge before pulling

1. Wait for current work to finish. Export the latest reviewed local knowledge:

```sh
python scripts/knowledge_backup.py export
```

2. Copy `knowledge/team-memory.enc.json` and its matching private `knowledge-backup.key` to safe private storage **outside the project checkout**. The recovery key is beside the active database, under `data` for the default database. Do not print or send its contents in chat.
3. Retain your own `.env`, `data` folder, database, company documents and `.belive-credentials.key`. The credential key and knowledge recovery key have different purposes.
4. Only after preserving the archive and key, pull/download the new source. An older version tracked the archive; removing it from the new source tree can remove that old tracked copy on pull. Do not discard local knowledge or resolve a conflict by deleting the only copy.
5. Place the preserved private archive back at `knowledge/team-memory.enc.json`, then follow the restore steps below if needed.

If export cannot authenticate the existing archive or reports a conflict, preserve the existing files and ask the authorised backup owner to resolve it. Do not replace them with an empty or unrelated backup.

## Restore on another computer

1. Obtain the approved **archive and matching recovery-key file** from an authorised teammate through a private transfer. A source download and a key alone are not enough.
2. Pull/download source code, retaining that computer's own private configuration and data. Install native Hermes if needed.
3. Copy the received archive into the project at **`knowledge/team-memory.enc.json` before importing the key**. Create the `knowledge` folder if absent.
4. Start **Run BeLive Prototype.bat**, sign in, then open **Self-learning → Team knowledge backup → Restore on another computer**. Choose the matching private recovery-key file and confirm restoration.
5. Verify the actual restored knowledge/document counts and current approval state. Resolve any conflicts; do not assume restored examples are tenant-specific facts.
6. Configure that computer's own authorised model connection and test it. This knowledge transfer does not include API keys, staff accounts or customer conversations.

A fresh code-only installation can start with no archive, but its knowledge library is empty. Importing only a recovery key cannot restore a missing archive. Keep the archive and key private and never upload either to GitHub.

## Later updates

After new knowledge or lessons are reviewed, export again and privately transfer the updated archive. The recipient places it at the same local path and restores using the matching key; startup can detect a privately replaced archive when a matching local key already exists. **Code pull alone never updates knowledge.** This is manual private exchange, not real-time synchronisation.

Use the source update workflow only for code. The historical **Push BeLive with memory** helper name does not authorise staging knowledge or keys; current publishing checks must exclude them. Never use `git add -f` to override their ignore rules.

## Conflicts, revocations and recovery

AES-256-GCM authenticates the archive. A wrong key or damaged archive must not replace existing records. Disabled lessons retain their revocations. Conflicting local edits are preserved for review rather than silently overwritten. Export again only after resolving conflicts.

Keep a private copy of both archive and key. A full private database backup has different scope and may also require document/media folders and the separate credential key. See [connection settings](CREDENTIAL_SETTINGS.md) and [system behavior](FORUM_SYSTEM.md).
