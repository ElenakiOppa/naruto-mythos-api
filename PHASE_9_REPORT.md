# Phase 9 — Full-System Audit, Integration Testing, and Production Hardening

Completed against PostgreSQL 18.6 and Alembic 8b41e2a9c730. Phase 9A remains approved and incorporated. Fictional data only.

## 1. Overall audit result

**Phase 9 completed.** No additional material database-schema correctness blocker was found. The application is ready to proceed to a separately authorized containerization/deployment phase, with the operational limitations below. This is an application audit and local verification, not a deployment certification or comprehensive penetration test. No deployment, authentication system, RapidAPI integration, scraper, real catalogue data, or new public feature was added.

## 2. Phase 9A correction acknowledgement

**FOUND AND FIXED IN PHASE 9A:** variant-image ownership. PostgreSQL still contains `uq_card_variants_id_card_id` and `fk_card_images_variant_card_owner`; the redundant simple variant FK is absent, the direct card FK remains, and mismatch count is zero. Existing Phase 9A regression tests ran in the full suite. No additional migration was created and the migration head remains `8b41e2a9c730`.

## 3. Files created

`tests/test_system_audit.py`; `scripts/verify_phase9.py`; `phase9_verification_results.json`; `phase9_schema_audit.json`; `PHASE_9_STOP_REPORT.md` (preserves the earlier stopped audit). `phase9_file_baseline.json`, `phase9_mypy.txt`, and the execution log are ignored local working evidence. The final report replaces the stopped report at the original filename.

## 4. Files modified

Most changes outside the targeted fixes are the explicitly requested Ruff import/style/typing/format cleanup. Applied migration formatting and annotation modernization do not alter migration SQL or revision history. Modified files:

- `.env.example`
- `.gitignore`
- `PHASE_9_REPORT.md`
- `README.md`
- `app/api/router.py`
- `app/api/v1/cards.py`
- `app/api/v1/metadata.py`
- `app/api/v1/search.py`
- `app/api/v1/sets.py`
- `app/config.py`
- `app/database.py`
- `app/main.py`
- `app/models/card.py`
- `app/models/image.py`
- `app/models/set.py`
- `app/schemas/health.py`
- `app/schemas/keyword.py`
- `app/schemas/metadata.py`
- `app/schemas/pagination.py`
- `app/schemas/ready.py`
- `app/schemas/search.py`
- `app/schemas/set.py`
- `app/services/card_filters.py`
- `app/services/card_service.py`
- `app/services/metadata_service.py`
- `app/services/search_service.py`
- `app/services/set_service.py`
- `app/utils/pagination.py`
- `importer/cli.py`
- `importer/schemas.py`
- `migrations/versions/5f360cfd2561_initial_schema.py`
- `tests/conftest.py`
- `tests/test_card_filters.py`
- `tests/test_cards_routes.py`
- `tests/test_discovery.py`
- `tests/test_models.py`
- `tests/test_schemas.py`
- `tests/test_sets_routes.py`

## 5. Public API inventory

Exactly twelve application GET operations are present in OpenAPI:

- `/health`, `/ready`
- `/v1/sets`, `/v1/sets/{public_id}`, `/v1/sets/{public_id}/cards`
- `/v1/cards`, `/v1/cards/random`, `/v1/cards/{public_id}`
- `/v1/rarities`, `/v1/keywords`, `/v1/keywords/{slug}/cards`
- `/v1/search`

Optional documentation routes are `/docs`, `/redoc`, `/openapi.json`. The unused OAuth redirect helper was disabled to keep the route inventory exact. There is no importer, admin, or write endpoint.

## 6. Method safety

POST, PUT, PATCH, and DELETE against cards list/detail, sets, and keywords returned 405 in isolated regression tests and actual localhost HTTP verification. Complete PostgreSQL snapshots were unchanged after GET and unsupported-method checks. Framework 405 remains its standard non-success response, not a new domain error.

## 7. End-to-end importer/API verification

`scripts.verify_phase9` generated normalized fictional JSON, passed it through the real importer into the normal configured PostgreSQL database, started Uvicorn on a temporary localhost port, and issued real HTTP requests with httpx. No production database dependency override was used. All twelve routes succeeded and catalogue JSON was validated with the actual Pydantic response models. Fixtures include multiple languages/editions, types, rarities, keywords, stats, nullable subtitle, and both image scopes.

## 8. Update/idempotency verification

