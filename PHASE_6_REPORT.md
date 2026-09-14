# Naruto Mythos TCG Developer API — Phase 6 Report

Date: September 13, 2026  
Status: Advanced Card Filtering implemented and verified.  
Scope: Extend GET /v1/cards only. Phase 7 not started.

## 1. Files created

| File | Purpose |
| --- | --- |
| app/services/card_filters.py | Frozen typed filter structure and explicit SQL predicates/validation |
| tests/test_card_filters.py | 78 advanced-filter regression cases |
| phase6_verification_results.json | Live request results, parameterized SQL, query counts, and cleanup evidence |
| PHASE_6_REPORT.md | This report |

## 2. Files modified

| File | Change |
| --- | --- |
| app/api/v1/cards.py | Ten new query parameters, descriptions, and typed service input |
| app/services/card_service.py | Apply advanced predicates before count and pagination |
| app/utils/error_docs.py | Card-specific invalid-filter examples alongside existing errors |
| tests/test_cards_routes.py | Extend the exact OpenAPI parameter-set assertion from 7 to 17 |
| README.md | Document advanced matching, ranges, AND behavior, and fictional requests |

The prior OpenAPI test was updated for the intentional additive API change;
its equality assertion remains exact. All 143 previous cases remain.
No database schema, migration, public response schema, or detail-route behavior changed.

## 3. New filters

rarity, type, keyword, variant, language, edition, chakra_min, chakra_max,
power_min, power_max. Existing name, set, number, sorting, and pagination remain.
No additional endpoint was introduced.

## 4. Exact matching semantics

| Filter | Match target |
| --- | --- |
| rarity | cards.rarity |
| type | cards.card_type; public parameter remains type |
| keyword | keywords.slug |
| variant | card_variants.variant_type |
| language | Parent sets.language, never variant language |
| edition | Parent sets.edition, never variant edition |

All six use case-insensitive equality with bound parameters. Values are not
hard-coded or enumerated. Unknown values produce HTTP 200 with an empty collection.
NULL editions/rarities/types do not equal supplied values. Exact matching treats
percent and underscore literally. Existing name matching remains a case-insensitive
substring with LIKE metacharacters escaped; number remains an exact string.

## 5. Range validation behavior

All four bounds must be nonnegative. Minimum and maximum are inclusive. Equal
bounds select an exact statistic value. Supplied comparisons exclude NULL stats
naturally; nulls are never coerced to zero. With no bound, NULL stats remain eligible.

Negative bounds return HTTP 400 INVALID_FILTER with the parameter-specific message:
`chakra_min must be greater than or equal to 0.` (and equivalent for the other bounds).
Reversed ranges return HTTP 400 INVALID_FILTER:
`chakra_min cannot be greater than chakra_max.` or
`power_min cannot be greater than power_max.`
Malformed integer values continue to return FastAPI HTTP 422.

## 6. Combined-filter behavior

All supplied filters compose with AND, including Phase 5 filters. Verified
combinations include rarity/type, set/rarity, set/number, set/variant, set/keyword,
rarity/keyword, variant/keyword, language/edition, both inclusive stat ranges,
rarity/type/variant, set/rarity/keyword/variant, and
name/set/rarity/type/chakra_min/power_min. No OR expression language was added.

## 7. Duplicate-prevention strategy

Keyword and variant filters use relationship .any() predicates, producing
correlated SQL EXISTS. They do not join collection rows into the outer card query.
A card with three matching variants still contributes one outer row and one count.
Fixtures also include two differently-cased keyword slugs that match the same
case-insensitive input on one card. Combined keyword/variant tests verify unique
items and totals across pages, including a beyond-end page.

## 8. SQLAlchemy implementation approach

CardFilters is a frozen dataclass with ten explicit optional fields.
apply_card_filters validates stat bounds and appends finite, explicit predicates.
The existing card service retains basic filters and its to-one set join, applies
the advanced helper, then counts and paginates. The route only parses parameters,
validates pagination, constructs filter input, calls the service, and serializes.

No generic query language, repository layer, raw SQL construction, or schema change
was needed. Related keyword/variant data is used in EXISTS only, not loaded into
CardSummary. Existing set/image eager loading and direct-image separation remain.

## 9. Pagination behavior with filters

