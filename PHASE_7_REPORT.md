# Naruto Mythos TCG Proceed with PHASE 8 ONLY: Catalogue Importer and Data Provenance.

Phases 1 through 7 have been reviewed and APPROVED.

Verified baseline:

- PostgreSQL 18.6
- Alembic: 5f360cfd2561 (head)
- Tests: 293 passed
- Public read/discovery API complete
- PostgreSQL verification complete
- Swagger verification complete
- No real Naruto Mythos catalogue data currently stored

IMPORTANT:

Phase 8 builds the IMPORT PIPELINE.

It does NOT authorize scraping or redistribution of copyrighted/licensed
content.

Do NOT scrape narutotcgmythos.com automatically in this phase.

Do NOT reverse-engineer undocumented Firebase/internal endpoints.

Do NOT download card artwork.

Do NOT add real Naruto card data to committed fixtures.

Do NOT publish or deploy anything.

The importer must accept approved/local normalized source data.

==================================================
1. OBJECTIVE
==================================================

Build a production-quality importer capable of safely importing Naruto
Mythos catalogue data into the existing database once an approved dataset
is available.

Pipeline:

approved source
      ↓
raw/source input
      ↓
parser
      ↓
normalized importer models
      ↓
validation
      ↓
duplicate/change detection
      ↓
dry-run report
      ↓
transactional database import
      ↓
source_records provenance

The importer must be:

- repeatable
- idempotent
- auditable
- transactional
- dry-run capable
- safe against accidental deletion
- deterministic
- source-aware

==================================================
2. INPUT FORMAT
==================================================

Define a normalized JSON import format.

Create something similar to:

data/schema/catalogue.schema.json

and fictional examples under:

data/examples/

Example structure:

{
  "source": {
    "name": "fictional-test-source",
    "url": "https://example.invalid/catalogue",
    "retrieved_at": "2026-09-13T12:00:00Z"
  },

  "sets": [
    {
      "id": "test-set-alpha",
      "code": "TSTA",
      "name": "Test Set Alpha",
      "edition": "Test Edition",
      "language": "EN",
      "release_date": "2026-01-01",
      "printed_total": 100,
      "total_with_variants": 150,

      "cards": [
        {
          "id": "TEST-001",
          "number": "001",
          "name": "Test Character Alpha",
          "subtitle": null,
          "type": "Character",
          "rarity": "Rare",
          "chakra": 4,
          "power": 5,
          "faction": "Test Village",
          "ability_text": null,
          "flavor_text": null,
          "artist": null,

          "keywords": [
            {
              "slug": "test-keyword",
              "name": "Test Keyword"
            }
          ],

          "variants": [
            {
              "id": "TEST-001-holographic",
              "type": "holographic",
              "finish": "holo",
              "rarity": null,
              "collector_number": null,
              "language": "EN",
              "edition": null,
              "serial_numbered": false,
              "serial_total": null,
              "images": []
            }
          ],

          "images": []
        }
      ]
    }
  ]
}

This is an IMPORT format, not necessarily identical to public API responses.

==================================================
3. IMPORT PYDANTIC MODELS
==================================================

Create dedicated importer validation models.

Do NOT reuse public response schemas directly.

Importer schemas have different responsibilities.

Suggested:

importer/schemas.py

Models such as:

ImportSource
ImportCatalogue
ImportSet
ImportCard
ImportKeyword
ImportVariant
ImportImage

Use Pydantic v2.

Validate before database writes begin.

==================================================
4. IMPORT VALIDATION
==================================================

Validate at minimum:

Set:
- id non-empty
- name non-empty
- printed_total >= 0 if supplied
- total_with_variants >= 0 if supplied

Card:
- id non-empty
- number non-empty
- name non-empty
- chakra >= 0 if supplied
- power >= 0 if supplied

Variant:
- id non-empty
- type non-empty
- serial_total > 0 if supplied
- if serial_numbered=false and serial_total supplied, decide/document policy

Image:
- URL valid
- width > 0 if supplied
- height > 0 if supplied

Keyword:
- slug non-empty
- name non-empty

Source:
- name required
- source URL optional if local/manual source
- retrieved_at required

Reject malformed input BEFORE changing the database.

==================================================
5. CROSS-RECORD VALIDATION
==================================================

Validate catalogue-wide rules before writing:

