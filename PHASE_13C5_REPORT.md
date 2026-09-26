# Phase 13C.5 — PostgreSQL Migration, Production Import, Deployment, and Final Verification

**Status: COMPLETE.** The approved collector catalogue architecture was migrated, populated, deployed, and verified in Railway production. No destructive database operation, downgrade, stamp, reset, truncation, or fabricated catalogue record was used.

## A. Pre-deployment environment

- Approved C4 commit and starting local HEAD: `eb387a86785a63460b799d94343311188ca851f8`.
- Branch: `main`; the worktree was clean before database mutation after the draft C5 report was temporarily stashed.
- Railway project: `naruto-mythos-api` (`8217b7e1-c12f-4ae8-86f2-0de02aed39ec`).
- Environment: `production` (`cab33d72-e12e-4d94-a1a1-c2cc6eb64a85`).
- API service: `naruto-mythos-api` (`5fc8b008-461c-490b-a604-ae49a22dcec0`).
- PostgreSQL service: `Postgres` (`d36a8d5b-bcdd-41b8-902d-efdb6a79cea4`) with attached persistent volume.
- Previously deployed application: deployment `d60971bd-41de-4a40-8800-f7975f3a96a0`, Git commit `749882bc06e8b45ed016a5708db6a4344abd6863`.
- Target connectivity was verified as Railway database `railway`, PostgreSQL 18.6, through a private Railway SSH tunnel. No credential-bearing value was printed or recorded.

## B. Starting database state

- Alembic revision: `c13c20260916`.
- Sets: 2.
- Cards: 318.
- upstream `card_variants` / Printings: 636.
- Printing translations: 2,544.
- Source records: 2,544 observations associated with 636 upstream Printings.
- Image references: 2,544.
- Keywords: 46.
- Card-keyword associations: 701.
- Nonblank source Edition values: 615; blank/editionless source Printings: 21.
- Expected source-supported groups were present: Konoha Shidō 1st Edition (186), Konoha Shidō 2nd Edition (187), and Shinobi Shiren 1st Edition (242).
- `editions` and `printing_references` did not exist, and none of the new Printing ownership/taxonomy/reference columns existed, consistent with the recorded revision.
- No orphan Card, orphan Printing, null Printing Card owner, or semantic Printing identity collision was found.

## C. Backup and recovery status

Railway reported that backups and point-in-time recovery are available only on the Pro plan. This project is on Trial and showed no existing recovery point, so no backup or snapshot capability was available through the configured tooling. This limitation was reported before migration. No backup was invented or claimed.

## D. Migration revisions applied

`alembic upgrade head` ran through the private production connection and applied, in order:

1. `c13c20260916 -> d13c20260926` — Set-scoped Editions and Printing ownership constraints.
2. `d13c20260926 -> e13c20260926` — normalized Printing taxonomy fields.
3. `e13c20260926 -> f13c20260926` — curated Printing references.

Final revision: `f13c20260926` (head). Alembic used PostgreSQL transactional DDL and reported no migration error.

## E. Post-migration schema validation

- `editions` and `printing_references` exist.
- All expected ownership, taxonomy, and reference columns exist on `card_variants`.
- Required Edition uniqueness, Printing/Card ownership, Printing/Edition ownership, taxonomy status, reference uniqueness, and positive workbook-row constraints exist.
- Required Edition, Printing ownership, semantic Printing identity, and reference indexes exist.
- The original 636 Printings remained present after migration.
- Three Editions were materialized with the expected per-Edition upstream counts.
- All 21 blank source Edition records remained `edition_id IS NULL`.
- Printing-to-Card Set mismatches: 0.
- Printing-to-Edition Set mismatches: 0.
- Semantic Printing identity collisions: 0.

## F. Import commands and process

The upstream catalogue was already present at its exact approved production baseline, so the empty-catalogue one-shot importer was not rerun and no existing data was deleted or overwritten. The migrations materialized Editions and normalized taxonomy from those persisted upstream Printings.

The curated layer used the existing deterministic repository functions:

- `build_reference_reconciliation()` to rebuild and validate the approved 396-entry plan from the local content-addressed source snapshot and curated reference.
- `persist_reference_reconciliation()` to persist matches, curated-only Printings, and reference associations transactionally.

The plan gate confirmed 318 Cards, 636 upstream Printings, 396 checklist entries, 184 overlaps, 212 curated-only Printings, two source-only conflicting upstream rows, zero ambiguities, and 848 planned total Printings before persistence.

## G. First import counts

Before curated persistence: 318 Cards, 636 upstream Printings, 0 reference rows, 0 curated-only Printings.

After the first committed pass:

- canonical Cards: 318
- upstream Printings: 636
- reference entries: 396
- upstream + curated overlap: 184
- curated-only Printings: 212
- upstream-only Printings: 452
- total Printings: 848

## H. Idempotency verification

The same deterministic reconciliation and persistence process was rerun twice inside the deployed Railway container, using the production database's private network connection. Both passes returned the same expected counts and created no additional Cards, Editions, Printings, or reference associations. A separate SQL verification after the repeat confirmed the unchanged 318/636/396/184/212/848 totals.

An auxiliary temporary ORM verifier used after the completed persistence calls referenced a nonexistent convenience attribute and exited after the identical-count assertion had already passed. The authoritative SQL verifier was then run successfully. No repository file was changed by this temporary verifier.

## I. Final database counts

- canonical Cards: 318
- upstream Printings: 636
- curated-reference-only Printings: 212
- total distinct Printings: 848
- curated reference rows: 396
- distinct referenced Printings: 396
- upstream + curated overlap: 184
- upstream-only Printings: 452
- Editions: 3
- editionless upstream Printings: 21