Changed card name, rarity, chakra, power, keyword associations, variant finish, and image width. HTTP responses immediately reflected the changes; public/internal card identity remained stable, search found the new name, the old keyword count decreased, and a new rarity count appeared. Explicit empty keywords removed associations, while omitted variants/images remained. Repeating identical input issued zero catalogue/provenance/association DML and left all deterministic public responses, metadata, and search identical. Random selection itself was excluded from equality comparisons because its purpose is nondeterministic.

## 9. Database constraint audit

Live schema inspection is retained in `phase9_schema_audit.json`. Unique public-ID indexes exist for sets/cards/variants; keyword slug is unique; cards have unique (set_id, card_number); card_keywords has its composite PK. Set deletion is RESTRICT while cards exist; card-owned variants/images and keyword associations cascade; variant deletion clears only variant_id. Nonnegative set totals/stats, positive serial totals and image dimensions are checked. Required ownership IDs remain non-null. Optional public fields match nullable model columns. serial_total positivity is DB-enforced; serial_numbered/serial_total coupling is the documented importer rule, not a new DB invariant. source_records intentionally remains polymorphic without FK. No additional correctness migration was necessary. `alembic check` found no drift.

## 10. Provenance audit

Normal imports construct entity UUIDs before provenance writes and commit all related rows together. The live fixture had zero provenance observations without matching entities for their declared types. A second source added observations without changing the first source rows. The existing importer lifecycle tests verify canonical hashes, first_seen preservation, monotonic last_seen, timestamp-only observations, and source independence. Polymorphic entity_type/entity_id has no DB FK by design: external writers/deleters must preserve integrity and explicitly clean provenance. This is an accepted tradeoff; it is not an immutable event history. Cooperative advisory locking prevents duplicate logical observations between importer runs; arbitrary writers must coordinate.

## 11. Transaction/session audit

GET services only select; request-scoped sessions close in finally without commit. New lifecycle regression verifies close after an exception. Importer validation/planning precedes a single actual transaction; the live injected failure rolled back writes and restored full snapshots. Dry runs were snapshot-equivalent and read-only. PostgreSQL integration used normal database dependencies rather than SQLite overrides. Engine bind parameters are hidden in SQLAlchemy diagnostic output.

## 12. Error-contract audit

Confirmed 404 SET_NOT_FOUND, CARD_NOT_FOUND, KEYWORD_NOT_FOUND; 400 INVALID_PAGINATION, INVALID_SORT, INVALID_FILTER; generic 500 INTERNAL_ERROR. Errors preserve the approved error/code/message shape. Malformed query types remain framework-native 422. Readiness returns generic 503 on database failure. Domain 400/404 examples remain documented, and a shared 500 ErrorResponse is now documented across application routes.

## 13. Injected 500 result

An isolated service raised an exception containing a fictional database URI/password/token. The client received only INTERNAL_ERROR and a generic message. Captured logs contained RuntimeError and frame/function locations, but no password/token/exception text. The middleware catches failures before Starlette can rethrow the original error to Uvicorn’s unredacted exception logger. Source lines and bind values are omitted. This covers current JSON request handlers; future streaming/background-task features would need their own review.

## 14. OpenAPI audit

Semantic assertions validate exact paths/methods, nonempty tags, success schemas, shared 500 documentation, important card query aliases/filters, and absence of importer/provenance/internal UUID schemas and fields. Runtime remains OpenAPI 3.1. A future 3.0.x export may need nullable anyOf, const/enum, exclusive-bound, examples, and discriminator/reference transformations validated against the actual gateway. No downgrade or conversion dependency was introduced.

## 15. Serialization audit

SetSummary remains compact while set lists intentionally return SetDetail. CardSummary excludes text/stats/variants/keywords; CardDetail remains complete. Image fields exclude internal UUIDs/FKs, hosted_by_us, and source metadata. Nulls and arrays retain their established shapes. Found and fixed set-scoped list loading of variant images: it now shares the same direct-image eager-loading options as other summaries and refreshes previously loaded state. Phase 9A’s image-promotion serialization regression passed.

## 16. Pagination/sorting audit

Shared page=1, limit=50, max=100 semantics remain. total/pages/has_next/has_previous calculations are reused across all four paginated routes. Beyond-final pages return empty data; has_previous follows page number even when there are no results. Empty-catalogue tests remain passing. Sorting uses explicit attribute allowlists, NULLS LAST, and public-ID tie-breakers. Card numbers stay lexical; database collation and case folding determine alphabetical behavior. Filtered sorting was exercised against PostgreSQL. Search remains separately bounded, not paginated.

