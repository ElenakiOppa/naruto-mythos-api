# Naruto Mythos TCG Developer API — Phase 2 Report

**Scope:** Database models + Alembic migration only (per the phased plan).
**Status:** ✅ Complete and verified — migration applied to and rolled back from real PostgreSQL 18.6, full test suite passing (28/28).

---

## 1. Files Created

| File | Purpose |
|---|---|
| `app/models/mixins.py` | Shared `UUIDPrimaryKeyMixin` / `TimestampMixin` (not in the original file list — added; see §17) |
| `app/models/set.py` | `CardSet` model → `sets` table |
| `app/models/card.py` | `Card` model → `cards` table |
| `app/models/variant.py` | `CardVariant` model → `card_variants` table |
| `app/models/keyword.py` | `Keyword` model + `card_keywords` association table |
| `app/models/image.py` | `CardImage` model → `card_images` table |
| `app/models/source.py` | `SourceRecord` model → `source_records` table |
| `app/schemas/ready.py` | `ReadyResponse` schema for `/ready` |
| `app/api/v1/ready.py` | `GET /ready` readiness endpoint |
| `alembic.ini` | Alembic configuration (no hard-coded DB URL) |
| `migrations/env.py` | Alembic environment — pulls `DATABASE_URL` from `app.config.get_settings()` |
| `migrations/script.py.mako` | Template for future `alembic revision` runs |
| `migrations/versions/5f360cfd2561_initial_schema.py` | Initial schema migration (hand-written, reviewed — see §11) |
| `tests/conftest.py` | Shared pytest fixtures: self-contained env defaults + isolated in-memory SQLite `db_session` fixture |
| `tests/test_models.py` | 23 model/constraint/relationship/cascade tests |
| `tests/test_ready.py` | 3 tests for `/ready`, with mocked DB connectivity |

## 2. Files Modified

| File | Change |
|---|---|
| `app/api/v1/health.py` | Removed all database access. Now a pure liveness check — no behavior change to its response contract. |
| `app/api/router.py` | Mounted the new `/ready` router alongside `/health`. |
| `tests/test_health.py` | Added a timing assertion (`< 2s`) proving `/health` never performs I/O; existing assertions on response shape/content unchanged. |
| `app/models/__init__.py` | Now imports all six model modules so `Base.metadata` (and Alembic autogenerate) see the complete schema. |
| `README.md` | Added Phase 2 status, database setup, and full Alembic usage instructions. |

