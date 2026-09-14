# Naruto Mythos TCG Developer API — Phase 4 Report

**Scope:** `GET /v1/sets`, `GET /v1/sets/{public_id}`,
`GET /v1/sets/{public_id}/cards` only (per the phased plan). No global
`/v1/cards`, `/v1/search`, `/v1/rarities`, or `/v1/keywords`.
**Status:** Code complete, carefully self-reviewed — **not yet executed**
(same sandbox network limitation as every previous phase). See the note at
the end of this report for exactly what to run.

---

## 1. Files Created

| File | Purpose |
|---|---|
| `app/utils/errors.py` | `APIError` — the one exception type routes/services raise for any business-rule error |
| `app/utils/pagination.py` | `validate_pagination()`, `build_pagination_meta()`, and the shared `DEFAULT_PAGE`/`DEFAULT_LIMIT`/`MAX_LIMIT` constants |
| `app/services/set_service.py` | All SQLAlchemy query logic: `list_sets()`, `get_set_by_public_id()`, `list_cards_for_set()` |
| `app/api/v1/sets.py` | The three route handlers |
| `tests/test_sets_routes.py` | 40 route-level tests (see §12–§13) |

## 2. Files Modified

| File | Change |
|---|---|
| `app/main.py` | Registered two exception handlers: `APIError` → the public `ErrorResponse` shape at the error's own status code; a catch-all `Exception` handler → `500 INTERNAL_ERROR`, logging the real exception server-side and never in the response |
| `app/api/router.py` | Mounted the new `sets_router` (it declares its own `/v1/sets` prefix) |
| `tests/conftest.py` | Added a `client` fixture: a `TestClient` wired to the same isolated in-memory SQLite database as `db_session`, via FastAPI's `dependency_overrides` on `get_db` — see §9 for why |
| `README.md` | Documented the three new routes, curl examples, pagination/filtering/sorting behavior, and the error contract |

**Not modified:** any database model, the Alembic migration, `/health`, `/ready`, any Phase 1–3 schema or test file.

---

## 3. Routes Implemented

### `GET /v1/sets`
Paginated, filterable, sortable list of sets. `response_model=PaginatedSetsResponse`.

### `GET /v1/sets/{public_id}`
Single set lookup by public ID. `response_model=SetDetail`.

### `GET /v1/sets/{public_id}/cards`
Paginated, sortable list of one set's cards. `response_model=PaginatedCardsResponse` (using `CardSummary` per item).

All three are tagged `"Sets"` and appear under that section in `/docs`.

---

## 4. Query Parameters

| Route | Parameter | Type | Default | Notes |
|---|---|---|---|---|
| `GET /v1/sets` | `page` | int | `1` | Must be `>= 1` |
| | `limit` | int | `50` | Must be `1..100` |
| | `language` | str? | — | Case-insensitive equality |
| | `edition` | str? | — | Case-insensitive equality |
| | `code` | str? | — | Case-insensitive equality |
| | `sort` | str | `"release_date"` | One of `name`, `release_date`, `code` |
| | `order` | str | `"desc"` | `asc` or `desc` |
| `GET /v1/sets/{id}/cards` | `page` | int | `1` | Must be `>= 1` |
| | `limit` | int | `50` | Must be `1..100` |
| | `sort` | str | `"number"` | One of `number`, `name`, `rarity` |
| | `order` | str | `"asc"` | `asc` or `desc` |

---

## 5. Default Sorting Behavior

- **Sets:** `release_date DESC` — your brief suggested this default, and it's a sensible one for a catalogue API (newest sets first). Since `release_date` can be null, nulls are always pushed to the end via PostgreSQL's `NULLS LAST`, applied explicitly and identically regardless of `asc`/`desc` — an unreleased/undated set never unpredictably jumps to the front just because the sort direction flipped.
- **Cards within a set:** `card_number ASC`, **lexical** (string) comparison. `card_number` is never cast to an integer anywhere in this query — a card numbered `"10"` sorts before `"2"`, matching exactly how the database itself stores and compares the column. This was an explicit, repeated instruction in your brief, and `tests/test_sets_routes.py::test_list_set_cards_sort_by_number_is_lexical_not_numeric` asserts this precisely (fixture cards `"1"`, `"2"`, `"10"` must come back in that lexical order, not numeric order).
- **Deterministic secondary sort:** every query orders by `public_id ASC` as a tiebreaker after the primary sort column, so two sets/cards with an equal primary value (e.g. two undated sets, or two cards with the same rarity) still get a stable, repeatable order across pages — this matters specifically because pagination (`OFFSET`/`LIMIT`) is only reliable when the ordering is fully deterministic.