## 17. Search/random audit

Search trims q, requires at least two characters, escapes LIKE metacharacters, binds values, ranks exact identifier then exact name/prefix/substring, and limits the final merged result to 50 maximum. Existing ranking/literal/limit/tie/query-growth regressions all passed. Live search returned updated names. Summary loading fetched direct images only, with no per-card variants/keywords. Static random routing precedes the public-ID route; randomish reaches the ordinary ID handler. Empty random behavior remains CARD_NOT_FOUND. ORDER BY random() remains intentionally unoptimized.

## 18. Performance dataset

10 fictional sets, 2,000 cards, 5 shared keywords, 2,000 variants, and 4,000 image URLs (2,000 direct and 2,000 variant), with multiple rarities/languages/editions and numeric stats. Input was generated in memory and imported as JSON; no giant catalogue fixture or artwork was committed. Update verification added one distinct rarity and removed one keyword association before measurements.

## 19. Performance baseline

| Operation | Latency (ms) | SQL statements | Items |
|---|---:|---:|---:|
| `/v1/cards?page=1&limit=50` | 8.07 | 3 | 50 |
| `/v1/cards?rarity=p9-527f350a05-rare-1` | 8.76 | 3 | 50 |
| `/v1/cards?keyword=p9-527f350a05-kw-0` | 10.2 | 3 | 50 |
| `/v1/cards?variant=p9-527f350a05-holo` | 11.99 | 3 | 50 |
| `/v1/search?q=p9-527f350a05` | 15.23 | 4 | 20 |
| `/v1/rarities` | 3.23 | 1 | 4 |
| `/v1/keywords` | 4.19 | 1 | 5 |
| `/v1/cards/random` | 6.75 | 5 | 1 |
| `/v1/cards/p9-527f350a05-0-000` | 5.76 | 5 | 1 |
| `/v1/sets/p9-527f350a05-set-0` | 2.33 | 1 | 1 |

Single-run local warmed-process timings, including HTTP overhead, not SLAs. SQL counts use SQLAlchemy cursor events in the server process. Search/list counts show bounded eager loading rather than per-card relationship queries.

## 20. Query-plan findings

EXPLAIN (ANALYZE, BUFFERS, FORMAT JSON) was run on captured, parameterized SELECT statements (first two per measured operation). These are read-only plans for the actual service SQL. Full plan trees are retained in the verification JSON.

- `/v1/cards?page=1&limit=50`: Aggregate, Index Only Scan on cards, Index Scan on cards, Limit, Nested Loop, Seq Scan on sets, Sort.
- `/v1/cards?rarity=p9-527f350a05-rare-1`: Aggregate, Index Scan on cards, Limit, Nested Loop, Seq Scan on sets, Sort.
- `/v1/cards?keyword=p9-527f350a05-kw-0`: Aggregate, Hash, Hash Join, Index Scan on cards, Limit, Nested Loop, Seq Scan on card_keywords, Seq Scan on keywords, Seq Scan on sets, Sort.
- `/v1/cards?variant=p9-527f350a05-holo`: Aggregate, Hash, Hash Join, Index Scan on cards, Limit, Nested Loop, Seq Scan on card_variants, Seq Scan on sets, Sort.
- `/v1/search?q=p9-527f350a05`: Index Scan on card_images, Limit, Nested Loop, Seq Scan on cards, Seq Scan on sets, Sort.
- `/v1/rarities`: Aggregate, Seq Scan on cards, Sort.
- `/v1/keywords`: Aggregate, Hash, Hash Join, Seq Scan on card_keywords, Seq Scan on keywords, Sort.
- `/v1/cards/random`: Hash, Hash Join, Index Scan on card_variants, Limit, Seq Scan on cards, Seq Scan on sets, Sort.
- `/v1/cards/p9-527f350a05-0-000`: Index Scan on card_variants, Index Scan on cards, Nested Loop, Seq Scan on sets.
- `/v1/sets/p9-527f350a05-set-0`: Seq Scan on sets.

A sequential scan of ten sets is reasonable even with the public-ID index present. Substring search, metadata aggregation, and random selection naturally scan broad data; limited sorts were observed. No plan constituted a production correctness blocker at the measured size.

## 21. Index recommendations

