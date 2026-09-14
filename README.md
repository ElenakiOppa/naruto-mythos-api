# Naruto Mythos TCG Developer API

A developer-friendly REST API for querying Naruto Mythos TCG catalogue data
(cards, sets, rarities, keywords). Built as a standalone, versioned public
API intended for third-party consumers (websites, apps, collection
trackers, deck builders, Discord bots) and eventual publication on
RapidAPI.

> **Status:** Phases 1–9, including the approved Phase 9A ownership correction, are complete. Catalogue/discovery reads and the approved local importer are implemented. No deployment or RapidAPI integration exists yet. See [Phase 9 audit](PHASE_9_REPORT.md).

## Architecture

```
Origin API  →  (later) RapidAPI proxy/gateway  →  API consumer
```

- **FastAPI** application, versioned catalogue endpoints under `/v1`
- **PostgreSQL** via **SQLAlchemy 2.x** + **Alembic** migrations
- **Pydantic v2** request/response schemas
- A separate **importer** package for loading normalized, authorized JSON
  catalogue data (no scraping, no invented data)
- Reads are public in v1; there are no public write endpoints — all data
  mutation happens through the CLI importer

```
app/
  main.py         FastAPI app, CORS, router mounting
  config.py       Environment-driven settings (validated at startup)
  database.py     SQLAlchemy engine/session
  models/         SQLAlchemy ORM models: sets, cards, card_variants,
                   keywords, card_images, source_records (Phase 2)
  schemas/        Pydantic public API schemas (Phase 3): base.py (shared
                   config), set.py, card.py, variant.py, image.py,
                   keyword.py, pagination.py, error.py, metadata.py,
                   search.py -- see PHASE_3_REPORT.md for the full
                   public JSON contract these define
  api/v1/         Versioned route handlers -- health.py and ready.py are
                   mounted unversioned; sets.py implements the public
                   Sets API under /v1/sets (Phase 4)
  services/       Business/query logic -- set_service.py holds all
                   SQLAlchemy query construction for the Sets API, kept
                   out of the route handlers themselves
  utils/          Shared helpers: pagination.py (page/limit validation +
                   PaginationMeta calculation), errors.py (APIError, the
                   single reusable path to the public ErrorResponse shape)
importer/         Standalone catalogue data importer (Phase 8)
data/             Normalized JSON inputs for the importer (git-ignored)
migrations/       Alembic environment + versioned migration scripts
tests/            Pytest suite (conftest.py provides an isolated
                   in-memory SQLite fixture for model tests)
```

`GET /health` and `GET /ready` are deliberately different:

- **`/health`** -- pure liveness. No database access. Always responds
  immediately. Use this for process-level liveness checks.
- **`/ready`** -- infrastructure readiness. Checks PostgreSQL connectivity.
  Returns `200 {"status": "ready"}` when the database is reachable, or
  `503 {"status": "not_ready"}` when it isn't. Never exposes connection
  details, credentials, or raw exception text.

## Local Installation

Requires Python 3.12+ and PostgreSQL.

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
```

## Environment Configuration

Copy the example file and fill in real values:

```bash
cp .env.example .env
```

| Variable       | Description                                              |
|----------------|-----------------------------------------------------------|
| `APP_ENV`      | `development` \| `test` \| `production`                   |
| `DATABASE_URL` | PostgreSQL connection string (`postgresql+psycopg://...`) |
| `CORS_ORIGINS` | Comma-separated allowed browser origins (empty = none)    |
| `DOCS_ENABLED` | Expose /docs, /redoc, /openapi.json (default true) |
| `LOG_LEVEL`    | `DEBUG` \| `INFO` \| `WARNING` \| `ERROR`                  |
| `PORT`         | Port suggestion; pass explicitly to the server command                  |

Configuration is validated at startup — the app will fail fast if
`DATABASE_URL` is missing.

## Database Setup

You need a running PostgreSQL instance. Two common options:

**A. Local PostgreSQL install** — create a database and point `DATABASE_URL`
in `.env` at it, e.g.:

```
DATABASE_URL=postgresql+psycopg://postgres:postgres@localhost:5432/naruto_mythos
```

**B. Docker** (if you have Docker installed — `docker-compose.yml` for this
project itself is added in Phase 10, but you can still run a bare Postgres
container now):

