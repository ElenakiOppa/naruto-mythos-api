# Phase 9 — Audit stopped: schema review required

## Overall result

**Phase 9 is incomplete.** The database constraint review confirmed a missing ownership constraint with a reproducible public serialization consequence. Per the Phase 9 request, work stopped before any schema migration or further hardening. This report does not certify deployment readiness.

## Confirmed finding: variant image ownership

`app/models/image.py` and the initial migration independently enforce:

- `card_images.card_id` references `cards.id`.
- `card_images.variant_id` references `card_variants.id`.

They do not enforce that the referenced variant belongs to the referenced card. PostgreSQL therefore accepts an image whose `card_id` identifies Card A while its `variant_id` identifies a variant of Card B.

`app/services/card_service.py` loads `CardVariant.images` by variant identity. The production detail service and `CardDetail` public serializer then include that image under Card B's variant. This breaks the ownership assumption used by public responses. Deletion also follows the conflicting relationships: deleting Card A can remove an image exposed under Card B.

The current importer constructs consistent parents from nested input and rejects variant parent moves. This finding is **not** evidence that normal Phase 8 imports create mismatches. It is an unenforced database invariant: a direct database write or a future maintenance writer can store inconsistent ownership that the read API subsequently trusts. There are no public write endpoints implicated by this finding.

## PostgreSQL reproduction and cleanup

Evidence: `phase9_constraint_audit_results.json`.

- PostgreSQL: **18.6**.
- Alembic: **5f360cfd2561**, unchanged.
- Existing mismatched images before the test: **0**.
- One transaction created a uniquely prefixed fictional set, two fictional cards, one variant belonging to Card B, and one mismatched image referencing Card A and that variant.
- PostgreSQL accepted the image insert.
- The actual card detail service and public response model serialized the image under Card B's variant.
- No HTTP request was made; the reproduction verifies the database/service/serialization path directly.
- All five fictional records were rolled back. Complete snapshots of every ORM-mapped table, including associations and provenance, matched before and after.
- No server was started, no real catalogue data was used, and no artwork URL was fetched.

## Proposed constraint for explicit migration review

Require each non-null `(card_images.variant_id, card_images.card_id)` pair to reference the same `(card_variants.id, card_variants.card_id)` pair.

A candidate migration would add a unique referenced key on `card_variants(id, card_id)` and a composite foreign key from `card_images(variant_id, card_id)`. Keep the direct card foreign key. The migration must preserve the established variant-deletion policy: deleting a variant clears **only variant_id**, retains card_id, and preserves the image as a direct image. A plain composite `ON DELETE SET NULL` that clears both columns is incorrect because card_id is required.

Implementation must review PostgreSQL's column-specific SET NULL behavior, migration rendering, and ORM relationship joins together. This is a regular ownership FK proposal; it does not introduce a polymorphic provenance FK workaround.

### Migration implications

1. Preflight existing ownership mismatches and report them; do not guess which card or variant is correct or silently delete images.
2. Add the referenced unique key and ownership foreign key in a new reviewed revision; do not edit the applied initial migration.
3. Account for index creation, constraint-validation locks, and rollout timing.
4. Review overlapping ORM foreign-key relationships and preserve card/variant deletion behavior.
5. Add PostgreSQL regression tests for rejected cross-card images, valid direct/variant images, variant deletion preserving images, card deletion, and importer idempotency.

### Compatibility impact

Valid importer data and the public JSON contract need no change. Previously permitted mismatched writes would fail. The supporting unique key adds storage/write overhead despite `id` already being globally unique. SQLite tests cannot be assumed to reproduce PostgreSQL-specific delete-action syntax; the final approach needs an explicit cross-dialect test strategy. Invalid legacy data would prevent constraint validation until reviewed and corrected.

## Scope and remaining work

Files created: `PHASE_9_REPORT.md`, `phase9_constraint_audit_results.json`.

Application files, importer files, tests, configuration, and migrations modified: **none**.

The initial inspection covered configuration, application exception handling, database sessions, provenance model, importer planning, image model, detail service, variant serialization, and initial migration. It was not a completed whole-project audit.

The remaining requested work was not executed after the stop condition: complete route/method inventory, full import/update/idempotency HTTP integration, remaining constraint/provenance/transaction review, injected 500/log redaction verification, semantic OpenAPI inventory, pagination/sorting/search/random review, 2,000-card latency and EXPLAIN baseline, concurrency review, complete configuration/CORS/dependency/security/hygiene audit, repository-wide lint/format/mypy checks, full test suite, final PostgreSQL verification, and production-readiness README updates.

The previous **327 passing tests** are the approved Phase 8 baseline, not a Phase 9 rerun. No Phase 9 full-suite or lint result is claimed. Other observations from the partial inspection have not been certified or fixed.

## Decision needed to resume

Review the ownership constraint and migration approach, or explicitly accept and document reliance on importer-only enforcement. No migration has been created or applied. Phase 9 remains stopped; Phase 10, deployment, and RapidAPI work have not begun.