No index was added. If future scale/traffic measurements justify them, consider: expression index on lower(cards.rarity) for selective case-insensitive rarity filters; card_keywords(keyword_id, card_id) for keyword-first association access; expression variant-type indexing if selective variant filters grow; pg_trgm indexes on selected searched expressions for substring search; a (card_number, public_id) ordering index if pagination sorts become material. Each adds storage and import/write maintenance, and trigram indexes additionally need an extension/migration review. Existing card/variant ownership indexes already help correlated lookups. Aggregate metadata and ORDER BY random() cannot be made constant-cost merely by adding these indexes.

## 22. Concurrency review

Simultaneous live GET requests succeeded. A GET issued after importer writes but before commit saw the old committed name; after commit it saw the new name. A second PostgreSQL connection could not acquire advisory key 807008 until the first transaction rolled back, then could acquire it. No advisory lock remained after imports. READ COMMITTED gives each statement a snapshot, so a multi-query response can straddle a concurrent commit; it is not guaranteed to represent one request-wide snapshot. Two cooperating importers serialize under the lock; arbitrary external writers bypass it unless explicitly coordinated. No distributed lock was added.

## 23. Configuration audit

DATABASE_URL remains required, environment-sourced, and excluded from Settings repr; validation text hides input values. APP_ENV labels the environment but does not implicitly configure deployment controls. Debug responses are explicitly disabled. DOCS_ENABLED now controls all documentation routes and is tested in a fresh process. LOG_LEVEL remains explicit; INFO is the normal operational choice. PORT does not itself configure Uvicorn; documentation now states it must be passed in the server command. No secrets were introduced and .env was not printed.

## 24. CORS review

Existing configuration-driven middleware remains: allowed origins from CORS_ORIGINS, methods GET, credentials=false. Empty configuration adds no cross-origin permission headers. Explicit browser origins are recommended for deployment; a deliberate public wildcard policy must stay credential-free. CORS is not authentication and does not restrict direct HTTP clients. Gateway/proxy CORS must be verified when those systems are introduced.

## 25. Dependency audit

Runtime: FastAPI, Uvicorn standard extras, SQLAlchemy, Alembic, Pydantic, pydantic-settings, psycopg binary, python-dotenv. Development: pytest, pytest-asyncio, httpx, Ruff, mypy. pytest-asyncio is configured but current tests are primarily synchronous; it was not removed merely for tidiness. No missing current runtime dependency was found; `pip check` passed. Verified installed versions: FastAPI 0.141.1, Starlette 1.6.0, httpx 0.28.1, AnyIO 4.15.1, SQLAlchemy 2.0.52, Pydantic 2.13.5, psycopg 3.3.5, Alembic 1.20.0. Starlette testclient warns when falling back to httpx rather than httpx2; its own BlockingPortal type alias triggers the AnyIO warning. Both originate in installed dependency code. No dependency files were edited or broad upgrades performed. Lower-bounded, unlocked dependencies remain a reproducibility concern for the future deployment phase; this was not a vulnerability-database audit.

## 26. Logging/security audit

API exceptions no longer log exception values/SQL/source lines, and SQLAlchemy diagnostics hide parameters. Duplicate-image validation no longer echoes URL query tokens. CLI invalid-schema handling no longer imports configured database modules while trying to format the validation error; a fresh-process test with missing configuration returns structured JSON rather than a traceback. Importer URLs remain structurally validated inert data. Filters/search use bound parameters and allowlists; no public write path exists. Deployment access logs/proxy logs remain a separate concern: query strings can contain values clients should not have sent.

## 27. Repository hygiene

Existing .env/environment/cache/log ignores retained. Added coverage and local database ignores plus temporary audit inventory/type-output ignores. Reviewed phase reports and fictional verification JSON are retained evidence; generated 2,000-card input is not written. The earlier stopped audit is preserved separately. No synced reference material, installed dependency files, real data, or artwork was modified. Ignore rules are prevention, not proof that no secret was ever committed to external history; no such history certification is claimed.

## 28. Ruff cleanup

The known 62 lint and 14 formatting findings were resolved with reviewed import ordering, typing modernization, redundant noqa removal, dictionary literals, and formatting. FastAPI dependency declarations now reuse module-level Depends objects, preserving import-time declaration and per-request resolution; full HTTP tests confirm no dependency behavior change. No rule was globally disabled. `ruff check .` passes; `ruff format --check .` reports 84 files formatted. `mypy app importer` passes for 51 source files; one precise Settings call-arg annotation documents runtime environment loading, and the heterogeneous search dispatch tuple has explicit dynamic typing.

## 29. Tests added

