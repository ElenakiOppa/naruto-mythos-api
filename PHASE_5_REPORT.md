# Naruto Mythos TCG Developer API — Phase 5 Report

Date: September 13, 2026  
Status: Implemented and verified against PostgreSQL and Swagger.  
Scope: Public Cards API only. Phases 1–4 preserved; Phase 6 not started.

## 1. Files created

| File | Purpose |
| --- | --- |
| app/api/v1/cards.py | Thin GET list/detail handlers under Cards |
| app/services/card_service.py | Parameterized card SQL queries and relationship loading |
| app/utils/error_docs.py | Reusable operation-specific error documentation builders |
| tests/test_cards_routes.py | 50 collected Phase 5 test cases |
| phase5_verification_results.json | Sanitized HTTP results, query counts, examples, and cleanup evidence |
| PHASE_5_REPORT.md | This report |

## 2. Files modified

| File | Change |
| --- | --- |
| app/api/router.py | Register Cards router |
| app/api/v1/sets.py | Correct OpenAPI 400/404 examples only |
| app/schemas/error.py | Remove misleading shared card-specific examples; preserve error fields and enum |
| README.md | Document endpoints, filters, sorting, pagination, images, and route order |

No database model, Alembic migration, or existing test was changed in Phase 5.
The Phase 4 SQLite fixture correction remains in place.

## 3. Routes implemented

- GET /v1/cards → PaginatedCardsResponse containing CardSummary items.
- GET /v1/cards/{public_id} → CardDetail.

Both routes use the Cards tag and dependency-injected database sessions.
Handlers validate pagination, call the service, and serialize Phase 3 schemas.
No public writes were introduced.

## 4. Supported filters

| Parameter | Behavior |
| --- | --- |
| name | Case-insensitive literal substring |
| set | Case-insensitive exact public set ID |
| number | Exact string card number |

Filters combine with AND and execute in SQL. Percent and underscore in name
are escaped as literal characters. Unknown set IDs produce an empty filtered
collection. No rarity/type/keyword/variant/stat-range filters were added.

## 5. Supported sorting

| Sort | Database value |
| --- | --- |
| number | cards.card_number |
| name | cards.name |
| rarity | cards.rarity |
| set | sets.name |
| release_date | sets.release_date |

Default: number ascending. All fields support asc/desc. Explicit allowlists
reject unsupported fields/directions. NULLS LAST applies in both directions;
card public ID ascending is always the secondary sort. Numbers remain strings:
1, 10, 2. Tests cover tied values and distinct dated/undated sets.

## 6. Pagination behavior

Existing utilities enforce page >= 1 and limit 1–100; defaults are page 1,
limit 50. A separate SQL count uses the filtered query before LIMIT/OFFSET.
Empty collections return 200 with total/pages zero. Beyond-end pages return
200 with empty data, accurate totals, and the requested page retained.

## 7. CardSummary behavior

Exactly: id, number, name, subtitle, type, rarity, set, images.
Detail-only fields are absent. The set is a SetSummary. Image responses contain
only type, URL, width, and height. For the new Cards routes, top-level images
are restricted in SQL to variant_id IS NULL.

## 8. CardDetail behavior

Includes all CardSummary fields plus chakra, power, faction, ability_text,
flavor_text, artist, keywords, and variants. Nullable values remain explicit
nulls, and empty relationships remain arrays. Variant images are nested under
their variant and do not also appear in top-level card images.
Lookup uses the exact public card ID; an internal UUID does not resolve a card.

## 9. Relationship loading strategy

List: an explicit to-one set join supports filtering/sorting; contains_eager
reuses that join to populate Card.set. selectinload fetches only direct card
images. No list queries load variants or keywords.

Detail: joinedload(Card.set), selectinload(Card.keywords), filtered
selectinload(Card.images), and selectinload(Card.variants) followed by
selectinload(CardVariant.images). Collections use separate batched queries.

populate_existing ensures an already-loaded ORM image collection is refreshed
with the route's direct-image restriction. No ORM relationship or schema was
changed; existing Phase 4 set-card behavior is preserved.

## 10. N+1 prevention and performance review

Regression tests start from a cleared identity map so fixture caching cannot
hide lazy loads. The list scenario includes 16 cards across multiple sets;
the detail scenario includes 13 variants with images and 13 keywords.
Upper query bounds detect per-item loads without requiring an exact count.

PostgreSQL service instrumentation, including schema serialization, measured:

- Filtered, paginated card list: 3 SQL statements.
- Card detail with keyword, variant, and both image levels: 5 SQL statements.

Inspection confirmed WHERE, ORDER BY, LIMIT/OFFSET, and COUNT occur in SQL.
The list does not fetch the full catalogue before slicing and does not load
variant/keyword collections. No caching infrastructure was added.

## 11. Error behavior and security review

| Condition | Status | Code |
| --- | --- | --- |
| Unknown card | 404 | CARD_NOT_FOUND |
| Invalid page/limit bounds | 400 | INVALID_PAGINATION |
| Invalid sort/order | 400 | INVALID_SORT |
| Malformed query types | 422 | FastAPI validation response |
| Unexpected exception | 500 | Existing INTERNAL_ERROR handler |

The existing runtime exception infrastructure is reused. The new routes are
GET-only. SQLAlchemy binds filter values; user text is never a SQL column name
or raw SQL. Tests include SQL-like name text and literal LIKE metacharacters.
Public schemas exclude internal UUID/foreign-key and provenance/storage fields.
No credentials, real catalogue data, or artwork were introduced. Images use
fictional example.invalid URLs; no artwork was downloaded.

## 12. Swagger documentation fix

Removed card-specific examples from shared ErrorResponse/ErrorDetail metadata.
Endpoint-specific examples now show SET_NOT_FOUND for set detail and set-card
404s, and CARD_NOT_FOUND for card detail 404s. List 400 documentation provides
separate pagination and sorting examples. Phase 4 runtime errors are unchanged.

## 13. OpenAPI verification

The live /openapi.json explicitly contains /v1/cards and
/v1/cards/{public_id}, with GET operations tagged Cards. All seven list query
parameters are covered by the automated OpenAPI test.

Verified referenced schemas: CardSummary, CardDetail, CardVariantResponse,
CardImageResponse, KeywordResponse, SetSummary, PaginationMeta,
PaginatedCardsResponse, ErrorResponse. Set/card 404 examples were checked
explicitly in both live verification and regression tests.

The dynamic public-ID route is declared last, with a comment requiring future
static routes to be inserted above it. No /random route exists.

## 14. PostgreSQL and Swagger verification

Target: localhost development database naruto_mythos; PostgreSQL 18.6.
Alembic current: 5f360cfd2561 (head). No upgrade or migration edit required.
A real Uvicorn server ran on 127.0.0.1:8000 using normal application settings;
HTTP verification used no dependency overrides.

28 live HTTP checks passed, covering health/readiness, list, basic and combined
filters, all 10 sort/direction combinations, pagination, detail relationships,
missing card, invalid sort/order/pagination, malformed page, and OpenAPI.

Swagger UI showed both endpoints under Cards. Executing the list and
TEST-001 detail operations through Try it out/Execute returned HTTP 200 with
the PostgreSQL fixture records. The detail visibly included the keyword,
variant image, and distinct top-level image. The verification server was stopped.

## 15. Temporary-data cleanup

Collision checks ran before fictional records were inserted. Exact created
primary keys were recorded for cleanup. Removed 2 sets, 4 cards, 2 images,
1 variant, and 1 keyword; associated card-keyword links cascade on deletion.
The recorded IDs were queried afterward and verified absent. No unrelated
records were targeted. The temporary cleanup manifest was deleted.

## 16. Tests added

50 new collected cases cover empty/one/many-card results; default/maximum/
beyond-end pagination; invalid and malformed parameters; exact, partial,
case-insensitive, combined, and no-match filters; literal wildcard and SQL-like
input; ten sort combinations; stable ties; null ordering; distinct release
dates; summary/detail shapes; populated and nullable fields; relationship
serialization; image separation; public-ID lookup; UUID rejection; exclusion
of internal/provenance fields; N+1 bounds; and explicit OpenAPI/error examples.

Parameterized cases are included in the count. Existing 93 cases were retained.

## 17. Full test results

Final command: python -m pytest -v

143 passed, 2 warnings in 3.86s.

Warnings are the same existing Starlette HTTP client and AnyIO BlockingPortal
deprecations. An initial new-fixture SQLAlchemy warning was corrected by adding
the variant to the session before relationship access; it is absent from the
final run. Focused Ruff E4/E7/E9/F checks on new Python modules, the error schema,
and new tests passed. New modules/tests were formatted.

## 18. Bugs discovered/fixed

