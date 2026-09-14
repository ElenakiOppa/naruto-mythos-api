# Phase 9A — Variant Image Ownership Constraint

Approved correction implemented and verified. Database ownership invariant and existing deletion semantics are preserved.

## 1. Exact invariant enforced

Every non-null card_images.variant_id must identify a variant with the same card_id as the image. PostgreSQL enforces the invariant, independently of importer validation. Direct images with variant_id=NULL remain valid.

## 2. PostgreSQL column-specific SET NULL investigation

Before creating the migration, temporary PostgreSQL tables tested this exact clause:

```sql
FOREIGN KEY (variant_id, card_id)
REFERENCES card_variants(id, card_id)
ON DELETE SET NULL (variant_id)
```

PostgreSQL 18.6 accepted valid direct/variant images, rejected a mismatched INSERT with SQLSTATE 23503, and changed only variant_id to NULL on parent deletion, preserving the non-null card_id. The investigation transaction was rolled back. Installed SQLAlchemy also compiled the clause correctly.

## 3. Final constraint design

New `fk_card_images_variant_card_owner` replaces the redundant `fk_card_images_variant_id_card_variants`. The direct card FK remains with ON DELETE CASCADE. Default MATCH SIMPLE means a null variant_id bypasses the composite match while the direct card FK still validates ownership. No trigger or application workaround was added.

## 4. Supporting unique/index design

Added `uq_card_variants_id_card_id` on (id, card_id), providing the referenced composite key. Public variant ID uniqueness is unchanged. Existing card_images indexes on variant_id and card_id remain. No additional referencing composite index was added: variant_id already identifies one parent variant and efficiently narrows image lookup/deletion checks; duplicating it with card_id is not justified by this correction. The supporting unique index adds unavoidable storage and write overhead for this FK design.

## 5. Migration revision

New revision `8b41e2a9c730`, message “Enforce variant image ownership with column-specific SET NULL,” depends on `5f360cfd2561`. The initial applied migration was not edited.

## 6. Upgrade behavior

The migration locks card_variants and card_images in SHARE ROW EXCLUSIVE mode to prevent concurrent writes between preflight and constraint installation. It then validates legacy ownership, adds the supporting unique key, removes the old variant FK, and adds the composite FK. Existing valid images survived the isolated Alembic upgrade. PostgreSQL transactional DDL protects against partial application.

## 7. Preflight behavior

A SQL DO block counts ownership mismatches and raises a diagnostic containing only the count and correction instruction. A deliberately invalid legacy image caused upgrade failure before constraint changes. Its card/variant IDs, the complete constraint inventory, and the old Alembic revision remained unchanged after rollback to the enclosing savepoint. No repair, deletion, or guessed ownership occurs. SQL preflight also remains present in offline migration exports.

## 8. Downgrade behavior

Downgrade removes the composite FK, restores the original simple variant FK with ON DELETE SET NULL, and removes the supporting unique key. The isolated PostgreSQL test compared all constraint names/definitions to the old schema and found an exact match. Re-upgrade passed. The development database was never left downgraded.

## 9. ORM relationship changes

CardImage.variant and CardVariant.images explicitly join by variant_id and synchronize only that column. CardImage.card and Card.images retain their direct card ownership path. Assigning a variant cannot silently overwrite card_id to make a mismatch valid. Cross-card ORM commit raises IntegrityError; rollback restores usable session state. No overlaps suppression was used. PostgreSQL ORM verification treats SQLAlchemy SAWarning as an error.

## 10. Public serialization regression

The production detail service and CardDetail serializer keep direct images separate from nested variant images. A portable regression test verifies both states. PostgreSQL verification deleted a variant through the ORM, expired loaded state, and confirmed all three preserved images appeared in CardDetail.images with an empty variants array. This is service/model serialization verification, not a browser test; importer regression additionally exercised all ten catalogue HTTP routes using the real PostgreSQL dependency.

## 11. PostgreSQL constraint tests

The isolated Alembic schema verified valid direct and variant images, SQL-level rejection of cross-card INSERT by the named ownership FK, correct ORM assignment/loading, rejected ORM reassignment, raw variant deletion, raw card cascade, and ORM deletion with loaded relationships. The isolated schema and every test row were rolled back. Evidence: phase9a_verification_results.json.

## 12. Variant deletion result

Raw SQL deletion left the image row present with its original card_id and variant_id=NULL. ORM deletion produced the same result for loaded variant images. card_id was never cleared.