```bash
docker run --name naruto-mythos-postgres -e POSTGRES_PASSWORD=postgres \
  -e POSTGRES_DB=naruto_mythos -p 5432:5432 -d postgres:16
```

## Alembic Migrations

Alembic reads `DATABASE_URL` from the same `Settings` object the app uses
(see `migrations/env.py`) — there is no separate, hard-coded connection
string to keep in sync.

Apply all migrations:

```bash
alembic upgrade head
```

Roll back everything (useful for verifying the migration is fully
reversible):

```bash
alembic downgrade base
```

Then re-apply:

```bash
alembic upgrade head
```

Generate a new migration in later phases (after changing models):

```bash
alembic revision --autogenerate -m "describe the change"
```

Always review autogenerated migrations by hand before applying them —
autogenerate does not reliably detect every kind of change (e.g. some
constraint renames), and this project's own initial migration was
hand-written and reviewed rather than trusted blindly.

## Starting the Development Server

```bash
uvicorn app.main:app --reload
```

Then visit:

- `http://localhost:8000/health`
- `http://localhost:8000/docs` (Swagger UI)
- `http://localhost:8000/openapi.json`

## Running Tests

```bash
pytest
```

## Docker Usage

Production containerization is configured for Python 3.12 and a non-root runtime user.

```bash
# build the production image
 docker build -t naruto-mythos-api:prod .

# run locally with a PostgreSQL URL present in the environment
 docker run --rm -p 8000:8000 \
   -e APP_ENV=production \
   -e DATABASE_URL='postgresql+psycopg://postgres:postgres@host.docker.internal:5432/naruto_mythos' \
   -e CORS_ORIGINS='http://localhost:3000' \
   -e DOCS_ENABLED=true \
   -e LOG_LEVEL=INFO \
   -e PORT=8000 \
   naruto-mythos-api:prod
```

The container starts Uvicorn without reload and fails fast if `DATABASE_URL` is missing. Health checks should use `/ready` for database readiness and `/health` for process liveness.

### Production dependency locking

Runtime dependencies are locked in a reviewed deployment set:

- `requirements.production.in` lists the deliberate runtime requirements.
- `production-baseline.constraints` pins the verified baseline for the production build.
- `requirements.production.txt` is the committed lockfile used by the container build.

Update the lock intentionally by editing the source requirements and regenerating the compiled file with a reviewed pip-tools workflow. Do not broadly change the already-verified stack without review.

## Railway Deployment

A `railway.toml` file is included for the app service and uses a Docker build, a single Uvicorn worker, and a pre-deploy Alembic migration command.

Required environment variables:

| Variable | Required | Notes |
| --- | --- | --- |
| `DATABASE_URL` | Yes | Railway PostgreSQL connection string; never committed to source control |
| `APP_ENV` | Yes | Set to `production` |
| `LOG_LEVEL` | Recommended | Usually `INFO` |
| `DOCS_ENABLED` | Yes | Defaults to `true` for controlled verification |
| `CORS_ORIGINS` | Recommended | Only explicit browser origins; no credentialed wildcard |
| `PORT` | Supplied by Railway | Bound by the start command |

Example application start command:

```bash
exec uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000} --proxy-headers
```

Migrations are not run on every worker. Instead, the deployment executes:

```bash
alembic upgrade head
```

before the service is considered ready. The app still keeps `/health` and `/ready` separate:

- `/health` = process liveness
- `/ready` = PostgreSQL readines

`/ready` is the preferred Railway health-check target because it verifies the database connection before traffic is considered safe.

## Importer Usage

Use an approved local normalized JSON file. Review a dry run before importing:

```bash
python -m importer.cli data/examples/fictional-catalogue.json --dry-run
python -m importer.cli data/examples/fictional-catalogue.json
```

## API Endpoints

Currently implemented:

| Method | Path                        | Description                                        |
|--------|-----------------------------|-----------------------------------------------------|
| GET    | `/health`                   | Liveness check — no database access                 |
| GET    | `/ready`                    | Readiness check — verifies PostgreSQL connectivity   |
| GET    | `/v1/sets`                  | Paginated list of sets, with filtering and sorting   |
| GET    | `/v1/sets/{id}`             | Look up one set by its public ID                     |
| GET    | `/v1/sets/{id}/cards`       | Paginated list of one set's cards                    |