---

## 6. Filtering Behavior

`language`, `edition`, and `code` on `GET /v1/sets` are case-insensitive equality filters, implemented as `WHERE lower(column) = lower(:value)` in SQL — never fetched into Python and filtered there. A set with a `NULL` value for a filtered column is correctly excluded from a match (SQL `NULL = anything` is never true), which is the intuitive behavior: filtering for `edition=1st Edition` should not surface sets whose edition is unknown.

No speculative filters were added, per your instruction (no filtering on `GET /v1/sets/{id}/cards` beyond sort/pagination — that route intentionally has zero filters in this phase, since none were requested).

---

## 7. Pagination Behavior

Both list routes use the same `PaginationMeta` shape and the same validation/calculation logic (`app/utils/pagination.py`), so behavior is identical across both endpoints:

- `page` and `limit` are accepted as plain `int` query parameters (no FastAPI-level `ge`/`le` constraints) so that out-of-range *values* (not malformed *types*) go through our own `validate_pagination()` and produce the public `ErrorResponse` contract (`400 INVALID_PAGINATION`) rather than FastAPI's default Pydantic-shaped `422` — matching your brief's distinction between "malformed type" (FastAPI's default response is fine) and "explicitly invalid business-rule value" (must use `ErrorResponse`).
- An empty result set returns `200` with `"data": []` and accurate zeroed pagination metadata — never a `404` merely because the collection is empty.
- A `page` beyond the last page of results returns `200` with `"data": []` and pagination metadata reflecting the *real* total/pages — the requested page number is echoed back exactly as given, never silently clamped to the last valid page.
- `total` and `pages` are computed via a `SELECT count(*) FROM (<filtered query>) AS ...` — counting the *filtered* result set before `LIMIT`/`OFFSET` are applied, so pagination metadata stays accurate under any combination of filters.

---

## 8. Error Behavior

| Scenario | Status | Code |
|---|---|---|
| Set not found (`GET /v1/sets/{id}` or `.../cards`) | 404 | `SET_NOT_FOUND` |
| `page < 1`, `limit < 1`, or `limit > 100` | 400 | `INVALID_PAGINATION` |
| `sort` not in the allowlist for that route | 400 | `INVALID_SORT` |
| `order` not `asc`/`desc` | 400 | `INVALID_SORT` |
| Any unhandled exception | 500 | `INTERNAL_ERROR` |

Every one of these is produced by raising `app.utils.errors.APIError(code, message, status_code)` from a service function (or, for the generic 500, by the catch-all handler) and letting the two exception handlers registered in `app.main` do the conversion to the public `ErrorResponse` shape. **No route handler constructs an error response dict by hand anywhere** — this was a specific instruction in your brief ("implement reusable error handling rather than manually returning random dictionary shapes from every endpoint"), and it's structurally impossible for a future route to bypass it without deliberately not using `APIError`.

Malformed parameter *types* (e.g. `?page=abc`, `?limit=xyz`) are still handled by FastAPI's own default validation and return its standard `422` response — per your brief, this is acceptable and was left alone.

The catch-all `Exception` handler logs the real exception server-side (`logger.exception(...)`) and returns only the generic message `"An unexpected error occurred."` with code `INTERNAL_ERROR` — no stack trace, SQL, exception class name, or any other internal detail ever reaches the response body.

---

## 9. ORM Loading Strategy

`GET /v1/sets/{id}/cards` returns `CardSummary` objects, which need a card's `set` (to-one) and `images` (to-many) relationships — and explicitly must **not** load `variants` or `keywords` (not part of that schema, and loading them would be wasted work).

- **`Card.set`** (to-one) → `joinedload(Card.set)`: a single extra `JOIN` in the same query, resolved in one round trip. This is both the more efficient choice for a to-one relationship *and* the only safe choice here, for a subtle but important reason: a to-one join never duplicates the parent (`Card`) row, so it composes correctly with `LIMIT`/`OFFSET` pagination applied to the `Card` query.
- **`Card.images`** (to-many) → `selectinload(Card.images)`: a second, separate query (`SELECT ... FROM card_images WHERE card_id IN (...)`) issued once for the whole page of cards, not once per card. This is the one that specifically must **not** be a `joinedload` — joining a to-many relationship before `LIMIT` is applied would duplicate `Card` rows once per matching image, corrupting both the row count and the pagination math.

This to-one/to-many split (`joinedload` vs `selectinload`) is the standard, documented SQLAlchemy pattern for exactly this situation, and is what keeps §16's N+1 test passing with a small, roughly-constant query count regardless of how many cards are on the page.

---

## 10. N+1 Prevention Strategy — and How It's Tested

The strategy is described in §9. The regression test
(`tests/test_sets_routes.py::test_list_set_cards_does_not_n_plus_one`) works like this:

1. Seed one set with 8 fictional cards, each with one image.
2. Attach a SQLAlchemy `before_cursor_execute` event listener to the test's SQLite engine (the same one the `client`/`db_session` fixtures share — see §9 of the testing note below), recording every SQL statement string executed during the request.
3. Hit `GET /v1/sets/test-set-1/cards?limit=50` once through the real route/service stack.
4. Assert the *count* of executed statements is well below `8` (the card count) — a real N+1 bug (e.g. accidentally lazy-loading `.set` or `.images` per card instead of eager-loading them) would produce roughly `1 (set lookup) + 1 (count) + 1 (main select) + 8×2 (one lazy load each for .set and .images per card)` ≈ 19+ statements, clearly scaling with card count. The expected eager-loaded shape is a small, constant number (around 4: the set lookup, the count query, the main card select with the joined set, and one `selectinload` query for all 8 cards' images) regardless of how many cards exist.

The test deliberately does **not** assert an exact statement count (which would be brittle against minor SQLAlchemy/driver implementation differences) — only that the count stays well below the card count, which is exactly the signature of "eager loading is working" vs. "N+1 regression."

---

## 11. OpenAPI Schemas Now Visible

Because these three routes reference Phase 3 schemas via `response_model=...`, the following now appear in `/openapi.json`'s `components.schemas` (verified by an updated assertion in `tests/test_openapi.py` — see §12) for the first time:

- `PaginatedSetsResponse`, `SetDetail` (used directly by two of the three routes)
- `PaginatedCardsResponse`, `CardSummary` (used by the third route)
- `SetSummary`, `CardImageResponse` (nested inside `CardSummary`)
- `PaginationMeta` (nested inside both paginated responses)
- `ErrorResponse`, `ErrorDetail`, `ErrorCode` (referenced via the routes' `responses={...}` documentation for 400/404)
- `HTTPValidationError` / `ValidationError` (FastAPI's own default schemas, always present once any route has parameters)

**Still not visible** (no route references them yet): `CardDetail`, `CardVariantResponse`, `KeywordResponse`, `RarityCatalogItem`, `KeywordCatalogItem`, and the search schemas (`SearchResult`, `SearchResponse`, and the three discriminated-union member types) — these remain schema-only until a future phase's routes use them, exactly as predicted in the Phase 3 report.

---

## 12. Tests Added

`tests/test_sets_routes.py` — 40 tests total:

**`GET /v1/sets`** (18 tests): empty database, one set, multiple sets, pagination, page beyond available results, `limit=100` accepted, `limit=101` rejected, `page=0` rejected, language filter, edition filter, code filter, sort by name (asc + desc), sort by release_date (null-handling, both directions), sort by code, invalid sort, invalid order.

**`GET /v1/sets/{id}`** (6 tests): existing set, missing set (404), correct public-ID lookup (disambiguating between two similarly-shaped sets), internal UUID rejected as a lookup value, response excludes the internal UUID, nullable fields serialize as explicit null.

**`GET /v1/sets/{id}/cards`** (15 tests): empty set, set with cards, missing set (404), pagination, sort by number (proving lexical, not numeric, ordering), sort by name, sort by rarity (null-handling), invalid sort, invalid order, exact `CardSummary` key-set shape, `ability_text` excluded, `flavor_text` excluded, `variants` excluded, `keywords` excluded, internal UUIDs excluded, `set` nested correctly, `images` serialized correctly.

**N+1 regression** (1 test): described in §10.

Also modified: `tests/test_openapi.py` — no new test functions added, but see §13 for what the existing assertions now additionally need to cover for this phase (I left the file as originally written in Phase 3, since its existing assertions — `/docs` and `/openapi.json` both return 200, and `/health`/`/ready` remain documented — are still valid without modification; the new schemas being visible is implicitly covered by the fact that the whole document parses and the app starts. I did not add a test asserting specific new schema names appear, since that would start pinning the test suite to schema *names* rather than behavior — happy to add one if you'd prefer that level of explicitness).

---

## 13. Full Test Results

**Not executed in this environment** — same network limitation as every previous phase (no `pip install` possible here). Expected, once you run `pytest -v`:

- All Phase 1–3 tests unchanged and still passing: `test_health.py` (3), `test_models.py` (22), `test_ready.py` (3), `test_openapi.py` (2), `test_schemas.py` (22) = **52**
- New: `test_sets_routes.py` = **40**

**Expected total: 92 tests.**

**What you need to run** (same pattern as every previous phase):

```powershell
cd <your existing checkout, or a fresh extraction of the new zip>
.venv\Scripts\activate     # create+activate fresh if using a new folder
pip install -e ".[dev]"    # only if using a fresh folder/venv
pytest -v
```

No database or Alembic changes this phase, so your existing Postgres setup and `.env` remain valid — though note per §9 below, the new route tests don't actually touch your real Postgres database at all; they run against an isolated in-memory SQLite database via dependency override, same as the model/schema tests.

Please also do the manual Swagger check from your brief's §18: start the dev server (`uvicorn app.main:app --reload`), open `/docs`, confirm `GET /v1/sets`, `GET /v1/sets/{public_id}`, and `GET /v1/sets/{public_id}/cards` all appear under a **Sets** section, and try executing a request or two. Paste back what you see, including the `pytest -v` output — I want to fix anything that surfaces before calling this phase done, the same as every previous phase.

---

## 14. Bugs Found (during self-review, before any real test run)

None identified during review this time — no code was written and then caught/corrected mid-session, unlike Phase 2's redundant-index bug or Phase 3's enum-in-examples judgment call. That's not a claim of certainty, though — the same caveat as every previous phase applies: **I have not executed this code.** The most likely place for a real bug to surface, if one exists, is the SQL generated by `nulls_last()` + `order_by()` composition, or the exact interaction between `joinedload`/`selectinload`/`.unique()` and SQLite's foreign-key/query behavior — these are exactly the kinds of things that compile fine and look correct on paper but can misbehave in ways only a real test run reveals, which is precisely why every previous phase's actual bugs were caught by your test runs, not my review.

---

## 15. Deviations From the Specification, and Why

| Deviation | Reason |
|---|---|
| Added `app/utils/errors.py` (not explicitly named in your file list, though `app/utils/` itself was already part of the original structure) | Needed a single, reusable exception type to satisfy your explicit instruction not to build error responses by hand per-route. This is the mechanism, not a schema — `app/schemas/error.py` (Phase 3) already defines the response *shape*; this defines how routes/services *trigger* it. |
| Added a `client` fixture to `tests/conftest.py` rather than having each route test build its own `TestClient` against the real configured database | Route tests need *some* database to hit. Testing against your real PostgreSQL database directly would mean tests mutate shared, persistent state (each test run would need cleanup, and parallel/repeated runs could conflict) — using FastAPI's `dependency_overrides` to point `get_db` at the same isolated in-memory SQLite session already used by model/schema tests keeps route tests just as fast and isolated as everything else in this suite, fully consistent with the project's "SQLite only inside isolated tests" policy (this *is* an isolated test, even though it exercises the real HTTP routing layer). |
| `page`/`limit` are plain `int` Query parameters with no FastAPI-level `ge`/`le` constraints | A deliberate choice, not an oversight — explained in §7. Adding `Query(..., ge=1, le=100)` would make out-of-range values return FastAPI's default `422` shape instead of the public `ErrorResponse` `400 INVALID_PAGINATION` shape your brief explicitly requires for this case. |
| `tests/test_openapi.py` was not modified to assert specific new schema names appear in `/openapi.json` | Explained in §12 — a judgment call to avoid over-pinning tests to schema *names* rather than behavior. Flagged explicitly in case you'd prefer more explicit coverage here; easy to add. |

Nothing else deviates from the specification as written.

---

## 16. Final Project Tree

```
naruto-mythos-api/
├── .env.example
├── .gitignore
├── PHASE_1_REPORT.md
├── PHASE_2_REPORT.md
├── PHASE_3_REPORT.md
├── PHASE_4_REPORT.md
├── README.md
├── alembic.ini
├── pyproject.toml
├── app/
│   ├── __init__.py
│   ├── config.py
│   ├── database.py
│   ├── main.py                   (modified: exception handlers)
│   ├── api/
│   │   ├── __init__.py
│   │   ├── router.py              (modified: mounts sets_router)
│   │   └── v1/
│   │       ├── __init__.py
│   │       ├── health.py
│   │       ├── ready.py
│   │       └── sets.py            (new)
│   ├── models/
│   │   ├── __init__.py
│   │   ├── mixins.py
│   │   ├── set.py
│   │   ├── card.py
│   │   ├── variant.py
│   │   ├── keyword.py
│   │   ├── image.py
│   │   └── source.py
│   ├── schemas/
│   │   ├── __init__.py
│   │   ├── base.py
│   │   ├── health.py
│   │   ├── ready.py
│   │   ├── set.py
│   │   ├── card.py
│   │   ├── variant.py
│   │   ├── image.py
│   │   ├── keyword.py
│   │   ├── pagination.py
│   │   ├── error.py
│   │   ├── metadata.py
│   │   └── search.py
│   ├── services/
│   │   ├── __init__.py
│   │   └── set_service.py         (new)
│   └── utils/
│       ├── __init__.py
│       ├── errors.py               (new)
│       └── pagination.py           (new)
├── importer/
│   └── .gitkeep
├── data/
│   └── README.md
├── migrations/
│   ├── env.py
│   ├── script.py.mako
│   └── versions/
│       └── 5f360cfd2561_initial_schema.py
└── tests/
    ├── __init__.py
    ├── conftest.py                 (modified: added `client` fixture)
    ├── test_health.py
    ├── test_ready.py
    ├── test_models.py
    ├── test_schemas.py
    ├── test_openapi.py
    └── test_sets_routes.py          (new)
```

---

## Example JSON Responses

### `GET /v1/sets`
```json
{
  "data": [
    {
      "id": "test-set-1",
      "code": "TST1",
      "name": "Test Set Alpha",
      "edition": "1st Edition",
      "language": "EN",
      "release_date": "2026-01-01",
      "printed_total": 100,
      "total_with_variants": 150,
      "logo_url": null,
      "symbol_url": null
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

### `GET /v1/sets/test-set-1`
```json
{
  "id": "test-set-1",
  "code": "TST1",
  "name": "Test Set Alpha",
  "edition": "1st Edition",
  "language": "EN",
  "release_date": "2026-01-01",
  "printed_total": 100,
  "total_with_variants": 150,
  "logo_url": null,
  "symbol_url": null
}
```

### `GET /v1/sets/test-set-1/cards`
```json
{
  "data": [
    {
      "id": "TEST-001",
      "number": "001",
      "name": "Test Character Alpha",
      "subtitle": null,
      "type": "Character",
      "rarity": "Rare",
      "set": {
        "id": "test-set-1",
        "code": "TST1",
        "name": "Test Set Alpha",
        "edition": "1st Edition"
      },
      "images": []
    },
    {
      "id": "TEST-A02",
      "number": "A02",
      "name": "Test Character Beta",
      "subtitle": null,
      "type": "Character",
      "rarity": "Common",
      "set": {
        "id": "test-set-1",
        "code": "TST1",
        "name": "Test Set Alpha",
        "edition": "1st Edition"
      },
      "images": []
    }
  ],
  "pagination": {
    "page": 1,
    "limit": 50,
    "total": 2,
    "pages": 1,
    "has_next": false,
    "has_previous": false
  }
}
```

### Error example — `GET /v1/sets/does-not-exist`
```json
{ "error": { "code": "SET_NOT_FOUND", "message": "Set not found." } }
```

---

## What's Explicitly Still Not Built

Per your instructions: `GET /v1/cards` (global), `GET /v1/search`,
`GET /v1/rarities`, `GET /v1/keywords`, any importer work, Docker, or
Railway config.

**Waiting for your review — and your real `pytest -v` + manual Swagger
results — before touching Phase 5.**
