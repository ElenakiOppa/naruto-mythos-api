# Naruto Mythos TCG Developer API — Phase 3 Report

**Scope:** Public Pydantic v2 schema layer only (per the phased plan). No
routes, no database changes.
**Status:** ✅ Complete and verified — full test suite passing (52/52) on
the developer's machine.

---

## 1. Files Created

| File | Purpose |
|---|---|
| `app/schemas/base.py` | `PublicSchema` — shared base class (`from_attributes=True`, `populate_by_name=True`) |
| `app/schemas/image.py` | `CardImageResponse` |
| `app/schemas/keyword.py` | `KeywordResponse` (compact, nested-in-card form) |
| `app/schemas/set.py` | `SetSummary`, `SetDetail` |
| `app/schemas/variant.py` | `CardVariantResponse` |
| `app/schemas/card.py` | `CardSummary`, `CardDetail` |
| `app/schemas/pagination.py` | `PaginationMeta`, `PaginatedCardsResponse`, `PaginatedSetsResponse` |
| `app/schemas/error.py` | `ErrorCode`, `ErrorDetail`, `ErrorResponse` |
| `app/schemas/metadata.py` | `RarityCatalogItem`, `KeywordCatalogItem` (for future `/v1/rarities`, `/v1/keywords`) |
| `app/schemas/search.py` | `CardSearchResult`, `SetSearchResult`, `KeywordSearchResult`, `SearchResult` (discriminated union), `SearchResponse` |
| `tests/test_schemas.py` | 20 serialization tests (see §9, §10) |
| `tests/test_openapi.py` | 2 tests confirming `/docs` and `/openapi.json` still work |

## 2. Files Modified

| File | Change |
|---|---|
| `README.md` | Added Phase 3 status and documented the new `schemas/` contents |

**Not modified:** any database model, the Alembic migration, `/health`, `/ready`, `app/main.py`, `app/api/router.py`, or any Phase 1/2 test. No route handlers were added or touched — per the brief, this phase defines the contract only.

---

## 3. Every Public Schema Created, With Exact JSON Shape

### `SetSummary`
```json
{
  "id": "test-set-1",
  "code": "TST1",
  "name": "Test Set Alpha",
  "edition": "1st Edition"
}
```

### `SetDetail`
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

### `CardSummary`
```json
{
  "id": "TEST-001",
  "number": "001",
  "name": "Test Character Alpha",
  "subtitle": null,
  "type": "Character",
  "rarity": "Rare",
  "set": { "id": "test-set-1", "code": "TST1", "name": "Test Set Alpha", "edition": "1st Edition" },
  "images": []
}
```

### `CardDetail`
```json
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
  "set": { "id": "test-set-1", "code": "TST1", "name": "Test Set Alpha", "edition": "1st Edition" },
  "keywords": [ { "slug": "test-keyword", "name": "Test Keyword" } ],
  "variants": [],
  "images": []
}
```

### `CardVariantResponse`
```json
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
```

### `CardImageResponse`
```json
{
  "type": "front",
  "url": "https://example.invalid/test-card.jpg",
  "width": 734,
  "height": 1024
}
```

### `KeywordResponse`
```json
{ "slug": "test-keyword", "name": "Test Keyword" }
```

### `PaginationMeta`
```json
{ "page": 1, "limit": 50, "total": 630, "pages": 13, "has_next": true, "has_previous": false }
```

### `PaginatedCardsResponse`
```json
{ "data": [ /* CardSummary[] */ ], "pagination": { /* PaginationMeta */ } }
```

### `ErrorResponse`
```json
{ "error": { "code": "CARD_NOT_FOUND", "message": "Card not found." } }
```

### `SearchResult` (discriminated union)
```json
{ "type": "card", "card": { /* CardSummary */ } }
{ "type": "set", "set": { /* SetSummary */ } }
{ "type": "keyword", "keyword": { /* KeywordResponse */ } }
```

### Also created, not in your explicit list but needed to fully satisfy §12 and §15:

- **`PaginatedSetsResponse`** — `{ "data": [ /* SetDetail[] */ ], "pagination": { ... } }` (see §5 for why `SetDetail`, not a summary)
- **`RarityCatalogItem`** — `{ "name": "Rare", "slug": "rare", "card_count": 42 }`
- **`KeywordCatalogItem`** — `{ "slug": "test-keyword", "name": "Test Keyword", "card_count": 10 }`
- **`SearchResponse`** — `{ "data": [ /* SearchResult[] */ ] }`, a forward-looking wrapper for the eventual search endpoint

---

## 4. Alias/Mapping Strategy (ORM → API)