- duplicate set public IDs
- duplicate card public IDs
- duplicate variant public IDs
- duplicate card numbers within one set
- conflicting keyword definitions for same slug
- duplicate variants under one card
- duplicate images where clearly identical
- card IDs reused across sets
- impossible/invalid references

Return clear importer validation errors.

Do not rely solely on database IntegrityError.

==================================================
6. NORMALIZATION POLICY
==================================================

Normalization must be conservative.

Allowed examples:

- trim surrounding whitespace
- normalize empty optional strings to null where explicitly appropriate
- normalize documented variant labels using an explicit mapping table
- normalize keyword slugs consistently

DO NOT:

- rewrite card names
- translate text
- invent missing rarity
- infer chakra/power
- infer variant type from artwork
- silently modify collector numbers
- convert card numbers to integers

Preserve source values where meaningful.

Card numbers and collector numbers remain strings.

==================================================
7. VARIANT NORMALIZATION
==================================================

Variant types are intentionally database strings, not enums.

Create an explicit normalization mapping mechanism.

Example fictional aliases:

"Holo" -> "holographic"
"Holographic" -> "holographic"

But DO NOT hard-code Naruto-specific assumptions unless they come from an
approved dataset/source specification.

Unknown variant types must remain importable.

Normalize only aliases explicitly configured.

Preserve original source value in provenance/source metadata where
possible.

==================================================
8. IMAGE POLICY
==================================================

Importer must support image metadata but must NOT download or mirror images.

Image input may contain:

url
type
width
height
source_name
source_url

Set:

hosted_by_us = false

for externally referenced images.

Do not fetch image bytes.

Do not validate URLs by downloading them.

Only structural URL validation is required.

==================================================
9. SOURCE PROVENANCE
==================================================

Use the existing source_records table.

Every imported:

set
card
variant

must have provenance.

Where practical, images/keywords may also have provenance, but do not
change the database schema merely to force this if the existing polymorphic
design already supports them.

Record:

entity_type
entity_id
source_name
source_url
external_id
content_hash
first_seen
last_seen

Use internal entity UUID for entity_id.

source_records is internal infrastructure and must remain absent from the
public API.

==================================================
10. CONTENT HASH
==================================================

Create deterministic content hashes for imported entities.

Use a stable canonical representation.

Requirements:

- deterministic key ordering
- stable null representation
- UTF-8
- SHA-256

Hash normalized semantic data.

Do not include volatile values such as:

retrieved_at
first_seen
last_seen

in the entity content hash.

The same normalized record imported twice should produce the same hash.

==================================================
11. IMPORT MODES
==================================================

Support:

--dry-run

and actual import.

Suggested CLI:

python -m importer.cli catalogue.json --dry-run

python -m importer.cli catalogue.json

Dry run must:

- parse
- validate
- normalize
- compare with DB
- generate complete change plan

but perform ZERO persistent database writes.

==================================================
12. CHANGE PLAN
==================================================

Before applying changes, classify:

sets:
created
updated
unchanged

cards:
created
updated
unchanged

variants:
created
updated
unchanged

keywords:
created
updated
unchanged

images:
created
updated
unchanged

relationships:
created
removed/unchanged as applicable

Return counts and preferably entity public IDs.

Example:

{
  "sets": {
    "created": ["test-set-alpha"],
    "updated": [],
    "unchanged": []
  },
  "cards": {
    "created": ["TEST-001"],
    "updated": [],
    "unchanged": []
  }
}

The plan must be deterministic.

==================================================
13. IDEMPOTENCY
==================================================

Importing identical normalized data twice must not create duplicates.

Expected:

First import:
created > 0

Second import:
created = 0
updated = 0
unchanged > 0

Test this thoroughly.

==================================================
14. UPDATE BEHAVIOR
==================================================

If an existing entity with the same public ID has changed normalized data:

update the existing row.

Do NOT delete/recreate it.

Internal UUID should remain stable.

Example:

TEST-001
name changes from:
Test Character Alpha

to:
Test Character Alpha Updated

The existing Card UUID must remain unchanged.

Update provenance:

content_hash
last_seen

Preserve:

first_seen

==================================================
15. SOURCE OWNERSHIP / MULTIPLE SOURCES
==================================================

Do not assume there will only ever be one source.

source_records must allow the same entity to be observed from multiple
sources.

An import from Source B must not destroy Source A provenance.

Think carefully about conflicting sources.

For Phase 8:

DO NOT automatically resolve conflicting source values.

Use deterministic source/import precedence based on the dataset being
explicitly imported, but record each provenance independently.

Document this policy clearly.

==================================================
16. SAFE DELETION POLICY
==================================================

Default behavior:

NEVER delete catalogue entities merely because they are missing from an
import file.

Absence is not proof of deletion.

This applies to:

sets
cards
variants
keywords
images

No destructive synchronization in Phase 8.

If an existing entity is absent from input:

leave it unchanged.

Do not add --sync or --delete-missing yet.

==================================================
17. RELATIONSHIP UPDATE POLICY
==================================================

This needs careful handling.

If an imported card explicitly supplies its complete keyword list:

synchronize that card's keyword associations to the supplied list.

But:

do not delete the Keyword entity itself merely because association is
removed.

For variants/images:

default Phase 8 policy should be non-destructive unless the importer can
prove the supplied collection is authoritative and complete.

Prefer:

create/update supplied records
leave omitted existing records alone

Document exact behavior.

==================================================
18. TRANSACTION SAFETY
==================================================

Actual import must run transactionally.

If any database write fails:

rollback the entire import.

No half-imported catalogue.

Do not commit entity-by-entity.

Dry-run must leave database unchanged even if planning requires flush-like
logic.

==================================================
19. DATABASE LOOKUPS
==================================================

Avoid one SELECT per imported entity where practical.

Preload existing relevant records in batches.

This importer may eventually process hundreds or thousands of cards.

Avoid obvious N+1 import behavior.

Do not optimize prematurely into unreadable bulk SQL.

==================================================
20. IMPORT REPORT
==================================================

Every execution should produce a structured report.

Include:

source
dry_run
started_at
finished_at

validation summary

created counts
updated counts
unchanged counts

warnings
errors

Do NOT include:

database credentials
internal UUIDs in normal user-facing output
full sensitive environment configuration

Machine-readable JSON output should be possible.

==================================================
21. LOGGING
==================================================

Use structured, useful logs.

Log:

source name
input file
validation status
entity counts
planned changes
transaction result
duration

Do not log:

DATABASE_URL
credentials
entire ability/flavor text bodies unnecessarily
raw copyrighted catalogue dumps

==================================================
22. FICTIONAL FIXTURES
==================================================

All committed importer examples/tests must remain fictional.

Create fixtures covering:

- one set
- multiple sets
- cards
- keywords
- variants
- direct card images
- variant images
- null optional fields
- numbered variant
- unknown variant type

Use example.invalid image/source URLs.

No Naruto characters.
No real Mythos set names.
No real card text.
No actual artwork.

==================================================
23. VALIDATION TESTS
==================================================

Test malformed input:

- invalid JSON
- missing source
- missing retrieved_at
- empty set ID
- duplicate set ID
- duplicate card ID
- duplicate variant ID
- duplicate number within set
- negative stats
- invalid serial total
- invalid image dimensions
- invalid image URL
- conflicting keyword definitions

Confirm database remains unchanged.

==================================================
24. DRY-RUN TESTS
==================================================

Test:

- empty DB
- existing DB
- creates detected
- updates detected
- unchanged detected
- relationship changes detected
- no writes
- no provenance writes
- repeated dry run identical
- deterministic plan ordering

==================================================
25. IMPORT TESTS
==================================================

Test:

- first import creates expected entities
- second identical import is idempotent
- changed entity updates in place
- internal UUID remains stable
- first_seen preserved
- last_seen updated
- content hash changes when semantic data changes
- content hash unchanged for identical data
- source_records created
- second source adds provenance without deleting first source
- missing entities are not deleted
- removed keyword association behavior follows documented policy
- omitted variant remains
- omitted image remains
- rollback on failure

==================================================
26. PUBLIC API REGRESSION
==================================================

After importing fictional data, exercise:

GET /v1/sets
GET /v1/sets/{id}
GET /v1/sets/{id}/cards
GET /v1/cards
GET /v1/cards/{id}
GET /v1/cards/random
GET /v1/rarities
GET /v1/keywords
GET /v1/keywords/{slug}/cards
GET /v1/search

Confirm imported records serialize correctly through the existing public API.

The importer must adapt to the API/database contract.

Do NOT alter public responses merely to make importer implementation easier.

==================================================
27. POSTGRESQL IMPORT VERIFICATION
==================================================

Perform real PostgreSQL verification.