Also implemented: `GET /v1/cards`, `GET /v1/cards/{public_id}`,
`GET /v1/cards/random`, `GET /v1/rarities`, `GET /v1/keywords`,
`GET /v1/keywords/{slug}/cards`, `GET /v1/search`.

## Filtering Examples

All examples use fictional data (`test-set-1`, `TEST-001`, ...) — nothing
here resembles real Naruto Mythos catalogue content.

**List sets:**
```bash
curl http://localhost:8000/v1/sets
```

**Paginate:**
```bash
curl "http://localhost:8000/v1/sets?page=2&limit=25"
```

**Filter by language, edition, or code** (case-insensitive):
```bash
curl "http://localhost:8000/v1/sets?language=EN"
curl "http://localhost:8000/v1/sets?edition=1st%20Edition"
curl "http://localhost:8000/v1/sets?code=TST1"
```

**Sort sets** — allowed fields: `name`, `release_date`, `code`; allowed
order: `asc`, `desc`. Default is `sort=release_date&order=desc`. Sets with
a null `release_date` always sort last, regardless of direction.
```bash
curl "http://localhost:8000/v1/sets?sort=name&order=asc"
```

**Get one set by its public ID:**
```bash
curl http://localhost:8000/v1/sets/test-set-1
```

**List a set's cards:**
```bash
curl http://localhost:8000/v1/sets/test-set-1/cards
```

**Sort a set's cards** — allowed fields: `number`, `name`, `rarity`;
allowed order: `asc`, `desc`. Default is `sort=number&order=asc`.
`number` sorts **lexically** (as a string), not numerically — a card
numbered `"10"` sorts before `"2"`. Cards with a null `rarity` sort last.
```bash
curl "http://localhost:8000/v1/sets/test-set-1/cards?sort=rarity&order=asc"
```

## Pagination

```json
{
  "data": [],
  "pagination": {
    "page": 1,
    "limit": 50,
    "total": 630,
    "pages": 13,
    "has_next": true,
    "has_previous": false
  }
}
```

`page` defaults to `1`, `limit` defaults to `50` and cannot exceed `100`.
Requesting a page beyond the last one returns an empty `data` array with
accurate `pagination` metadata (not a 404). Invalid values (`page=0`,
`limit=101`, ...) return `400` with `INVALID_PAGINATION`.

## Error Format

```json
{
  "error": {
    "code": "SET_NOT_FOUND",
    "message": "Set not found."
  }
}
```

Every route in this API returns this exact shape for errors — never a
stack trace, SQL text, or internal identifier. Codes currently in active
use: `SET_NOT_FOUND` (404), `INVALID_SORT` (400), `INVALID_PAGINATION`
(400), `INTERNAL_ERROR` (500, generic fallback for unexpected failures).
`CARD_NOT_FOUND` and `INVALID_FILTER` are defined in the schema layer for
endpoints implemented in later phases.

## OpenAPI Docs

Available at `/docs` (Swagger UI) and `/openapi.json` once the server is
running.

## Railway Deployment Notes

Deployment is not implemented. A future server start command must pass the desired port explicitly; the application Settings value alone does not configure Uvicorn.

## RapidAPI Developer Notes

This project is a developer-facing public API for Naruto Mythos TCG catalogue data. The origin API is intended to be consumed by external tools, websites, and app integrations, and it may later be exposed through a RapidAPI listing. The project does not claim to be an official Naruto API and does not claim any current live RapidAPI listing or commercial publication.

### API purpose

- Public origin API for catalogue discovery and lookup
- Versioned under `/v1`
- `API version 1.0.0`
- Read-only public resources: sets, cards, keywords, metadata, search
- No real importer or live catalogue ingestion is currently active in production
- Production database remains intentionally empty until authorized ingestion work begins

### Origin URL and versioning

The production origin is intended to be served from Railway at:

```text
https://naruto-mythos-api-production.up.railway.app
```

The current public versioning policy is:

- `/v1` for the stable public API
- API version metadata: `1.0.0`
- no write endpoints for public clients

### Public contract at a glance