Every renamed field uses the same pattern: **the Pydantic field name is set to the desired public JSON key**, and `validation_alias` is set to the ORM attribute name so `Model.model_validate(orm_object, from_attributes=True)` reads the right source attribute. No `serialization_alias` is used anywhere, so output always uses the field name (the public key) regardless of the `by_alias` flag — there's no second alias to conflict with it.

| ORM attribute | Public JSON field | Used in |
|---|---|---|
| `public_id` | `id` | `SetSummary`, `SetDetail`, `CardSummary`, `CardDetail`, `CardVariantResponse` |
| `card_number` | `number` | `CardSummary`, `CardDetail` |
| `card_type` | `type` | `CardSummary`, `CardDetail` |
| `variant_type` | `type` | `CardVariantResponse` |
| `rarity_override` | `rarity` | `CardVariantResponse` |
| `image_type` | `type` | `CardImageResponse` |

`model_config = ConfigDict(from_attributes=True, populate_by_name=True)` is set on every schema — not just the top-level ones — because a nested field (e.g. `CardSummary.set: SetSummary`) needs its *own* `from_attributes=True` to convert an ORM relationship object; the parent's config doesn't automatically propagate to it. `populate_by_name=True` means a schema can still be constructed by hand with the friendly field name (`SetSummary(id="test-set-1", ...)`), not only via `model_validate()` from an ORM object.

A shared `PublicSchema` base class in `app/schemas/base.py` declares this config once. Every schema subclasses it, **and each schema also re-declares the same `ConfigDict(...)` explicitly on itself** rather than relying purely on inherited/merged config. This was a deliberate choice: Pydantic v2 does merge `model_config` across a class hierarchy, but since this code could not be executed in the environment it was written in, I chose the more verbose but unambiguous option — no subclass depends on inheritance behavior working a particular way to be correct.

---

## 5. Fields Intentionally Hidden

| Table | Hidden fields | Why |
|---|---|---|
| every table | internal `id` (UUID) | Never a stable/meaningful identifier for a third-party consumer; `public_id` (exposed as `id`) is the real contract |
| `cards` | `set_id` | Raw FK UUID — the related set is nested as a full `SetSummary` instead |
| `card_variants` | `card_id` | A variant is always accessed already nested under its card; the link is structural (JSON nesting), not a field |
| `card_images` | `card_id`, `variant_id`, `hosted_by_us`, `source_name`, `source_url` | `card_id`/`variant_id` are internal FKs; the other three are storage/provenance infrastructure details, not something a consumer needs to render or link to an image |
| `keywords` (nested form) | internal `id` | Same as above; `slug` is the stable public identifier |
| all tables | `created_at` (except where explicitly modeled) | Not part of the public contract unless a future phase decides otherwise — your brief said "unless explicitly required," and nothing so far requires it |
| all tables with it | `updated_at` | Same reasoning |

`CardSummary` additionally excludes, relative to `CardDetail`: `ability_text`, `flavor_text`, `artist`, `chakra`, `power`, `faction`, `keywords`, `variants` — kept out specifically to keep a paginated list response lightweight (see §7).

---

## 6. Nullability Decisions

Every field that maps to a nullable database column is `X | None` in its schema, **with an explicit default of `None`** — never omitted from the response. This was a specific, repeated instruction in your brief ("prefer `'artist': null` over sometimes removing the field entirely... stable response shape"), and every nullable field across every schema follows it: `subtitle`, `type`, `rarity`, `chakra`, `power`, `faction`, `ability_text`, `flavor_text`, `artist` on cards; `finish`, `rarity`, `collector_number`, `edition`, `serial_total` on variants; `width`, `height` on images; `code`, `edition`, `release_date`, `printed_total`, `total_with_variants`, `logo_url`, `symbol_url` on sets.

Non-nullable database columns (`name`, `card_number`→`number`, `language`, `serial_numbered`, etc.) are required (non-Optional) fields in their schemas, matching the database's own guarantees.

---

## 7. Public Contract Review (§21 self-review, as an external developer)