**Not modified:** `app/config.py`, `app/database.py` (Phase 1's `connect_timeout=3` fix is retained and now backs `/ready`), `app/main.py`, CORS behavior, `.env.example`, `pyproject.toml` (all Phase 2 dependencies — SQLAlchemy, Alembic, psycopg — were already listed in Phase 1).

---

## 3. Health Check Change (Section 1 of the brief)

- **`GET /health`** — response contract is **unchanged**: `{"status": "ok", "version": "1.0.0"}`. It now performs zero database access, so it can never be slow or dependent on Postgres being up.
- **`GET /ready`** (new) — checks PostgreSQL connectivity via the existing engine (which already has a 3-second `connect_timeout` from the Phase 1 bug fix).
  - DB reachable → `200 {"status": "ready"}`
  - DB unreachable → `503 {"status": "not_ready"}`
  - Never exposes host, database name, credentials, or raw exception text — confirmed by a test that plants a fake exception message containing a password and a hostname, then asserts neither appears anywhere in the response body.

---

## 4. Final Database Tables

### `sets`
Important columns: `id` (UUID PK), `public_id` (unique, indexed), `code`, `name` (indexed), `edition`, `language` (default `"EN"`), `release_date`, `printed_total`, `total_with_variants`, `logo_url`, `symbol_url`, `created_at`, `updated_at`.

### `cards`
Important columns: `id` (UUID PK), `public_id` (unique, indexed), `set_id` (FK → `sets.id`), `card_number` (string, indexed), `name` (indexed), `subtitle`, `card_type` (indexed), `rarity` (indexed), `chakra`, `power`, `faction`, `ability_text`, `flavor_text`, `artist`, `created_at`, `updated_at`.

### `card_variants`
Important columns: `id` (UUID PK), `public_id` (unique, indexed), `card_id` (FK → `cards.id`), `variant_type` (free-text string, indexed — no ENUM), `finish`, `rarity_override`, `collector_number`, `language`, `edition`, `serial_numbered` (bool, default `false`), `serial_total`, `created_at`, `updated_at`.

### `keywords`
Important columns: `id` (UUID PK), `slug` (unique, indexed), `name`, `created_at`, `updated_at`.

### `card_keywords` (association table)
Columns: `card_id`, `keyword_id` — composite primary key, both FKs `ON DELETE CASCADE`.

### `card_images`
Important columns: `id` (UUID PK), `card_id` (FK → `cards.id`), `variant_id` (nullable FK → `card_variants.id`), `image_type` (default `"front"`), `url`, `source_name`, `source_url`, `hosted_by_us` (default `false`), `width`, `height`, `created_at` **only** (no `updated_at` — see §17).

### `source_records`
Important columns: `id` (UUID PK), `entity_type`, `entity_id` (UUID, **no FK** — see §17), `source_name` (indexed), `source_url`, `external_id`, `content_hash`, `first_seen_at`, `last_seen_at`.

---

## 5. Foreign Keys

| Table.Column | References | ON DELETE |
|---|---|---|
| `cards.set_id` | `sets.id` | `RESTRICT` |
| `card_variants.card_id` | `cards.id` | `CASCADE` |
| `card_images.card_id` | `cards.id` | `CASCADE` |
| `card_images.variant_id` | `card_variants.id` | `SET NULL` |
| `card_keywords.card_id` | `cards.id` | `CASCADE` |
| `card_keywords.keyword_id` | `keywords.id` | `CASCADE` |

`source_records.entity_id` intentionally has **no** foreign key (see §17).

## 6. Unique Constraints

- `sets.public_id`
- `cards.public_id`
- `cards(set_id, card_number)` — composite; allows the same collector number across different sets, forbids it within one set
- `card_variants.public_id`
- `keywords.slug`
- `card_keywords(card_id, keyword_id)` — enforced via the composite primary key

## 7. Check Constraints

- `sets`: `printed_total >= 0` (or null), `total_with_variants >= 0` (or null)
- `cards`: `chakra >= 0` (or null), `power >= 0` (or null)
- `card_variants`: `serial_total > 0` (or null) — `serial_numbered=false` never forces `serial_total` to exist
- `card_images`: `width > 0` (or null), `height > 0` (or null)

## 8. Indexes

| Index | Columns | Why |
|---|---|---|
| `ix_sets_public_id` (unique) | `sets.public_id` | Primary lookup path for the API |
| `ix_sets_code` | `sets.code` | Filter by set code |
| `ix_sets_name` | `sets.name` | Search/filter by set name |
| `ix_cards_public_id` (unique) | `cards.public_id` | Primary lookup path for the API |
| `ix_cards_set_id` | `cards.set_id` | `GET /v1/sets/{id}/cards`, join performance |
| `ix_cards_card_number` | `cards.card_number` | Filter/search by number |
| `ix_cards_name` | `cards.name` | Case-sensitive prefix of name search (Phase 7 will layer case-insensitive search on top) |
| `ix_cards_card_type` | `cards.card_type` | Filter by type |
| `ix_cards_rarity` | `cards.rarity` | Filter by rarity |
| `ix_card_variants_public_id` (unique) | `card_variants.public_id` | Primary lookup path |
| `ix_card_variants_card_id` | `card_variants.card_id` | Load a card's variants without a scan |
| `ix_card_variants_variant_type` | `card_variants.variant_type` | Filter by variant type |
| `ix_keywords_slug` (unique) | `keywords.slug` | Primary lookup + join key |
| `ix_card_images_card_id` | `card_images.card_id` | Load a card's images without a scan |
| `ix_card_images_variant_id` | `card_images.variant_id` | Load a variant's images without a scan |
| `ix_source_records_source_name` | `source_records.source_name` | Filter by source |
| `ix_source_records_entity_type_entity_id` (composite) | `entity_type, entity_id` | Primary provenance lookup: "what do we know about this entity" |
| `ix_source_records_source_name_external_id` (composite) | `source_name, external_id` | De-duplication lookup during import: "did source X already give us external ID Y" |

No index was added on `card_keywords` beyond its composite primary key — as an association table it's always queried by one or both of those columns, both covered by the PK.

**Deliberately not indexed separately:** `source_records.entity_type` alone — it's the leftmost column of the composite `(entity_type, entity_id)` index, so a standalone index would be redundant (documented in `app/models/source.py`).

## 9. ORM Relationships

```
CardSet
 └── cards           (CardSet.cards / Card.set)            [no ORM delete cascade — see §10]

Card
 ├── variants         (Card.variants / CardVariant.card)     [cascade="all, delete-orphan"]
 ├── images           (Card.images / CardImage.card)         [cascade="all, delete-orphan"]
 └── keywords         (Card.keywords / Keyword.cards)        [many-to-many via card_keywords]

CardVariant
 └── images           (CardVariant.images / CardImage.variant) [no ORM delete cascade — nullify instead]
```

## 10. Cascade / Delete Behavior — Decisions and Rationale

| Action | Behavior | Why |
|---|---|---|
| Delete a **Card** | Its `CardVariant`s, `CardImage`s, and `card_keywords` association rows are all deleted (DB-level `ON DELETE CASCADE`, mirrored by ORM `cascade="all, delete-orphan"`) | Explicit requirement in the brief |
| Delete a **CardVariant** | The parent `Card` is untouched. Any `CardImage`s pointing at that variant have `variant_id` set to `NULL` rather than being deleted | An image's URL/metadata still has value even if the specific variant record it depicted gets corrected or removed later — deleting the image too would be a surprising, silent data loss from what might be a routine catalogue correction |
| Delete a **CardSet** that still has `Card`s | **Rejected** — `ON DELETE RESTRICT` at the DB level | Not explicitly specified in the brief, but the brief's own hierarchy diagram treats `Card`s as owned by a `Set`; allowing a `Set` delete to cascade away an entire catalogue of cards (or silently orphan them) seemed like the wrong default for a table this consequential. If bulk set removal is ever needed, it should be an explicit, deliberate operation on the cards first. |
| Delete a **Keyword** | Its `card_keywords` rows are removed (`ON DELETE CASCADE`); the `Card`s themselves are untouched | Keywords are reusable, catalogue-wide tags — never owned by a single card |

No child→parent cascades exist anywhere (e.g. deleting a variant never deletes its card).

---

## 11. Alembic Migration

- **Revision ID:** `5f360cfd2561`
- **Down revision:** `None` (this is the initial migration)
- This migration was **hand-written**, not generated via `alembic revision --autogenerate`, and then manually cross-checked column-by-column against every model file. See §12 for why autogenerate wasn't used here.
- One real bug was caught and fixed during that manual review: four columns (`sets.public_id`, `cards.public_id`, `card_variants.public_id`, `keywords.slug`) were initially given **both** a separate named `UniqueConstraint` **and** a separate plain index — which would have created two redundant index structures over the same column in Postgres. Fixed by using a single `unique=True` index for each, matching what the ORM models themselves declare (`Column(..., unique=True, index=True)` compiles to exactly one unique index).

## 12. Migration Verification — Result

**Verified against real PostgreSQL 18.6** on the developer's machine (this could not be done in the sandboxed environment this code was authored in — see the note at the end of this section for that history).

```
alembic upgrade head
→ Running upgrade  -> 5f360cfd2561, initial schema: sets, cards, card_variants,
  keywords, card_keywords, card_images, source_records
```

`\dt` confirmed all 7 tables created (plus Alembic's own `alembic_version` bookkeeping table).

`\d cards` confirmed every constraint landed exactly as modeled:
- Both check constraints: `ck_cards_chakra_non_negative`, `ck_cards_power_non_negative`
- The composite unique constraint: `uq_cards_set_id_card_number`
- The foreign key with the intended delete behavior: `fk_cards_set_id_sets ... ON DELETE RESTRICT`
- The three reverse references, each with the correct `ON DELETE CASCADE`: from `card_images`, `card_keywords`, `card_variants`
- All six indexes on `cards`, including `ix_cards_public_id` correctly created as `UNIQUE`

**Rollback verified:**
```
alembic downgrade base
→ all 7 tables dropped (only alembic_version remained)
alembic upgrade head
→ re-applied cleanly
```

Both directions work. The redundant-index bug fixed during manual review (§11) did not resurface, and no other issues appeared.

<details>
<summary>Why this couldn't be verified in the authoring environment (historical note)</summary>

The sandbox this code was originally written in had no network access and no PostgreSQL or Docker installed, so the migration could only be syntax-checked and manually cross-referenced against the models at authoring time — not actually executed. That gap has now been closed by running it for real, as recorded above.
</details>

## 13. Test Results

**Verified — real run, real PostgreSQL running underneath (though the model tests themselves use an isolated in-memory SQLite fixture per the project's testing policy; only `/ready`'s mocked tests and the app's own startup config touch the real `DATABASE_URL`):**

```
28 passed, 2 warnings in 0.68s
```

Breakdown:
- `tests/test_health.py` — 3 passed
- `tests/test_models.py` — 22 passed (covering every scenario from your brief's §13: set creation, card-belongs-to-set, public_id uniqueness for cards and variants, card number repeat-across-sets vs duplicate-within-set, non-numeric card numbers, negative chakra/power rejection, variant creation, invalid serial_total rejection, serial_numbered=false not requiring a total, keyword many-to-many + duplicate-association rejection, image with/without variant, negative image dimensions, source record entity reference, and the three cascade-behavior tests)
- `tests/test_ready.py` — 3 passed

The 2 warnings are pre-existing Starlette/FastAPI test-client deprecation notices unrelated to this project's own code (same warnings seen in the Phase 1 report) — not an issue introduced by this phase.

## 14. Bugs Found and Fixed

1. **Redundant unique indexes in the hand-written migration** (§11) — caught during manual cross-check against the models, fixed before the migration was ever run.
2. **Model class named `Set`** would have shadowed Python's built-in `set` type throughout any code that later imports it (e.g. `from app.models import Set` sitting alongside ordinary `set()` calls). Renamed to `CardSet` early, before it could propagate into dependent files.

No bugs surfaced during the real PostgreSQL verification run (migration up/down/up, and 28/28 tests) — both issues above were caught by manual review before that point.

## 15. Deviations From the Specification, and Why

| Deviation | Reason |
|---|---|
| Added `app/models/mixins.py` (not in the original file list) | `id`, `created_at`, `updated_at` are identical across five of the six tables; centralizing them avoids the columns drifting out of sync across model files. Explicitly permitted by "You may improve this structure if there is a strong architectural reason." |
| Used SQLAlchemy's backend-agnostic `Uuid(as_uuid=True)` type rather than `sqlalchemy.dialects.postgresql.UUID` directly | Still compiles to Postgres's native `UUID` column type in production (satisfies "use PostgreSQL UUID types appropriately"), but also allows the exact same model code to be exercised against SQLite in isolated tests, per your own testing policy. |
| UUID primary keys are generated **application-side** (`default=uuid.uuid4`), not via a Postgres server-side default like `gen_random_uuid()` | Avoids requiring the `pgcrypto` or `uuid-ossp` Postgres extension to be enabled before migrations can run — one less manual setup step, with no functional downside for this use case. |
| `cards.set_id` uses `ON DELETE RESTRICT` (not specified in the brief) | See §10 — a deliberate, documented safety choice; open to revisiting if it proves inconvenient once the importer (Phase 8) exists. |
| `card_images.variant_id` uses `ON DELETE SET NULL` rather than cascading delete | The brief explicitly asked me to choose and document this — see §10. |
| Model class is named `CardSet`, not `Set` | Avoids shadowing Python's built-in `set` type across the codebase. The table name is still exactly `sets`, and the field name on `Card` is still `card.set` (matching the target API shape's `"set": {...}` key from the Phase 1 spec). |
| Migration was hand-written rather than produced by `alembic revision --autogenerate` | No live database was available in this environment to run autogenerate against in the first place (§12), and the brief itself says not to trust autogenerate blindly regardless. |

Nothing else deviates from the specification as written.

---

## 16. Final Project Tree

```
naruto-mythos-api/
├── .env.example
├── .gitignore
├── PHASE_1_REPORT.md
├── PHASE_2_REPORT.md
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
│   │       ├── health.py        (rewritten: pure liveness, no DB)
│   │       └── ready.py         (new: readiness check)
│   ├── models/
│   │   ├── __init__.py          (imports all 6 models)
│   │   ├── mixins.py            (new)
│   │   ├── set.py               (new: CardSet)
│   │   ├── card.py              (new: Card)
│   │   ├── variant.py           (new: CardVariant)
│   │   ├── keyword.py           (new: Keyword + card_keywords)
│   │   ├── image.py             (new: CardImage)
│   │   └── source.py            (new: SourceRecord)
│   ├── schemas/
│   │   ├── __init__.py
│   │   ├── health.py
│   │   └── ready.py             (new)
│   ├── services/
│   │   └── __init__.py
│   └── utils/
│       └── __init__.py
├── importer/
│   └── .gitkeep
├── data/
│   └── README.md
├── migrations/
│   ├── env.py                   (new)
│   ├── script.py.mako           (new)
│   └── versions/
│       └── 5f360cfd2561_initial_schema.py   (new)
└── tests/
    ├── __init__.py
    ├── conftest.py               (new)
    ├── test_health.py            (updated)
    ├── test_ready.py             (new)
    └── test_models.py            (new)
```

---

## 17. Security Review Checklist

- ✅ No credentials committed — `.env` remains git-ignored, only `.env.example` (placeholders) is tracked
- ✅ `DATABASE_URL` is never logged anywhere in the codebase
- ✅ `/ready`'s exception handler logs only a generic message (`"Readiness check failed: database is unreachable"`), never the exception object itself or its message
- ✅ No public write endpoints exist — `/health` and `/ready` are the only two endpoints, both `GET`, both read-only
- ✅ Internal UUIDs (`id` columns) are not exposed by `/health` or `/ready` — neither endpoint touches the ORM at all in its response body
- ✅ No copyrighted Naruto data, artwork, or logos were added — every test fixture uses obviously fictional identifiers (`TEST-SET-1`, `TEST-001`, `"Test Character Alpha"`, etc.)

---

## What's Explicitly Still Not Built

Per your instructions, none of the following exist yet: `/v1/cards`, `/v1/sets`, `/v1/rarities`, `/v1/keywords`, `/v1/search`, pagination/filtering/sorting logic, the importer, Docker, or Railway config.

**Waiting for your review before touching Phase 3.**