- `GET /health` — liveness only
- `GET /ready` — infrastructure readiness
- `GET /v1/sets` — list sets
- `GET /v1/sets/{public_id}` — set detail
- `GET /v1/sets/{public_id}/cards` — cards in a set
- `GET /v1/cards` — paginated card queries with filtering
- `GET /v1/cards/random` — random card result if present in the route set
- `GET /v1/cards/{public_id}` — card detail
- `GET /v1/rarities` — distinct rarity values
- `GET /v1/keywords` — list keywords
- `GET /v1/keywords/{slug}/cards` — keyword-based lookup
- `GET /v1/search` — search queries

### Pagination, filtering, sorting, and search

The public API uses a consistent pagination wrapper:

- `page` defaults to `1`
- `limit` defaults to `50`
- `limit` must stay within the allowed range
- invalid values return the standardized 400 error contract
- empty result sets still return a `200` with an empty `data` array and accurate pagination metadata

Filters, sorting, and search are request-driven and documented in the canonical FastAPI OpenAPI at runtime. The API is designed to be read-only and request-safe; no write or admin routes are exposed in the public API surface.

### Standardized errors

Every public route uses the shared error contract:

```json
{
  "error": {
    "code": "SET_NOT_FOUND",
    "message": "Set not found."
  }
}
```

Actual error codes in the public contract include `SET_NOT_FOUND`, `CARD_NOT_FOUND`, `KEYWORD_NOT_FOUND`, `INVALID_FILTER`, `INVALID_PAGINATION`, `INVALID_SORT`, `FORBIDDEN`, and `INTERNAL_ERROR`.

### OpenAPI and docs

The canonical application generates OpenAPI 3.1.0 JSON for local use at `/openapi.json`. Swagger UI is available at `/docs`, and Redoc is available at `/redoc` when docs are enabled. A generated RapidAPI compatibility export is produced in the repository and remains derived from the canonical FastAPI schema rather than being maintained by hand.

### RapidAPI authentication model

RapidAPI handles consumer-side authentication, which means the consumer requests are expected to carry:

- `X-RapidAPI-Key`
- `X-RapidAPI-Host`

Those headers are not validated by the origin API itself; they are validated by the RapidAPI gateway. The origin service is only responsible for protecting itself from direct traffic when configured.

The origin-facing protection is optional and implemented as:

- `X-RapidAPI-Proxy-Secret` header check
- only enforced on `/v1` routes when `RAPIDAPI_PROXY_SECRET` is set
- no protection for `/health` or `/ready`
- no protection when the secret is unset

This is intended to be used only when the live RapidAPI runtime is configured and the RapidAPI gateway is forwarding requests to the origin. It is not enabled in production by default.

### Rate limiting and CORS

Rate limiting and quotas are intended to be gateway-owned. The origin API does not claim to currently enforce a specific plan or quota model itself. CORS is configuration-driven and intentionally limited to explicit origins when configured; no wildcard credentialed browser policy is enabled by default.

### Production state and deployment notes

This repository is not claiming a live API publication. The production database remains intentionally empty, no importer has been authorized to load real Naruto card data, and no live RapidAPI listing has been established from this codebase alone.

### RapidAPI setup steps for later manual approval

The following are the manual setup steps after code-ready approval:

1. Sign into RapidAPI and create the provider API entry.
2. Keep the listing private until the origin is validated.
3. Import the generated OpenAPI 3.0.2 document.
4. Configure the origin URL to `https://naruto-mythos-api-production.up.railway.app`.
5. Configure and test the RapidAPI runtime.
6. Obtain the provider-side `X-RapidAPI-Proxy-Secret` value.
7. Add it to Railway as `RAPIDAPI_PROXY_SECRET`.
8. Redeploy the service.
9. Confirm direct `/v1` access without the secret returns `403`.
10. Confirm proxied RapidAPI access succeeds.
11. Configure plans, quotas, and rate limits.
12. Test representative endpoints.
13. Review analytics and monitor traffic.
14. Only then consider publication.

## Data Licensing Notice

This project provides technical infrastructure for a Naruto Mythos TCG
catalogue API. Card data, artwork, logos, trademarks, game text and other
intellectual property may be owned by their respective rights holders.

This project does not claim affiliation with Naruto, Cicaboom, Shueisha,
TV Tokyo, Studio Pierrot, or any other rights holder. No copyrighted
artwork or logos are included in this repository, and no proprietary card
text is populated except as supplied via approved, authorized project
data.


## Phase 5: Public Cards API

