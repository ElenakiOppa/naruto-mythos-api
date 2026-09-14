# Naruto Mythos TCG Developer API — Phase 8 Report

Scope: Catalogue Importer and Data Provenance. Implementation and verification complete; Phase 8 only. All datasets used were fictional.

## 1. Files created

`importer/__init__.py`, `schemas.py`, `hashing.py`, `planner.py`, `runner.py`, `cli.py`, and `README.md`; `data/schema/catalogue.schema.json`; `data/examples/fictional-catalogue.json`; `tests/test_importer.py`; `scripts/verify_phase8.py`; `phase8_dry_run_example.json`; `phase8_verification_results.json`; this report.

## 2. Files modified

`README.md` and `data/README.md` document the implemented importer and replace the obsolete placeholder contract. Existing public routes, response schemas, database models, and migrations were not changed.

## 3. Normalized import format

JSON contains required `source` and `sets`, with optional `variant_aliases`. Sets nest cards, cards nest keywords/variants/direct images, variants nest images. Source name and timezone-aware retrieved_at are required; source URL is optional. Dedicated Pydantic v2 importer models generate the committed JSON Schema. The fictional example contains two sets, two cards, one shared keyword, two variants, and four image references.

## 4. Validation rules

Required strings are nonempty and bounded by database lengths. Stats/counts are strict nonnegative integers. Dimensions and serial totals are positive. Numbers remain strings. Serial total requires serial_numbered=true. URLs must be HTTP(S), without embedded credentials. Unknown fields, duplicate JSON keys, invalid JSON, and nonfinite JSON numbers are rejected. Validation errors include locations without raw input dumps.

## 5. Cross-record validation

Global duplicate set/card/variant IDs, duplicate numbers within a set, duplicate keyword associations, conflicting keyword definitions, and identical images within an owner are rejected. Nesting supplies valid parent references. Preflight rejects existing card/variant parent reassignment, occupied card numbers, ambiguous duplicate image identities, and duplicate provenance for one entity/source. No write is needed for this planning.

## 6. Normalization policy

Trim surrounding whitespace; empty optional strings become null; keyword slugs become lowercase. Preserve names, text, numeric values, rarity, leading zeros, and collector-number strings. URLs follow Pydantic structural normalization. Supplied entities are complete scalar snapshots: omitted optional scalars use defaults/null, not sparse-patch semantics.

## 7. Variant normalization

An explicit, exact, case-sensitive input mapping supports aliases such as fictional Holo -> holographic. Chains/cycles are rejected. Unrecognized labels remain valid. Original and normalized values appear in the execution report; the current source_records schema has no raw metadata field, so original aliases are retained in the input/report rather than a new database column.

## 8. Image policy

Only URL metadata is stored, always hosted_by_us=false. No artwork or source URL is fetched. Identity is card + optional variant + type + canonical URL. Changing dimensions/attribution updates the same row; changing URL creates a new image and retains the old one. Plans use deterministic hashed image identities, not internal UUIDs.

## 9. Provenance implementation

Every imported set, card, variant, keyword, and image has a source_records observation with entity type, internal entity UUID, source name/URL, external ID, SHA-256 content hash, first_seen_at, and last_seen_at. Existing first_seen is preserved; last_seen is the maximum observed retrieval time. Provenance remains absent from public API responses.

## 10. Content hashing

Canonical JSON uses sorted keys, compact separators, explicit nulls, UTF-8, and SHA-256. Hash inputs contain normalized scalar data and public parent identity, excluding internal UUIDs and timestamps. Card hashes include effective sorted keyword slugs. Children are hashed separately: changing a card name changes that card hash without cascading into its set hash.

## 11. Dry-run behavior

Parsing, normalization, validation, batched lookup, and the complete deterministic plan run without DML or provenance writes. PostgreSQL uses a repeatable-read, read-only transaction. Tests compare complete snapshots and inspect executed SQL. Repeated dry-run plans match; a later actual import replans against its own current database state.

## 12. Change-plan format