Before:

confirm Alembic remains:

5f360cfd2561 (head)

Use a fictional JSON catalogue.

Run:

dry-run

Confirm:
database unchanged.

Run:
actual import.

Confirm:
database populated correctly.

Run:
same import again.

Confirm:
idempotent.

Modify one fictional field.

Run dry-run.

Confirm:
one update detected.

Run actual import.

Confirm:
same internal UUID retained.

Test:
second fictional source provenance.

Test:
missing entity does not delete it.

Test:
transaction rollback.

==================================================
28. CLEANUP
==================================================

Record exact fictional records created during PostgreSQL verification.

After verification:

remove ONLY Phase 8 fictional verification data.

Verify all recorded entities and provenance rows are gone.

Do not alter migrations.

Do not drop tables.

==================================================
29. PERFORMANCE VERIFICATION
==================================================

Create a larger fictional dataset, for example:

500 cards
multiple sets
multiple keywords
variants/images

Measure query behavior.

The importer should not execute an obvious:

1 + N + N + N

lookup pattern.

Report:

dataset size
SQL statement count
dry-run duration
actual-import duration

Do not establish arbitrary performance pass/fail numbers yet.

We want a baseline.

==================================================
30. SECURITY
==================================================

Importer input is untrusted.

Verify:

- file path handling is safe
- malformed JSON handled cleanly
- SQLAlchemy parameterization used
- URLs are data only
- URLs are not fetched
- no arbitrary code execution
- no shell interpolation
- no credentials in reports
- no public write endpoints introduced

==================================================
31. README
==================================================

Document importer usage.

Include:

normalized JSON structure
dry-run
actual import
idempotency
safe deletion policy
source provenance
content hashes
image policy

Make it VERY clear:

The importer accepts approved/local datasets.

It does not automatically scrape Naruto Mythos.

==================================================
32. DO NOT SCRAPE
==================================================

This requirement is explicit.

Do not:

- request narutotcgmythos.com
- crawl collection-guide
- inspect undocumented Firebase requests
- reverse-engineer internal endpoints
- download artwork
- build a scraper

Phase 8 is importer infrastructure only.

==================================================
33. FULL TEST SUITE
==================================================

Baseline:

293 passed

Run entire suite after importer implementation.

Do not weaken previous tests.

Run focused lint/static checks.

==================================================
34. PHASE 8 REPORT
==================================================

Return a detailed Phase 8 report including:

1. Files created
2. Files modified
3. Normalized import format
4. Validation rules
5. Cross-record validation
6. Normalization policy
7. Variant normalization
8. Image policy
9. Provenance implementation
10. Content hashing
11. Dry-run behavior
12. Change-plan format
13. Idempotency
14. Update behavior
15. Multi-source behavior
16. Deletion policy
17. Relationship policy
18. Transaction behavior
19. Query/performance behavior
20. CLI usage
21. PostgreSQL verification
22. Public API regression verification
23. Cleanup
24. Tests added
25. Full test results
26. Bugs discovered/fixed
27. Deviations
28. Final project tree

Include fictional importer examples only.

STOP after Phase 8.

Do NOT scrape real Naruto data.

Do NOT begin Phase 9.Developer API — Phase 7 Report

Date: September 13, 2026  
Status: Implemented, tested, and verified against PostgreSQL and Swagger.  
Scope: Discovery, metadata, search, and random card only. Phase 8 not started.

## 1. Files created

| File | Purpose |
| --- | --- |
| app/api/v1/metadata.py | Three metadata routes |
| app/api/v1/search.py | Bounded search route and operation-specific errors |
| app/services/metadata_service.py | SQL counts and keyword-card delegation |
| app/services/search_service.py | SQL candidate filtering/ranking and bounded merge |
| app/utils/slugs.py | Deterministic presentation slug utility |
| tests/test_discovery.py | 72 new collected test cases |
| phase7_verification_results.json | Sanitized live request, SQL, ranking, and cleanup evidence |
| PHASE_7_REPORT.md | This report |

## 2. Files modified

| File | Change |
| --- | --- |
| app/api/v1/cards.py | Static random route before public-ID detail |
| app/services/card_service.py | Shared summary/detail loading and isolated random selection |
| app/api/router.py | Register metadata and search routers |
| app/schemas/error.py | Add KEYWORD_NOT_FOUND |
| tests/test_cards_routes.py | Update the previous random-route absence assertion to presence |
| README.md | Document all five routes, ranking, limits, metadata, and examples |