`GET /v1/cards` returns `PaginatedCardsResponse`: lightweight `CardSummary`
items with public ID, number, name, subtitle, type, rarity, nested set, and
card-level images. `GET /v1/cards/{public_id}` returns `CardDetail`, adding
chakra, power, faction, ability/flavor text, artist, keywords, and variants
with their own images. Nullable fields remain explicit JSON nulls.

The three basic SQL filters are:

| Parameter | Behavior |
| --- | --- |
| `name` | Case-insensitive literal substring (percent/underscore are literal text) |
| `set` | Case-insensitive exact public set ID |
| `number` | Exact string card number |

Filters combine with AND. Sorting supports `number`, `name`, `rarity`,
`set` (set name), and `release_date` (set release date); `order` is `asc` or
`desc`. Defaults: `sort=number&order=asc`. Numbers sort lexically (`1`, `10`,
`2`), nulls always last, and card public ID ascending breaks ties.

Pagination defaults to `page=1&limit=50`; page must be at least 1 and limit
1 through 100. Empty results and pages beyond the end return 200 with empty
data and accurate metadata. Invalid pagination/sorting returns the shared
400 error format; malformed types return 422. Unknown card public IDs return
404 `CARD_NOT_FOUND`. Internal UUIDs are not lookup IDs.

Top-level images in the new Cards API include only images without a variant;
variant-specific images appear under that variant. Existing set-card endpoint
behavior is preserved. Source metadata and internal IDs are never public.

Fictional examples (records must exist in the development database):

```sh
curl "http://127.0.0.1:8000/v1/cards?name=test&set=test-set-alpha"
curl "http://127.0.0.1:8000/v1/cards?number=001&sort=release_date&order=desc&page=1&limit=10"
curl "http://127.0.0.1:8000/v1/cards/TEST-001"
```

Both endpoints appear under **Cards** in Swagger. Error examples are specific
to the operation: set 404s show `SET_NOT_FOUND`, card 404s show `CARD_NOT_FOUND`.
Future static card routes must be registered before `/{public_id}`; no random
route or advanced filtering is implemented in Phase 5.


## Phase 6: Advanced Card Filtering

`GET /v1/cards` also supports these filters. All supplied filters combine with
**AND**, including the existing `name`, `set`, and `number` filters.

| Parameter | Meaning |
| --- | --- |
| `rarity` | Case-insensitive exact card rarity; values come from the database |
| `type` | Case-insensitive exact card type |
| `keyword` | Case-insensitive exact keyword slug; card must have a matching keyword |
| `variant` | Case-insensitive exact variant type; card must have a matching variant |
| `language` | Case-insensitive exact **parent set language**, not variant language |
| `edition` | Case-insensitive exact **parent set edition**, not variant edition |
| `chakra_min`, `chakra_max` | Inclusive minimum/maximum chakra |
| `power_min`, `power_max` | Inclusive minimum/maximum power |

Unknown text values return an empty collection, not an error. Exact filters
treat `%` and `_` literally; `name` continues to escape LIKE metacharacters.
NULL editions do not match a supplied edition. Cards with NULL chakra/power do
not match a supplied range for that statistic; nulls are never treated as zero.

All four range bounds must be nonnegative. A minimum above its maximum or a
negative bound returns HTTP 400 `INVALID_FILTER`. Malformed integer types remain
HTTP 422. Bounds are inclusive, so equal minimum and maximum select that value.

Keyword and variant predicates use correlated SQL EXISTS. Multiple matching
keywords/variants do not duplicate cards or inflate totals. CardSummary still
excludes keywords and variants. Filters are applied before counting/pagination;
all five existing sort fields, stable public-ID ties, and NULLS LAST remain.

Fictional examples:

```sh
curl "http://127.0.0.1:8000/v1/cards?rarity=Rare"
curl "http://127.0.0.1:8000/v1/cards?variant=holographic"
curl "http://127.0.0.1:8000/v1/cards?keyword=test-keyword"
curl "http://127.0.0.1:8000/v1/cards?chakra_min=2&chakra_max=5"
curl "http://127.0.0.1:8000/v1/cards?set=test-set-alpha&rarity=Rare&variant=holographic"
```

Swagger documents all 17 query parameters and separate 400 examples for invalid
chakra ranges, power ranges, negative statistics, pagination, and sorting.


## Phase 7: Discovery, metadata, search, and random card