The filtered SQL statement feeds COUNT before LIMIT/OFFSET. Defaults remain
page=1, limit=50, maximum limit=100. Metadata represents unique matching cards.
Tests and PostgreSQL verification checked filtered total=2, pages=2 at limit=1,
one distinct card on each available page, and an empty third page with total retained.

## 10. Sorting behavior with filters

All five existing fields remain: number, name, rarity, set, release_date, each in
asc/desc order. Default is lexical number ascending. NULLS LAST and public ID
ascending as a secondary key are preserved. All ten sort/direction combinations
were tested with a rarity filter against both SQLite and PostgreSQL.

## 11. Query-count/performance results

PostgreSQL service instrumentation includes public-schema serialization and fresh
sessions. Sixteen more matching cards, each with three holographic variants, were
added between measurements:

| Predicate | Matching cards before → after | SQL queries before → after |
| --- | --- | --- |
| keyword=test-keyword | 3 → 19 | 3 → 3 |
| variant=holographic | 2 → 18 | 3 → 3 |
| Both predicates | 2 → 18 | 3 → 3 |

The three statements are filtered count, filtered/sorted/paginated card+set selection,
and batched direct-image selection. SQL evidence confirms EXISTS in the count and
selection, and no per-card relationship fetching. Automated growth tests cover all
three scenarios with query bounds. These measurements demonstrate stable query
counts for the tested page sizes; they are not a large-catalogue latency benchmark.
No caching was added.

## 12. Security tests

SQL-like values were tested as literal filter text, including:
- rarity: `' OR 1=1 --`
- keyword: `%_test`
- variant: `'; DROP TABLE cards; --`

They returned empty collections. Literal wildcard behavior is also covered for
rarity, type, language, and edition. SQLAlchemy binds all filter values; allowed
sort columns and statistic columns are chosen only by server-owned code. Existing
name wildcard/injection regressions still pass. CardSummary continues to omit
keywords, variants, internal IDs, foreign keys, and source metadata. Credentials
were not printed or saved. Fixtures contain only fictional data.

## 13. Swagger verification

The actual Swagger Try it out/Execute UI was used against the normal PostgreSQL-backed
Uvicorn server. Each requested query returned HTTP 200:

- rarity=Rare
- variant=holographic
- keyword=test-keyword
- chakra_min=2&power_min=3

All ten new inputs were visible with descriptions, including parent-set language,
parent-set edition, and inclusive range semantics. The example selector includes
pagination, sort, chakra_range, power_range, and negative_stat.

## 14. OpenAPI verification

Live /openapi.json and automated assertions confirm exactly 17 described parameters:
page, limit, name, set, number, sort, order, rarity, type, keyword, variant, language,
edition, chakra_min, chakra_max, power_min, power_max.

The public type parameter does not expose card_type. The 400 documentation contains
three INVALID_FILTER examples alongside INVALID_PAGINATION/INVALID_SORT examples.
Set-specific 404 examples still show SET_NOT_FOUND; card 404 shows CARD_NOT_FOUND.

## 15. PostgreSQL verification

Database: local development naruto_mythos, PostgreSQL 18.6.
Alembic current and heads both report 5f360cfd2561 (head). No migration was run.
The application ran with its normal settings and no dependency overrides.

78 live card-filter HTTP checks passed, plus health/readiness and explicit OpenAPI
checks. Coverage includes every new filter, exact/case-insensitive/unknown values,
all range forms, negative and reversed ranges, malformed values, composed filters,
unique filtered pagination, all supported sorting, and hostile-looking text.
Additional SQL instrumentation and four Swagger executions completed successfully.

## 16. Temporary-data cleanup

Collision checks preceded insertion. Exact ORM-created IDs were recorded during
flush, before cleanup. The growth dataset was included in the manifest.
Removed exactly 19 sets, 21 cards, 53 variants, and 3 keywords. Queried every recorded
ID afterward and confirmed absence; also verified associated card-keyword links
were absent. No images were inserted for this phase. No unrelated records were
targeted, no tables dropped, and no migration downgraded. The temporary cleanup
manifest was removed and the verification server stopped.

## 17. Tests added