For sets/cards/variants/keywords/images/provenance, plans contain sorted created, updated, and unchanged keys. Relationships contain created, removed, and unchanged card-to-keyword pairs. Counts mirror the lists. Reports include source name, input filename, mode, timestamps, validation, normalization entries, errors/warnings, duration, and transaction outcome. Structured logs summarize counts and execution without database credentials or raw card-text bodies.

## 13. Idempotency

The second identical small PostgreSQL import created and updated zero entities, provenance rows, and associations. Complete snapshots were identical. The 500-card repeat also executed zero DML statements. A newer retrieved_at updates provenance last_seen even when semantic content is unchanged; this is an observation update rather than a catalogue change.

## 14. Update behavior

A single fictional card name change produced exactly one catalogue entity update and one provenance hash update. Dry run left the database unchanged. Actual update retained the same card UUID. Unit tests also verify first_seen preservation, last_seen advancement, unchanged hashes across timestamp-only observations, and stable UUIDs.

## 15. Multi-source behavior

Source B adds independent provenance without deleting Source A records. Explicit import order determines scalar values: each supplied snapshot wins, even with an older retrieval date. No source ranking or automatic reconciliation occurs. Source records store the latest observation per entity/source, not a complete immutable history.

## 16. Deletion policy

Missing sets, cards, variants, keywords, and images are never deleted by the importer. No sync/delete-missing option exists. PostgreSQL verification imported an omitted-entity dataset and confirmed the complete database snapshot stayed unchanged.

## 17. Relationship policy

Missing/null keywords preserve existing associations; an explicit keyword list is authoritative for that card; [] clears associations. Keyword entities remain. Empty or omitted variants/images preserve existing records. Relationship-only changes are separately reported and affect card provenance hashes without falsely reporting scalar card updates.

## 18. Transaction behavior

All actual entity, provenance, and association writes run in one transaction. An injected exception after writes rolled back the entire transaction on SQLite and PostgreSQL. PostgreSQL actual imports take an advisory transaction lock to serialize cooperating importer runs. External writers must coordinate separately because no schema uniqueness migration was added.

## 19. Query/performance behavior

Batched lookups and writes use chunks of 400. The larger fictional dataset contained 5 sets, 500 cards, 10 shared keywords, 500 variants, 1,000 images, 2,015 provenance rows, and 500 associations.

| Run | Seconds | SQL executions | SELECTs | DML executions |
|---|---:|---:|---:|---:|
| dry_run | 0.0937 | 7 | 6 | 0 |
| actual | 0.2996 | 24 | 7 | 17 |
| repeat | 0.1644 | 18 | 18 | 0 |

These are observed local timings, not a service-level threshold. Counts are SQLAlchemy cursor executions, not affected-row counts; actual-import SELECT counts include the advisory lock. No per-entity SELECT pattern was observed. The complete batch is held in memory.

## 20. CLI usage

From the configured project environment:

```powershell
python -m importer.cli data/examples/fictional-catalogue.json --dry-run --report dry-run.json
python -m importer.cli data/examples/fictional-catalogue.json --report import-report.json
```

JSON reports go to stdout; execution summaries go to stderr. Exit status is 0 on success, 1 on failure. Input/report paths cannot be identical. Report-file write failure returns 1 but cannot undo an already committed import; retain stdout. Invalid schema input receives field-location errors.

## 21. PostgreSQL verification

Verified PostgreSQL 18.6 and unchanged Alembic head `5f360cfd2561`. Checks passed for no-write dry run, actual import, identical repeat, one changed-field preview/update, stable UUID, second source, omitted entities, injected rollback, and 500-card performance. Evidence: `phase8_verification_results.json`. The actual database was used directly; SQLite was confined to isolated tests.

## 22. Public API regression verification

All ten requested routes returned 200 after fictional PostgreSQL import: sets list/detail/cards; cards list/detail/random; rarities; keywords; keyword cards; search. Requests used FastAPI TestClient with the actual configured PostgreSQL dependency, without a database override. Equivalent isolated regression tests also passed. Responses serialized successfully and excluded internal provenance. No separate browser/Swagger or external HTTP server verification was performed in Phase 8.

## 23. Cleanup