All new endpoints are read-only and use the existing public schemas.

| Endpoint | Response and behavior |
| --- | --- |
| `GET /v1/cards/random` | One `CardDetail`; empty catalogue returns 404 `CARD_NOT_FOUND` / `No cards available.` |
| `GET /v1/rarities` | `RarityCatalogItem` array with stored rarity name, derived slug, and canonical-card count |
| `GET /v1/keywords` | `KeywordCatalogItem` array, including keywords with zero cards |
| `GET /v1/keywords/{slug}/cards` | `PaginatedCardsResponse` using the existing five sort fields and CardSummary |
| `GET /v1/search?q=...` | Bounded `SearchResponse` combining card, set, and keyword results |

Random selection uses SQL `ORDER BY random()` for the expected initial catalogue
size; the service can be optimized later for much larger catalogues. Its static
route precedes `/{public_id}`. CardDetail uses the existing batched loading and
keeps variant images separate from direct card images.

Rarity counts group by the exact stored non-null rarity name. Ordering is count
descending, then name ascending. Slugs lowercase/trim text, collapse punctuation
and whitespace to hyphens, and retain Unicode letters/digits. Case-distinct names
and slug collisions remain separate entries; slugs are presentation metadata,
not identity. Punctuation-only names produce empty slugs and remain separate.

Keyword counts use SQL COUNT(DISTINCT card_id), ordered by count descending,
name ascending, then slug ascending. The keyword-card path matches slug
case-insensitively, consistent with the existing keyword filter. If multiple
case-distinct stored slugs match, their cards are returned as a unique union.
An unknown slug returns 404 `KEYWORD_NOT_FOUND`; a zero-card keyword returns 200
with empty data. Pagination defaults to page 1, limit 50 (maximum 100), and
sorting defaults to lexical number ascending, with all Phase 5 sort fields.

Search requires `q`; whitespace is trimmed and at least two characters must
remain. Missing q returns 422; shorter provided queries return 400 INVALID_FILTER.
Search matches case-insensitive literal substrings in card name/public ID/number/
subtitle, set name/public ID/code, and keyword name/slug. Percent/underscore are
literal characters, not wildcards. Search results contain compact public schemas.

Ranking: exact public ID/slug, exact name, name prefix, then other substring.
Equal-quality results prefer card, then set, then keyword. Within a type, SQL
alphabetical name order and public identifier break ties, using database collation.
Each entity appears once even if several fields match. Three SQL queries each
fetch at most `limit` candidates; card images are fetched in one batched query.
The bounded candidates are merged and truncated to a **final combined** limit:
default 20, maximum 50, minimum 1. Invalid bounds return 400 INVALID_PAGINATION;
malformed types return 422. Search has no pagination metadata or fuzzy matching.

Fictional examples:

```sh
curl "http://127.0.0.1:8000/v1/cards/random"
curl "http://127.0.0.1:8000/v1/rarities"
curl "http://127.0.0.1:8000/v1/keywords"
curl "http://127.0.0.1:8000/v1/keywords/test-keyword/cards?page=1&limit=10&sort=name"
curl "http://127.0.0.1:8000/v1/search?q=test&limit=20"
```

Swagger tags are Cards, Metadata, and Search. Error examples are specific to each
operation. No importer or public write functionality is included.


## Phase 8: approved local catalogue imports

The importer accepts approved/local normalized JSON. It does not automatically scrape Naruto Mythos or download artwork. See [importer usage and policies](importer/README.md), [fictional example](data/examples/fictional-catalogue.json), and [Phase 8 report](PHASE_8_REPORT.md).

```powershell
python -m importer.cli data/examples/fictional-catalogue.json --dry-run --report dry-run.json
python -m importer.cli data/examples/fictional-catalogue.json --report import-report.json
```

Actual imports are transactional and idempotent. Omitted entities are retained; explicit keyword lists replace associations. Independent source provenance uses semantic SHA-256 hashes. Image URLs are stored only as metadata. Review the complete scalar-snapshot and multi-source precedence policies before importing.


## Phase 9A: variant image ownership

Migration `8b41e2a9c730` enforces that an image and its referenced variant belong to the same card. Apply it with `python -m alembic upgrade head`. It checks legacy mismatches and fails without repairing them; resolve any diagnostic explicitly before retrying. PostgreSQL deletes a variant by clearing only the image's variant reference, preserving the image and owning card. Card deletion still cascades to its images.