The previously validated 2,544 translations, 2,544 source observations, 2,544 upstream image references, 46 keywords, and 701 keyword associations were preserved.

## J. Edition validation

Production contains only the three supported Editions:

- Set 1: Konoha Shidō — 1st Edition
- Set 1: Konoha Shidō — 2nd Edition
- Set 2: Shinobi Shiren — 1st Edition

No Shinobi Shiren 2nd Edition was created. All 21 blank source Edition records remain editionless.

## K. Konoha collector validation

- Konoha Shidō 1st Edition collector identities: 396, each referenced exactly once.
- 184 identities reuse upstream Printings.
- 212 identities use curated-only Printings.
- The two known source-only conflicting upstream Printings remain in the general Printing catalogue and do not inflate the collector view.
- Every reference resolves through an existing Printing to an existing canonical Card.
- Canonical Card count remained 318.
- Curated-only rows with source provenance: 0.
- Curated-only rows with images: 0.
- Curated-only rows with translations: 0.
- Curated-only rows with serial evidence: 0.
- No pricing data was introduced.

## L. Deployment result

- Railway deployment: `4112ea52-eaa0-47d0-93b9-38ff53cfd558`.
- Result: `SUCCESS` after Docker build, no-op head migration pre-deploy, startup, and `/ready` health check.
- Live API base URL: `https://naruto-mythos-api-production.up.railway.app`.
- The repository's existing Railway configuration was used unchanged.

## M. Live API smoke tests

Public origin checks:

- `GET /health`: 200, status `ok`.
- `GET /ready`: 200, status `ready`.
- `GET /openapi.json`: 200.
- Direct unauthenticated origin access to `/v1` returned 403, confirming the existing RapidAPI proxy-secret guard remains active.

Protected live checks ran inside the deployed production container using its configured secret without printing or exporting it. All passed:

- `GET /v1/cards`
- `GET /v1/cards/{card_id}` including legacy `variants` and additive `printings`
- `GET /v1/sets`
- `GET /v1/sets/{set_id}`
- `GET /v1/printings`
- `GET /v1/printings/{printing_id}`
- `GET /v1/sets/{konoha_set_id}/editions`
- `GET /v1/editions/{konoha_1st_edition_id}`
- `GET /v1/editions/{konoha_1st_edition_id}/printings`
- Edition, rarity, treatment, collector-class, and origin filters
- Legacy and Printing rarity metadata endpoints

## N. Live API counts

- `/v1/cards` canonical total: 318.
- `/v1/sets` total: 2.
- `/v1/printings` total: 848.
- Konoha 1st Edition verified collector total: 396.
- General Konoha 1st Edition Printing total: 398, retaining the two source-only conflict rows.
- `origin=CURATED_REFERENCE`: 212.
- `origin=UPSTREAM_AND_CURATED`: 184.
- `origin=UPSTREAM`: 452.
- Konoha 1st Edition `collector_class=Mission`: 10.
- Representative rarity and Holographic treatment filters returned nonzero results.

## O. Backward compatibility

Live Card list, Card detail, legacy `variants`, Set list/detail, and rarity metadata behavior passed. The collector deployment is additive: Cards remain canonical and the existing read-only behavior remains available behind the unchanged proxy guard.

## P. OpenAPI verification

The public deployed OpenAPI document contains all Edition and Printing endpoints introduced in C4. Its path set exactly matches `docs/generated/openapi.rapidapi.json`: 18 paths and 18 unique GET operations. Local RapidAPI OpenAPI export and OpenAPI 3.0.2 validation passed, and regeneration produced the identical artifact SHA-256 `c23cde05a1c8a8aca64e6f3bd23e9ccb2fa58b78014fdac584d7b9792d78f40f`.

## Q. RapidAPI status

No RapidAPI configuration or visibility setting was changed. The backend now serves the deployed collector surface. If the RapidAPI listing requires a separate manual specification publication, that remains a manual platform action because the repository contains no supported automatic publication workflow.

## R. Local validation

- Focused collector API suite: 6 passed.
- Complete non-PostgreSQL suite: 789 passed, 3 dependency deprecation warnings.
- Ruff lint: passed.
- Ruff format check: passed; 174 Python files already formatted.
- Mypy `app importer scripts`: passed, 0 issues in 105 source files.
- OpenAPI 3.0.2 export and validation: passed; generated artifact unchanged.
- Source dry-run: 636 accepted, 0 rejected, 318 Cards, 3 Editions, 636 upstream Printings, 21 editionless, 0 identity collisions, 30 Mission-point records, and 2 negative-Power records.
- Reference reconciliation: 396 entries, 184 overlaps, 212 curated-only, 2 source-only conflicts, 0 ambiguities, planned total 848.
- Live PostgreSQL migration/schema/data verification: passed.
- `git diff --check`: run before commit.

The six local PostgreSQL fixture tests were not rerun because Windows Application Control has previously blocked local `initdb`. The actual Railway PostgreSQL 18.6 migration and production validation supplied the required PostgreSQL runtime evidence.

## S. Remaining limitations and actions

- Railway Trial provides no backup/PITR capability for this database; enable an appropriate recovery feature before future high-risk database changes.
- RapidAPI may require a manual specification publication/update to expose the new documented surface in its listing.
- No Binder deployment or pricing implementation was performed.

Phase 13C.5 completed without destructive cleanup, database recreation, catalogue fabrication, RapidAPI configuration changes, or secret disclosure.