Exact newly generated UUIDs were recorded in memory during application. Cleanup targeted only those IDs, including polymorphic provenance and card-keyword associations, in a finally block. Removed: 7 sets, 502 cards, 502 variants, 11 keywords, 1004 images, 2037 provenance. Complete catalogue/provenance snapshots matched the original baseline afterward. No tables were dropped and migrations were untouched. The script generates a unique fictional prefix per run.

## 24. Tests added

34 tests: 17 malformed/cross-record inputs; deterministic dry runs with no DML; import/idempotency/update/source/timestamp/omission/relationship lifecycle; injected rollback and error sanitization; ownership and number conflicts; hashing/normalization; ten public routes; variant alias/unknown/numbered types and image ownership; CLI validation/report/input protection; JSON Schema synchronization.

## 25. Full test results

`python -m pytest -q`: **327 passed**, 2 existing dependency deprecation warnings (Starlette/httpx and AnyIO BlockingPortal), 10.71 seconds. Baseline was 293. `ruff check importer tests/test_importer.py scripts/verify_phase8.py`: passed. `ruff format --check` on the same scope: 9 files already formatted. No earlier tests were weakened.

## 26. Bugs discovered/fixed

CLI prevalidation initially reduced schema failures to a generic message; it now returns the same safe field-location errors as the runner. The data directory documentation referenced a nonexistent earlier importer and obsolete shape; it now points to the implemented contract. Formatting and focused lint issues were corrected before completion. No public API defect was found during importer regression.

## 27. Deviations and limits

No migration was necessary. Original alias labels are recorded in reports because existing provenance has no raw metadata column. The planner conservatively rejects card-number swaps and parent moves. Database concurrency protection covers cooperating importers, not arbitrary writers. Performance is a measured local baseline rather than a promised threshold. No real catalogue data, scraper, artwork download, deployment, or Phase 9 work was introduced.

## 28. Final project tree

The tree below lists project source, tests, documentation, and evidence; environment files, caches, generated package metadata, and prior verification artifacts are omitted for readability.

```text
.pytest_cache/README.md
.venv/Lib/site-packages/mypy/typeshed/stdlib/_typeshed/README.md
alembic.ini
app/__init__.py
app/api/__init__.py
app/api/router.py
app/api/v1/__init__.py
app/api/v1/cards.py
app/api/v1/health.py
app/api/v1/metadata.py
app/api/v1/ready.py
app/api/v1/search.py
app/api/v1/sets.py
app/config.py
app/database.py
app/main.py
app/models/__init__.py
app/models/card.py
app/models/image.py
app/models/keyword.py
app/models/mixins.py
app/models/set.py
app/models/source.py
app/models/variant.py
app/schemas/__init__.py
app/schemas/base.py
app/schemas/card.py
app/schemas/error.py
app/schemas/health.py
app/schemas/image.py
app/schemas/keyword.py
app/schemas/metadata.py
app/schemas/pagination.py
app/schemas/ready.py
app/schemas/search.py
app/schemas/set.py
app/schemas/variant.py
app/services/__init__.py
app/services/card_filters.py
app/services/card_service.py
app/services/metadata_service.py
app/services/search_service.py
app/services/set_service.py
app/utils/__init__.py
app/utils/error_docs.py
app/utils/errors.py
app/utils/pagination.py
app/utils/slugs.py
data/examples/fictional-catalogue.json
data/README.md
data/schema/catalogue.schema.json
importer/.gitkeep
importer/__init__.py
importer/cli.py
importer/hashing.py
importer/planner.py
importer/README.md
importer/runner.py
importer/schemas.py
migrations/env.py
migrations/script.py.mako
migrations/versions/5f360cfd2561_initial_schema.py
phase8_dry_run_example.json
phase8_verification_results.json
pyproject.toml
README.md
scripts/verify_phase8.py
tests/__init__.py
tests/conftest.py
tests/test_card_filters.py
tests/test_cards_routes.py
tests/test_discovery.py
tests/test_health.py
tests/test_importer.py
tests/test_models.py
tests/test_openapi.py
tests/test_ready.py
tests/test_schemas.py
tests/test_sets_routes.py
PHASE_8_REPORT.md
```