25 additional pytest cases over the 331 baseline: semantic route/OpenAPI inventory; 16 unsupported-method combinations; sanitized injected 500/log output; set-summary direct-image loading/no-DML; session closure on exception; duplicate-image token redaction; Settings repr protection; readiness failure/liveness behavior; docs-disabled fresh process; CLI validation without DB configuration. A separate real HTTP/PostgreSQL verification script covers the large integrated workflow, query plans, MVCC visibility, source independence, and exact cleanup.

## 30. Full test result

**356 passed**, **2 existing dependency deprecation warnings**, **7.10 seconds**. No previous test assertions were weakened. The full suite includes the approved importer and Phase 9A portable ownership/serialization regressions. Mypy and both repository-wide Ruff checks pass.

## 31. PostgreSQL full-system verification

Normal configured PostgreSQL 18.6, actual localhost HTTP server, no production DB override. Passed health/readiness, every public route, representative filters/sorts/pages, metadata/search/random, input import/update/repeat, rollback, provenance independence/no-orphan checks, ownership presence/mismatch count, domain errors, OpenAPI, and concurrency checks. The isolated injected-500 test complements live healthy-service verification. See `phase9_verification_results.json` and `phase9_schema_audit.json`.

## 32. Cleanup verification

The importer application hook recorded exact newly generated UUIDs in memory. Cleanup removed only those entity/provenance IDs and their keyword associations; complete mapped-table snapshots matched the original baseline. Counts removed: 10 sets, 2000 cards, 2000 variants, 5 keywords, 4000 images, 8020 provenance. Server stopped successfully. Final ownership mismatch count is 0; Alembic remains `8b41e2a9c730`; no schema/model drift.

## 33. Bugs found/fixed

Set-scoped card lists incorrectly included variant images; shared filtered summary loading fixes this. Catch-all exception logging could leak secrets in exception text; sanitized frame/type logging and early error handling fix this. Duplicate image validation could echo URL tokens; it now emits a generic duplicate diagnostic. Invalid CLI input handling could depend on missing DB configuration; it now builds validation reports without importing database modules. The unused documentation OAuth redirect and missing shared 500 OpenAPI documentation were corrected. Stale README status/importer commands/port-binding/RapidAPI assumptions and future-schema comments were updated.

## 34. Remaining risks

No deployment exists. Operational concerns for the next reviewed phase include reproducible dependency resolution, hosting secrets/TLS/access-log policy, connection-pool sizing/timeouts, proxy behavior, production CORS/docs choices, backup/restore, and load measurements. Source provenance remains intentionally polymorphic and external writers must coordinate. READ COMMITTED permits cross-query snapshot changes. Search/random/metadata cost grows with catalogue size. Accepted lower-level string/serial rules remain partly importer-enforced. None prompted a new unreviewed migration during this audit.

## 35. Deviations

No additional schema change or Phase 9A repeat migration was needed. Existing dependency warnings remain after source-level investigation instead of speculative upgrades. Performance measurements use a temporary real localhost Uvicorn server, not an external deployment. PostgreSQL isolation/advisory behavior was directly tested; arbitrary uncoordinated external-writer correctness remains documented rather than falsely guaranteed. Full vulnerability scanning and deployment/load certification were not part of this phase. Work stops at Phase 9.

## 36. Final project tree

Source/docs/evidence tree below excludes environment directories, caches, package metadata, local logs, and ignored temporary audit files.

```text
.env.example
.gitignore
.mypy_cache/.gitignore
.pytest_cache/.gitignore
.pytest_cache/README.md
.ruff_cache/.gitignore
.venv/.gitignore
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
migrations/versions/8b41e2a9c730_enforce_variant_image_ownership.py
phase9_schema_audit.json
phase9_verification_results.json
PHASE_1_REPORT.md
PHASE_2_REPORT.md
PHASE_3_REPORT.md
PHASE_4_REPORT.md
PHASE_5_REPORT.md
PHASE_6_REPORT.md
PHASE_7_REPORT.md
PHASE_8_REPORT.md
PHASE_9_REPORT.md
PHASE_9_STOP_REPORT.md
PHASE_9A_REPORT.md
pyproject.toml
README.md
scripts/verify_phase8.py
scripts/verify_phase9.py
scripts/verify_phase9a.py
tests/__init__.py
tests/conftest.py
tests/test_card_filters.py
tests/test_cards_routes.py
tests/test_discovery.py
tests/test_health.py
tests/test_image_ownership.py
tests/test_importer.py
tests/test_models.py
tests/test_openapi.py
tests/test_ready.py
tests/test_schemas.py
tests/test_sets_routes.py
tests/test_system_audit.py
```