No model, migration, or successful-response schema changed. All previous 221 test
cases remain; the obsolete absence assertion was updated for the newly authorized
endpoint, and new tests explicitly verify static-route precedence.

## 3. Endpoints implemented

| Endpoint | Tag | Successful response |
| --- | --- | --- |
| GET /v1/cards/random | Cards | CardDetail |
| GET /v1/rarities | Metadata | list[RarityCatalogItem] |
| GET /v1/keywords | Metadata | list[KeywordCatalogItem] |
| GET /v1/keywords/{slug}/cards | Metadata | PaginatedCardsResponse |
| GET /v1/search | Search | SearchResponse |

All are read-only GET routes using the existing database dependency and error handling.

## 4. Random-card strategy

The service applies ORDER BY random() LIMIT 1 to the shared CardDetail query.
This is appropriate for the expected initial catalogue size; PostgreSQL must still
consider the candidate rows, so selection can be optimized later for a large catalogue.
No speculative random-ID algorithm was added. Empty catalogue: 404 CARD_NOT_FOUND,
message `No cards available.` The static route is declared before /{public_id}.
Tests and live verification distinguish /random from /randomish; the latter remains
a public-ID lookup with message `Card not found.` when absent.

## 5. Rarity aggregation and slug behavior

One SQL GROUP BY counts canonical cards for each exact non-null stored rarity name.
Ordering is card_count descending, then name ascending. Values are not hard-coded.
Case-distinct names remain separate. Slugs lowercase and trim names, replace runs
of non-alphanumeric characters with one hyphen, and strip boundary hyphens. Unicode
letters/digits are retained. Punctuation-only names yield an empty slug.

Rare → rare; Super Rare → super-rare; Test / Rare → test-rare.
Distinct names whose slugs collide remain separate entries with their own counts.
A slug is presentation metadata, never a database identity or merge key.

## 6. Keyword aggregation

One SQL outer join and COUNT(DISTINCT card_id) produces unique-card counts. Keywords
with no cards remain present with count zero. Ordering is count descending, name
ascending, then slug ascending. Internal keyword IDs are never serialized.

## 7. Keyword card listing

The service checks for a case-insensitive public slug match and delegates to the
existing card list service with CardFilters(keyword=slug). This reuses EXISTS,
counting, all five sorts, stable ties, NULLS LAST, direct images, and CardSummary.
Case-distinct stored slugs matching the same input produce a unique union, consistent
with the existing Phase 6 keyword filter. Missing slug: 404 KEYWORD_NOT_FOUND /
`Keyword not found.` Existing zero-card keyword: 200 with an empty collection.
Defaults: page 1, limit 50, number ascending; maximum limit 100.

## 8. Search matching

q is required. Leading/trailing whitespace is trimmed; at least two characters must
remain. Missing q uses FastAPI 422. Present short/blank q returns 400 INVALID_FILTER /
`Search query must contain at least 2 characters.`

Literal case-insensitive substring fields:
- Card: name, public_id, card_number, subtitle.
- Set: name, public_id, code.
- Keyword: name, slug.

LIKE percent/underscore metacharacters are escaped. All input values use bound
SQLAlchemy parameters. Successful results use the existing discriminated union:
card/CardSummary, set/SetSummary, keyword/KeywordResponse.

## 9. Search ranking

Each SQL query computes rank: exact public ID/slug, exact name, name prefix, then
other substring. Overall ordering first compares rank, then type priority card/set/
keyword. Within each type, lowercase name, original name, and public identifier
provide deterministic tie-breaking under the database's collation. SQL row ordinals
are retained when merging, so Python does not apply a different alphabetical collation.

Live ranking verification also confirmed that subtitle/keyword substring matches
follow stronger identifier/name matches. Tests cover name ties broken by public ID.

## 10. Search result limiting

Default limit 20, allowed 1–50. Invalid bounds return 400 INVALID_PAGINATION /
`Search limit must be between 1 and 50.` Malformed integer types return 422.

Each entity query fetches at most the requested limit. At most 3 × limit candidates
are merged, and the final combined list is truncated to limit. Fetching limit from
each type is sufficient: a later candidate already has limit predecessors of its own
type. No entire table is loaded in Python and no search pagination was added.

## 11. Duplicate prevention