The migration locks the affected tables during preflight and DDL; plan a maintenance window for a busy or large database. SQLite unit tests use a simple FK fallback and do not certify PostgreSQL ownership enforcement.

Run `python -m scripts.verify_phase9a` for the isolated PostgreSQL migration/ownership checks. See [Phase 9A report](PHASE_9A_REPORT.md) for the correction results. The subsequent [Phase 9 audit](PHASE_9_REPORT.md) completed the remaining review and Ruff cleanup.


## Production readiness after Phase 9

PostgreSQL is required for runtime; verification used PostgreSQL 18.6. SQLite is only a portable unit-test backend and cannot certify the column-specific ownership FK. Current Alembic head is `8b41e2a9c730`. Before running the service, configure DATABASE_URL and run `python -m alembic upgrade head`, then `python -m alembic check`. Migration 9A locks image/variant tables and rejects mismatched legacy ownership; schedule it appropriately.

Set `APP_ENV` explicitly for the environment; it labels the environment rather than silently enabling security controls. Debug responses are always disabled. Choose `DOCS_ENABLED` explicitly (default true); false disables all three documentation routes. Set `LOG_LEVEL` appropriately, normally INFO. Keep `.env` out of version control and inject production credentials through the eventual hosting environment. `PORT` is fed by the host runtime and passed to Uvicorn via the deployment command. Phase 10 adds Docker and Railway deployment configuration for this flow.

Use only approved/local JSON with the importer. Start with `--dry-run`, inspect the plan, then import. Catalogue entities omitted from a file are retained; explicit keyword lists replace associations. Sources retain separate semantic hashes/observation times. The polymorphic provenance table has no FK: importer transactions keep normal imports coherent, but external deletion tools must explicitly maintain provenance. Cooperating importers serialize via a transaction advisory lock; arbitrary database writers do not automatically participate.

GET sessions close without committing. PostgreSQL READ COMMITTED readers do not see uncommitted importer changes. A response assembled from multiple queries can see different committed snapshots if an import commits between those queries; stricter cross-query snapshots would require a reviewed isolation choice. Do not treat a dry-run plan as a lock on future data.

CORS currently uses configured origins, GET methods, and credentials=false. An empty origin list emits no cross-origin permission headers. Decide explicit allowed browser origins before deployment; wildcard origins, if deliberately selected for a public API, must remain credential-free. CORS is a browser policy, not authentication or protection against direct clients. Gateway/proxy CORS behavior will need verification at publication.

OpenAPI remains 3.1 at `/openapi.json`, with Swagger `/docs` and ReDoc `/redoc` when enabled. A future 3.0.x export may need nullable `anyOf` conversion, `const` to enum conversion, exclusive-bound representation changes, schema-example handling, and discriminator/reference validation. Check the actual generated schemas and gateway importer then; no converter or speculative dependency was added now.

Sorting uses allowlisted fields, NULLS LAST, and a public-ID tie-breaker. Card numbers sort lexically; alphabetic ordering follows database collation and case-folding semantics, not locale-independent natural sorting. Search is bounded to 50 combined results and escapes LIKE wildcards. `ORDER BY random()` scans/sorts candidates and is appropriate only while measured catalogue size and traffic remain modest. The Phase 9 report records a 2,000-card baseline and potential indexes for later review, not an SLA.

Unexpected API failures return a generic 500. Logs retain exception type and frame locations without exception text, SQL bind values, or source lines. Review proxy/server access logging separately before deployment, especially query strings that clients might populate with tokens. Dependency versions are currently lower-bounded rather than locked; use a reproducible, reviewed dependency set during containerization. Existing Starlette test-client deprecation warnings are documented; no broad upgrade was made.

Run `python -m scripts.verify_phase9` only against a quiet development PostgreSQL database. It starts a temporary localhost HTTP server, imports 2,000 fictional cards, captures query plans and timings, and cleans only its exact recorded IDs in a finally block. It verifies the original catalogue/provenance snapshot and stops the server. Retain `PHASE_*_REPORT.md`, `phase*_verification_results.json`, and reviewed audit evidence. Local logs, coverage output, caches, databases, and the temporary hash inventory are ignored; do not commit real input data or secret-bearing traces.