78 new collected cases: matching and case-insensitivity; unknown values; NULL
handling; keyword/variant multiplicity; inclusive/zero/stat bounds; negative and
reversed ranges; malformed values; all requested combination categories; literal
SQL/wildcard text; filtered totals/pages; ten filtered sorting combinations;
three query-growth scenarios; and exact OpenAPI/error-documentation checks.
The previous OpenAPI parameter assertion was extended without removing old parameters
or weakening its equality check. Existing list/detail and Phase 1–4 tests remain.

## 18. Full test results

Final full run: python -m pytest -v

**221 passed, 2 warnings in 6.63s.** Baseline 143 + 78 new cases.

Warnings remain the existing Starlette HTTP client and AnyIO BlockingPortal
deprecations. Focused Ruff E4/E7/E9/F checks passed for all changed/new Python
modules and tests. Relevant files were formatted.

## 19. Bugs discovered/fixed

No existing runtime bug or PostgreSQL-specific defect was discovered. The new
implementation prevents join-induced duplicate rows by construction and validates
range errors through the existing APIError mechanism. No blocking database issue
was found.

## 20. Deviations from specification

None in functional scope. A small typed filter helper was used as allowed by the
brief. Case-insensitive keyword matching was practical and implemented. The test
fixture intentionally uses two differently-cased unique slugs to exercise multiple
matching keyword rows without violating the database's unique-slug constraint.

No search, random card, rarity/keyword catalogue endpoint, importer, cache,
authentication, RapidAPI integration, or Phase 7 work was added.

## 21. Final project tree

Project files below exclude the private .env, installed dependencies, caches,
and package metadata. Existing earlier reports are retained.

```text
.env.example
.gitignore
PHASE_1_REPORT.md
PHASE_2_REPORT.md
PHASE_3_REPORT.md
PHASE_4_REPORT.md
PHASE_5_REPORT.md
PHASE_6_REPORT.md
README.md
alembic.ini
app/__init__.py
app/api/__init__.py
app/api/router.py
app/api/v1/__init__.py
app/api/v1/cards.py
app/api/v1/health.py
app/api/v1/ready.py
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
app/services/set_service.py
app/utils/__init__.py
app/utils/error_docs.py
app/utils/errors.py
app/utils/pagination.py
data/README.md
importer/.gitkeep
migrations/env.py
migrations/script.py.mako
migrations/versions/5f360cfd2561_initial_schema.py
phase5_verification_results.json
phase6_verification_results.json
pyproject.toml
tests/__init__.py
tests/conftest.py
tests/test_card_filters.py
tests/test_cards_routes.py
tests/test_health.py
tests/test_models.py
tests/test_openapi.py
tests/test_ready.py
tests/test_schemas.py
tests/test_sets_routes.py
```

## Fictional request and response examples

### Combined filter — HTTP 200

`GET /v1/cards?set=test-set-alpha&rarity=Rare&keyword=test-keyword&variant=holographic`

Actual temporary-dataset response (records since removed):

```json
{
  "data": [
    {
      "id": "TEST6-1",
      "number": "1",
      "name": "Test Alpha",
      "subtitle": null,
      "type": "Character",
      "rarity": "Rare",
      "set": {
        "id": "test-set-alpha",
        "code": null,
        "name": "Test Set Alpha",
        "edition": "Test Edition"
      },
      "images": []
    }
  ],
  "pagination": {
    "page": 1,
    "limit": 50,
    "total": 1,
    "pages": 1,
    "has_next": false,
    "has_previous": false
  }
}
```

### Unknown rarity — HTTP 200

`GET /v1/cards?rarity=unknown`

```json
{
  "data": [],
  "pagination": {
    "page": 1,
    "limit": 50,
    "total": 0,
    "pages": 0,
    "has_next": false,
    "has_previous": false
  }
}
```

### Invalid range — HTTP 400

`GET /v1/cards?chakra_min=5&chakra_max=2`

```json
{
  "error": {
    "code": "INVALID_FILTER",
    "message": "chakra_min cannot be greater than chakra_max."
  }
}
```

### Invalid range — HTTP 400

`GET /v1/cards?power_min=5&power_max=2`

```json
{
  "error": {
    "code": "INVALID_FILTER",
    "message": "power_min cannot be greater than power_max."
  }
}
```

### Invalid range — HTTP 400

`GET /v1/cards?chakra_min=-1`

```json
{
  "error": {
    "code": "INVALID_FILTER",
    "message": "chakra_min must be greater than or equal to 0."
  }
}
```