Search uses one OR predicate per entity query; multiple matching fields do not create
multiple rows. Keyword-card listing retains the existing EXISTS predicate, avoiding
collection joins that multiply cards. Metadata counts use canonical card rows or
COUNT(DISTINCT card_id), and slug collisions never merge rarity names.

## 12. Relationship loading

Random and ordinary detail share the same query builder: joined set, batched keywords,
batched direct images, batched variants, and batched variant images. Direct images
use variant_id IS NULL. Variant images remain only in the corresponding variant.

Search uses joined set and batched direct images for CardSummary, without card variant
or keyword relationship loading. Keyword-card listing reuses Phase 5/6 loading.
The Phase 1–6 regression suite confirms prior successful-response behavior remains.

## 13. Query-count/performance results

Measured PostgreSQL service statements including serialization on the grown dataset:

| Operation | Statements |
| --- | --- |
| Random CardDetail | 5 |
| Rarity catalogue | 1 |
| Keyword catalogue | 1 |
| Keyword card listing | 4 |
| Search | 4 |

SQL evidence verifies metadata aggregation and three bounded search selections plus
one batched image query. Search does not load card variants/keywords. Query growth
tests cover random, both metadata routes, keyword listing, and search. A separate
single-card random test verifies 13 variants with images and 13 keywords stay within
a small query bound. These are query-count checks, not large-scale latency benchmarks.

## 14. Security tests

Hostile-looking search text (`' OR 1=1 --`, `%_`, `'; DROP TABLE cards; --`) behaved as
literal input. A positive literal `%_` fixture matched only the card containing that
text. No user text is interpolated into SQL or accepted as an arbitrary column name.
All five routes are GET-only. Public schemas exclude internal UUID/foreign-key,
provenance, and hosted_by_us fields. Only fictional records and example.invalid image
URLs were used; no artwork was downloaded and no credentials were printed.

## 15. OpenAPI verification

All five exact paths, tags, GET-only operations, and response schemas were checked.
SearchResponse and its three union members, RarityCatalogItem, and KeywordCatalogItem
are now referenced in OpenAPI. The enum includes additive KEYWORD_NOT_FOUND.
Endpoint-specific random-empty, keyword-missing, and invalid-search examples were
verified. Existing set/card 404 documentation and advanced card parameters still pass
regression tests. No misleading shared error example was introduced.

## 16. Swagger verification

Executed through the actual Try it out/Execute UI against PostgreSQL:

| Request | Result |
| --- | --- |
| GET /v1/cards/random | 200; detail with keyword, four variants/images, and separate direct image |
| GET /v1/rarities | 200; Rare count 2 |
| GET /v1/keywords | 200; test-keyword count 24, plus zero-card keywords |
| GET /v1/keywords/test-keyword/cards | 200; CardSummary items with direct images |
| GET /v1/search?q=test | 200; bounded discriminated search response |

## 17. PostgreSQL verification

Local development database naruto_mythos, PostgreSQL 18.6. Alembic current remained
5f360cfd2561 (head); no migration was needed. Uvicorn used normal application settings
with no dependency overrides. The final verification pass executed 58 live HTTP
requests, including all five routes, health/readiness, metadata counts, keyword case
matching, zero/missing keywords, all ten keyword sort/direction combinations,
pagination, search fields/ranking/limits, invalid inputs, literal hostile text,
route conflict behavior, and OpenAPI. Representative SQL was instrumented separately.

## 18. Temporary-data cleanup

Exact ORM-created primary keys were recorded during flush. Initial collision checks
preceded insertion, and growth/ranking fixtures were included in the same manifest.
Removed exactly 112 images, 89 variants, 30 cards, 25 keywords, and 25 sets. Every
recorded ID was queried afterward and verified absent, as were associated card-keyword
links. No unrelated development records were targeted. The temporary cleanup manifest
was deleted and the verification server stopped. No tables or migrations were altered.

## 19. Tests added

72 new collected cases cover random empty/one/many/full-detail/route safety;
metadata counts/zero-card keywords/case distinctions/ordering/slug collisions;
keyword listing/case-insensitive union/pagination/all sorts/errors;
search validation/all fields/ranking/type and identifier ties/limits/duplicates/
image separation/literal input; five query-growth scenarios; a heavily related random
card; and explicit OpenAPI assertions. All 221 prior cases remain.

## 20. Full test results

Final command: python -m pytest -v