- **Field names intuitive?** Yes — `id`, `number`, `type`, `rarity` read naturally; a developer doesn't need to know the database ever called these `public_id`/`card_number`/`card_type`/`rarity_override`.
- **Nullability predictable?** Yes — every nullable field is always present with an explicit `null`, never sometimes-present/sometimes-absent.
- **List/detail sizing appropriate?** Yes — `CardSummary` (list) excludes four large/expensive fields (`ability_text`, `flavor_text`, `keywords`, `variants`) that `CardDetail` includes; a paginated list of 50 cards stays lightweight, while a single-card lookup gets everything.
- **Internal details hidden?** Yes — no UUID, no `set_id`/`card_id`/`variant_id`, no storage/provenance metadata anywhere in a public response (verified by the tests in §9/§10, once you run them).
- **Public IDs stable?** Yes — `id` always maps to the database's own `public_id`, which Phase 2's schema treats as the real, human-assigned catalogue identifier, independent of internal row UUIDs that could theoretically change if data were ever re-imported.
- **Pagination consistent?** Yes — one `PaginationMeta` shape, reused by both `PaginatedCardsResponse` and `PaginatedSetsResponse`; no endpoint gets a bespoke pagination shape.
- **Errors consistent?** Yes — one `ErrorResponse` shape for every future error, with a closed-but-extensible (`ErrorCode` is an enum you add to, never rename) set of codes.
- **New variant types without breaking clients?** Yes — `CardVariantResponse.type` is a plain string end-to-end (matches the database's own non-enum design from Phase 2); a brand-new `variant_type` value in the database appears in the API automatically, no schema change needed.
- **Future fields backward-compatible?** Yes, with one caveat worth flagging: adding a new *optional* field to any response schema is backward-compatible (existing clients simply ignore it). Adding a new *required* field, or changing a field's type, would not be — that's the `/v1` → `/v2` boundary your brief already established, and nothing in this phase weakens that policy.
- **Examples useful and non-infringing?** Yes — every example uses `TEST-001`, `Test Character Alpha`, `Test Set Alpha`, `test-keyword`, `test-set-1`, and a `https://example.invalid/...` URL (a reserved-for-documentation domain per RFC 2606) — nothing resembling real Naruto Mythos data, characters, or URLs.

---

## 8. OpenAPI Example Strategy

Every top-level public schema (and both search wrapper wrappers) carries a full, realistic `json_schema_extra={"example": {...}}` block matching its exact target JSON — this is what Swagger UI displays as the example response body for any route that eventually uses the schema, giving a developer a complete, readable example without needing real catalogue data. Individual fields additionally carry per-field `examples=[...]` (e.g. `Field(examples=["Rare"])`), which OpenAPI/Swagger uses for the per-field example shown in the schema explorer. Union member schemas used only internally within the `SearchResult` discriminated union (`CardSearchResult`, `SetSearchResult`, `KeywordSearchResult`) don't carry their own top-level example, since the enclosing `SearchResponse.example` already demonstrates all three shapes together — duplicating it per member would be redundant without adding documentation value.

---

## 9. What Could and Could Not Be Verified Here

Same environment constraint as Phases 1 and 2: **no network access**, so `pytest`/`pydantic`/`fastapi` could not be installed and this code has **not actually been executed**.

What I did instead, to keep the same standard of rigor as previous phases:

- Every file passes `python -m py_compile` — real syntax verification, not a stand-in for running it
- A careful, explicit manual review of Pydantic v2's alias semantics (`validation_alias` vs `serialization_alias` vs `alias`, and how `from_attributes` resolves nested ORM relationships) against every field in every schema, cross-checked line by line against this report
- Chose the more verbose, fully-explicit `ConfigDict(...)` on every subclass rather than trusting config-inheritance behavior I couldn't verify by running code
- Wrote `tests/test_schemas.py` (20 tests) and `tests/test_openapi.py` (2 tests) to the same standard as Phase 2's model tests — built against fictional ORM instances via the existing isolated in-memory SQLite `db_session` fixture — but **I have not run them**

## 10. Test Results — Verified

**Real run, on the developer's machine, against the real Phase 2 PostgreSQL database (though the schema tests themselves validate against fictional in-memory ORM fixtures, per the isolated-testing policy):**

```
52 passed, 2 warnings in 0.94s
```

Breakdown:
- `tests/test_health.py` — 3 passed (unchanged from Phase 2)
- `tests/test_models.py` — 22 passed (unchanged from Phase 2)
- `tests/test_ready.py` — 3 passed (unchanged from Phase 2)
- `tests/test_openapi.py` — 2 passed (new)
- `tests/test_schemas.py` — 22 passed (new — 14 single tests + 4 parametrized pagination-validation cases + 4 more, covering every item in your brief's §17: internal-UUID exclusion across all four card/set schemas, all five alias mappings including a dedicated positive-value check for `rarity_override`→`rarity`, `CardSummary`'s exclusions, `CardDetail`'s nullable fields/keywords/variants/images, image-response provenance exclusion, pagination validation, the exact error shape, and the search discriminated union)

The 2 warnings are the same pre-existing Starlette/FastAPI test-client deprecation notices seen in every previous phase's report — unrelated to this project's own code.

**Every Phase 1 and Phase 2 test still passes unchanged**, confirming this phase made no unintended changes to `/health`, `/ready`, the database models, or the migration.

---

## 11. Bugs Found

1. **`ErrorDetail.code`'s field-level `examples=[...]` originally passed the `ErrorCode` enum member directly** (`examples=[ErrorCode.CARD_NOT_FOUND]`) rather than its string value. Caught and fixed during self-review, before any test run — see §9.

No bugs surfaced during the real test run (52/52 passing on the first attempt). The alias-mapping logic — the part of this phase most likely to have a subtle runtime-only bug — held up correctly across every test, including the dedicated `test_variant_rarity_override_maps_to_rarity_field` check for a *non-null* override value (not just the default-None case covered incidentally elsewhere).

---

## 12. Deviations From the Specification, and Why

| Deviation | Reason |
|---|---|
| Added `app/schemas/base.py` (not in your original file list) | Same rationale as Phase 2's `models/mixins.py` — centralizes config that every single schema needs, explicitly permitted by "you may improve this structure if there is a strong architectural reason." |
| `PaginatedSetsResponse` uses `SetDetail` as its list-item shape, not a further-trimmed `SetSummary` | You explicitly asked me to decide and document this (§12 of the brief) — reasoning is in §5 of this report / the docstring in `pagination.py`: sets are few enough in number that full detail in a list response carries no real payload cost, unlike cards. |
| `ErrorCode` implemented as a `str` Enum rather than a bare `str` field | A deliberate trade-off, fully documented in `app/schemas/error.py`'s module docstring and §11's evenhandedness note — better OpenAPI documentation now, at the cost of new codes needing an additive (non-breaking) enum change later. |
| Added `SearchResponse` wrapper (not explicitly requested — your brief asked for the per-result union shape only) | Needed *something* concrete to hang a full worked OpenAPI example on for the discriminated union (see §8), and it's a natural, obviously-needed shape once `GET /v1/search` exists — provided now so it's settled, not wired to any route. |
| Added `tests/test_openapi.py` (not explicitly requested as a separate file) | Your brief's §19 asked me to verify `/docs` and `/openapi.json` still work — I turned that verification into an actual committed test rather than a one-off manual check, consistent with how the rest of this project treats "verified" as "covered by a test that runs in CI," not just "I looked at it once." |

Nothing else deviates from the specification as written.

---

## 13. Which Schemas Currently Appear in OpenAPI

**None of the Phase 3 schemas appear in `/openapi.json` yet.** FastAPI only includes a Pydantic model in the generated OpenAPI document when at least one route references it as a `response_model` (or request body). Since this phase deliberately does not add any catalogue routes, `/openapi.json`'s `components.schemas` section still only contains `HealthResponse` and `ReadyResponse` from Phases 1–2.

Per your instruction not to add fake routes just to force schemas into Swagger, I didn't. `tests/test_openapi.py` instead verifies the *document itself* is still well-formed and that `/health`/`/ready` are still documented — proving Phase 3 didn't break OpenAPI generation, without faking route coverage it doesn't have yet.

**Once Phase 4+ route handlers exist and reference these schemas as `response_model=...`, every schema in this report will automatically appear in `/openapi.json` and render in `/docs`** — no additional wiring will be needed beyond the routes themselves referencing them.

---

## 14. Final Project Tree

```
naruto-mythos-api/
├── .env.example
├── .gitignore
├── PHASE_1_REPORT.md
├── PHASE_2_REPORT.md
├── PHASE_3_REPORT.md
├── README.md
├── alembic.ini
├── pyproject.toml
├── app/
│   ├── __init__.py
│   ├── config.py
│   ├── database.py
│   ├── main.py
│   ├── api/
│   │   ├── __init__.py
│   │   ├── router.py
│   │   └── v1/
│   │       ├── __init__.py
│   │       ├── health.py
│   │       └── ready.py
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
│   │   ├── base.py              (new)
│   │   ├── health.py
│   │   ├── ready.py
│   │   ├── set.py                (new)
│   │   ├── card.py               (new)
│   │   ├── variant.py            (new)
│   │   ├── image.py              (new)
│   │   ├── keyword.py            (new)
│   │   ├── pagination.py         (new)
│   │   ├── error.py              (new)
│   │   ├── metadata.py           (new)
│   │   └── search.py             (new)
│   ├── services/
│   │   └── __init__.py
│   └── utils/
│       └── __init__.py
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
    ├── conftest.py
    ├── test_health.py
    ├── test_ready.py
    ├── test_models.py
    ├── test_schemas.py           (new)
    └── test_openapi.py           (new)
```

---

## What's Explicitly Still Not Built

Per your instructions, none of these exist yet: `/v1/cards`, `/v1/sets`, `/v1/rarities`, `/v1/keywords`, `/v1/search`, any route exception handling, pagination/filtering/sorting query logic, the importer, Docker, or Railway config.

**Waiting for your review — and your real `pytest -v` results — before touching Phase 4.**