## 13. Card deletion result

Raw SQL deletion removed both an existing direct image and an image attached to a live variant. ORM deletion with loaded images/variants also removed all images for the card. No invalid rows remained.

## 14. Importer regression

Reused the Phase 8 verification driver with the new expected revision and a separate evidence filename. Against the development PostgreSQL schema, dry run, initial import, update in place, source provenance, omitted entities, explicitly omitted variants/images, rollback, and API serialization passed. A 500-card fictional batch also completed. Importer input/output contracts and implementation were unchanged.

## 15. Idempotency result

Identical second imports reported zero created/updated catalogue entities and unchanged provenance. The 500-card repeat emitted zero DML. Full snapshots matched before and after the repeated small import; UUIDs survived the changed-name import. Evidence: phase9a_importer_results.json.

## 16. SQLite/PostgreSQL test strategy

SQLite retains real foreign-key enforcement and the simple nullable variant FK for portable ORM/delete tests. Conditional DDL emits the composite ownership FK only for PostgreSQL, and the simple fallback only for SQLite. SQLite is not claimed to enforce cross-card ownership. Dedicated PostgreSQL verification is authoritative for column-specific SET NULL and mismatch rejection. Alembic excludes only the SQLite fallback from PostgreSQL autogeneration; `alembic check` reports no upgrade operations.

## 17. Files created

`migrations/versions/8b41e2a9c730_enforce_variant_image_ownership.py`; `tests/test_image_ownership.py`; `scripts/verify_phase9a.py`; `phase9a_verification_results.json`; `phase9a_importer_results.json`; `phase9a_final_checks.json`; `PHASE_9A_REPORT.md`. The local importer execution log is ignored by existing *.log rules.

## 18. Files modified

`app/models/image.py`; `app/models/variant.py`; `migrations/env.py`; `scripts/verify_phase8.py`; `README.md`. The Alembic environment now accepts an explicitly supplied connection for isolated transaction/schema tests and filters SQLite-only metadata during PostgreSQL autogeneration. The Phase 8 driver accepts an expected revision and result path and now explicitly checks omitted child collections. Its default historical revision remains unchanged.

## 19. Tests added

Four pytest tests cover PostgreSQL DDL, SQLite fallback DDL, relationship synchronization targets, and serialization after ORM variant deletion. The PostgreSQL verification script adds migration/preflight/downgrade/re-upgrade, SQL FK rejection, ORM assignment/deletion/loading, no-SAWarning checks, and rolled-back schema cleanup. Existing test assertions were not weakened.

## 20. Full test result

**331 passed**, 2 existing dependency deprecation warnings, 5.71 seconds. Approved baseline: 327. The warnings remain Starlette/httpx and AnyIO BlockingPortal; no SQLAlchemy relationship warnings were introduced.

## 21. Ruff result

Required repository-wide commands were run. `ruff check .` reports 62 existing findings across 15 untouched files (import ordering, FastAPI Depends defaults, typing modernization, unused noqa markers, and dict-literal style). `ruff format --check .` reports 14 untouched files. These are project-owned baseline issues, not external/generated files, so the whole-repository checks are honestly reported as failing. No rule configuration was relaxed. All seven changed/new Python files pass Ruff lint and formatting. Unrelated cleanup is deferred to the explicitly paused remainder of Phase 9; the initial migration remains untouched. Exact file lists are in phase9a_final_checks.json.

## 22. Development DB final Alembic head

**8b41e2a9c730 (head)**. Development upgrade completed successfully, and `alembic check` found no model/schema drift. Final ownership mismatch count: **0**.

## 23. Cleanup verification

Temporary SQL-investigation tables and the entire isolated migration schema were rolled back. The development importer verifier tracked exact created UUIDs, removed only those fictional entities/associations/provenance, and compared complete before/after snapshots successfully. No legitimate catalogue rows were deleted. No verification server was started.

## 24. Remaining risks/deviations

This constraint uses PostgreSQL column-specific SET NULL syntax; PostgreSQL is the runtime target and SQLite remains limited to portable tests. Upgrade locks and supporting-index creation require a suitable maintenance window for larger databases. Legacy mismatches require explicit operator correction. The full Phase 9 audit and its broader lint backlog remain pending. No new endpoints, importer contract changes, scraping, deployment, Phase 10 work, or automatic resumption of Phase 9 occurred.