**293 passed, 2 warnings in 13.45s.** Baseline 221 + 72 new cases.

The two warnings remain existing Starlette HTTP client and AnyIO BlockingPortal
deprecations. Focused Ruff E4/E7/E9/F checks passed for the changed/new implementation
and discovery tests. Relevant files were formatted.

## 21. Bugs discovered/fixed

No PostgreSQL-specific implementation defect or blocking schema issue was discovered.
A new Unicode slug-test file was initially written using Windows encoding; it was
corrected to UTF-8 before successful runs. An unused test variable was removed.
The first live ranking expectation overlooked pre-existing fixture fields containing
Needle; the API correctly returned those substring matches. The expectation was
corrected and all nine ranked results were verified without changing API behavior.

## 22. Deviations from specification

No functional scope deviations. The unspecified search lower limit is 1, and invalid
search-limit bounds use the existing INVALID_PAGINATION code. Slug-only punctuation
produces an empty display slug; colliding names remain separate. Case-insensitive
keyword lookup uses the same unique-union semantics as the existing filter.
These edge behaviors are documented and tested.

No importer, real data, authentication, RapidAPI, Docker/Railway deployment, caching,
or public write endpoints were implemented. Phase 8 remains unstarted.

## 23. Final project tree

Private .env, installed dependencies, caches, and package metadata are excluded.

```text
.env.example
.gitignore
PHASE_1_REPORT.md
PHASE_2_REPORT.md
PHASE_3_REPORT.md
PHASE_4_REPORT.md
PHASE_5_REPORT.md
PHASE_6_REPORT.md
PHASE_7_REPORT.md
README.md
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
data/README.md
importer/.gitkeep
migrations/env.py
migrations/script.py.mako
migrations/versions/5f360cfd2561_initial_schema.py
phase5_verification_results.json
phase6_verification_results.json
phase7_verification_results.json
pyproject.toml
tests/__init__.py
tests/conftest.py
tests/test_card_filters.py
tests/test_cards_routes.py
tests/test_discovery.py
tests/test_health.py
tests/test_models.py
tests/test_openapi.py
tests/test_ready.py
tests/test_schemas.py
tests/test_sets_routes.py
```

## Fictional example responses

The following are captured live responses from temporary data since removed.

### GET /v1/cards/random

```json
{
  "id": "test-p7-card-18",
  "number": "18",
  "name": "Test Growth Card 18",
  "subtitle": null,
  "type": null,
  "rarity": null,
  "chakra": null,
  "power": null,
  "faction": null,
  "ability_text": null,
  "flavor_text": null,
  "artist": null,
  "set": {
    "id": "test-p7-set-18",
    "code": null,
    "name": "Test Growth Set 18",
    "edition": null
  },
  "keywords": [
    {
      "slug": "test-keyword",
      "name": "Test Keyword Needle"
    }
  ],
  "variants": [
    {
      "id": "test-p7-variant-18-0",
      "type": "test",
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
    },
    {
      "id": "test-p7-variant-18-1",
      "type": "test",
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
    },
    {
      "id": "test-p7-variant-18-2",
      "type": "test",
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
    },
    {
      "id": "test-p7-variant-18-3",
      "type": "test",
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
      "url": "https://example.invalid/direct.png",
      "width": null,
      "height": null
    }
  ]
}
```

### GET /v1/rarities

```json
[
  {
    "name": "Rare",
    "slug": "rare",
    "card_count": 2
  }
]
```

### GET /v1/keywords