- Fixed the previously reported shared Swagger error-example inconsistency.
- Prevented variant-image duplication in the new Cards API by applying a
  route-specific SQL image filter and adding list/detail regression coverage.
- Corrected fixture construction order to avoid a transient SQLAlchemy warning.

No PostgreSQL-specific defect or blocking database schema issue was discovered.

## 19. Deviations and scope

No functional scope deviations. contains_eager uses the necessary set join
instead of adding a redundant joinedload join for list responses. A small
error_docs helper avoids duplicating OpenAPI examples between routers.

Advanced filters, search, random card, rarity/keyword catalogues, importer,
schema changes, and Phase 6 were not implemented.

## 20. Final project tree

Generated below from project files, excluding environment files, dependency
folders, caches, and package metadata. Existing Phase 1–4 reports are retained.

```text
.env.example
.gitignore
PHASE_1_REPORT.md
PHASE_2_REPORT.md
PHASE_3_REPORT.md
PHASE_4_REPORT.md
PHASE_5_REPORT.md
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
pyproject.toml
tests/__init__.py
tests/conftest.py
tests/test_cards_routes.py
tests/test_health.py
tests/test_models.py
tests/test_openapi.py
tests/test_ready.py
tests/test_schemas.py
tests/test_sets_routes.py
```

## Fictional JSON responses

### GET /v1/cards

Actual response from the temporary PostgreSQL dataset (since removed):

```json
{
  "data": [
    {
      "id": "TEST-001",
      "number": "1",
      "name": "Test Character Alpha",
      "subtitle": null,
      "type": null,
      "rarity": "Rare",
      "set": {
        "id": "test-set-alpha",
        "code": "TSTA",
        "name": "Test Set Alpha",
        "edition": "Test Edition"
      },
      "images": [
        {
          "type": "front",
          "url": "https://example.invalid/card.png",
          "width": 100,
          "height": 140
        }
      ]
    },
    {
      "id": "TEST-B01",
      "number": "1",
      "name": "Test Character Alpha",
      "subtitle": null,
      "type": null,
      "rarity": "Rare",
      "set": {
        "id": "test-set-beta",
        "code": "TSTB",
        "name": "Test Set Beta",
        "edition": null
      },
      "images": []
    },
    {
      "id": "TEST-A03",
      "number": "10",
      "name": "Test Character Gamma",
      "subtitle": null,
      "type": null,
      "rarity": "Common",
      "set": {
        "id": "test-set-alpha",
        "code": "TSTA",
        "name": "Test Set Alpha",
        "edition": "Test Edition"
      },
      "images": []
    },
    {
      "id": "TEST-002",
      "number": "2",
      "name": "Test Character Beta",
      "subtitle": null,
      "type": null,
      "rarity": null,
      "set": {
        "id": "test-set-alpha",
        "code": "TSTA",
        "name": "Test Set Alpha",
        "edition": "Test Edition"
      },
      "images": []
    }
  ],
  "pagination": {
    "page": 1,
    "limit": 50,
    "total": 4,
    "pages": 1,
    "has_next": false,
    "has_previous": false
  }
}
```

### GET /v1/cards/TEST-001

```json
{
  "id": "TEST-001",
  "number": "1",
  "name": "Test Character Alpha",
  "subtitle": null,
  "type": null,
  "rarity": "Rare",
  "chakra": null,
  "power": null,
  "faction": null,
  "ability_text": null,
  "flavor_text": null,
  "artist": null,
  "set": {
    "id": "test-set-alpha",
    "code": "TSTA",
    "name": "Test Set Alpha",
    "edition": "Test Edition"
  },
  "keywords": [
    {
      "slug": "test-keyword",
      "name": "Test Keyword"
    }
  ],
  "variants": [
    {
      "id": "TEST-001-holo",
      "type": "holographic",
      "finish": null,
      "rarity": null,
      "collector_number": null,
      "language": "EN",
      "edition": null,
      "serial_numbered": false,
      "serial_total": null,
      "images": [
        {
          "type": "front",
          "url": "https://example.invalid/variant.png",
          "width": null,
          "height": null
        }
      ]
    }
  ],
  "images": [
    {
      "type": "front",
      "url": "https://example.invalid/card.png",
      "width": 100,
      "height": 140
    }
  ]
}
```

### 404 CARD_NOT_FOUND

```json
{
  "error": {
    "code": "CARD_NOT_FOUND",
    "message": "Card not found."
  }
}
```
