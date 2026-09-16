# Phase 13A acquisition area (local, read-only, discovery only)

This directory holds raw acquisitions from official public Naruto Mythos TCG
sources. Nothing here is imported into the application database and nothing
here defines public API identity.

## Layout

- `manifest.json` — append-only log of every fetch attempt (source URL,
  retrieval timestamp, HTTP status, content type/length, SHA-256, whether the
  content was newly stored or already known).
- `raw/` — content-addressed, immutable raw bytes (`<sha256>.<ext>`).
  **Untracked by git** (see repository `.gitignore`): these are copyrighted
  third-party documents/pages/API payloads and are kept local only.
- `observations/` — one small JSON record per unique content hash, recording
  factual retrieval metadata. Safe to keep under version control (no
  copyrighted bodies), but nothing in this phase is committed.
- `card_data_audit.json` — a read-only, non-normalizing statistical summary
  computed from the acquired `cards.narutotcgmythos.com/api/cards` responses
  (record counts, field presence, raw rarity/cardtype/edition value
  frequencies, ID/Uid collision candidates). No public IDs are generated and
  no rarity/treatment vocabulary is normalized here; see
  `PHASE_13A_REPORT.md` for interpretation and required model extensions.

## Rules that apply to everything under this directory

- Read-only acquisition only. No database writes, no importer invocation.
- No card artwork files are ever downloaded here; image URLs are recorded as
  text references only.
- Raw content is immutable: a repeated fetch of unchanged content reuses the
  existing file; changed content is stored under a new hash, never
  overwriting the old one.
- Acquisition source code lives in `scripts/acquisition/` and enforces an
  official-domain allowlist, bounded timeouts, and response size limits.