```json
[
  {
    "slug": "test-keyword",
    "name": "Test Keyword Needle",
    "card_count": 24
  },
  {
    "slug": "test-p7-keyword-0",
    "name": "Test Growth Keyword 00",
    "card_count": 0
  },
  {
    "slug": "test-p7-keyword-1",
    "name": "Test Growth Keyword 01",
    "card_count": 0
  },
  {
    "slug": "test-p7-keyword-2",
    "name": "Test Growth Keyword 02",
    "card_count": 0
  },
  {
    "slug": "test-p7-keyword-3",
    "name": "Test Growth Keyword 03",
    "card_count": 0
  },
  {
    "slug": "test-p7-keyword-4",
    "name": "Test Growth Keyword 04",
    "card_count": 0
  },
  {
    "slug": "test-p7-keyword-5",
    "name": "Test Growth Keyword 05",
    "card_count": 0
  },
  {
    "slug": "test-p7-keyword-6",
    "name": "Test Growth Keyword 06",
    "card_count": 0
  },
  {
    "slug": "test-p7-keyword-7",
    "name": "Test Growth Keyword 07",
    "card_count": 0
  },
  {
    "slug": "test-p7-keyword-8",
    "name": "Test Growth Keyword 08",
    "card_count": 0
  },
  {
    "slug": "test-p7-keyword-9",
    "name": "Test Growth Keyword 09",
    "card_count": 0
  },
  {
    "slug": "test-p7-keyword-10",
    "name": "Test Growth Keyword 10",
    "card_count": 0
  },
  {
    "slug": "test-p7-keyword-11",
    "name": "Test Growth Keyword 11",
    "card_count": 0
  },
  {
    "slug": "test-p7-keyword-12",
    "name": "Test Growth Keyword 12",
    "card_count": 0
  },
  {
    "slug": "test-p7-keyword-13",
    "name": "Test Growth Keyword 13",
    "card_count": 0
  },
  {
    "slug": "test-p7-keyword-14",
    "name": "Test Growth Keyword 14",
    "card_count": 0
  },
  {
    "slug": "test-p7-keyword-15",
    "name": "Test Growth Keyword 15",
    "card_count": 0
  },
  {
    "slug": "test-p7-keyword-16",
    "name": "Test Growth Keyword 16",
    "card_count": 0
  },
  {
    "slug": "test-p7-keyword-17",
    "name": "Test Growth Keyword 17",
    "card_count": 0
  },
  {
    "slug": "test-p7-keyword-18",
    "name": "Test Growth Keyword 18",
    "card_count": 0
  },
  {
    "slug": "test-p7-keyword-19",
    "name": "Test Growth Keyword 19",
    "card_count": 0
  },
  {
    "slug": "test-p7-keyword-20",
    "name": "Test Growth Keyword 20",
    "card_count": 0
  },
  {
    "slug": "test-p7-keyword-21",
    "name": "Test Growth Keyword 21",
    "card_count": 0
  },
  {
    "slug": "test-unused",
    "name": "Test Unused",
    "card_count": 0
  },
  {
    "slug": "need",
    "name": "ZZ Test Keyword",
    "card_count": 0
  }
]
```

### GET /v1/keywords/test-keyword/cards?limit=1

```json
{
  "data": [
    {
      "id": "test-p7-card-00",
      "number": "0",
      "name": "Test Growth Card 00",
      "subtitle": null,
      "type": null,
      "rarity": null,
      "set": {
        "id": "test-p7-set-00",
        "code": null,
        "name": "Test Growth Set 00",
        "edition": null
      },
      "images": [
        {
          "type": "front",
          "url": "https://example.invalid/direct.png",
          "width": null,
          "height": null
        }
      ]
    }
  ],
  "pagination": {
    "page": 1,
    "limit": 1,
    "total": 24,
    "pages": 24,
    "has_next": true,
    "has_previous": false
  }
}
```

### GET /v1/search?q=test&limit=3

```json
{
  "data": [
    {
      "type": "card",
      "card": {
        "id": "TEST-001",
        "number": "C701",
        "name": "Test Character Alpha",
        "subtitle": "SubtitleNeedle",
        "type": null,
        "rarity": "Rare",
        "set": {
          "id": "test-set-alpha",
          "code": "SETCODE7",
          "name": "Test Set Alpha",
          "edition": "Test Edition"
        },
        "images": [
          {
            "type": "front",
            "url": "https://example.invalid/direct.png",
            "width": null,
            "height": null
          }
        ]
      }
    },
    {
      "type": "card",
      "card": {
        "id": "TEST-002",
        "number": "10",
        "name": "Test Character Beta",
        "subtitle": null,
        "type": null,
        "rarity": "Rare",
        "set": {
          "id": "test-set-alpha",
          "code": "SETCODE7",
          "name": "Test Set Alpha",
          "edition": "Test Edition"
        },
        "images": []
      }
    },
    {
      "type": "card",
      "card": {
        "id": "TEST-A03",
        "number": "2",
        "name": "Test Character Gamma",
        "subtitle": null,
        "type": null,
        "rarity": null,
        "set": {
          "id": "test-set-beta",
          "code": "BETA7",
          "name": "Test Set Beta",
          "edition": null
        },
        "images": []
      }
    }
  ]
}
```

