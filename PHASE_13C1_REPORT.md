# Phase 13C.1 — Edition Domain Foundation

**Status: implemented locally; PostgreSQL runtime migration validation is blocked by host policy.**

This phase adds the Edition domain foundation only. It does not change the public API contract, implement pricing, acquire source data, run an import, access a database, deploy, or touch production data.

## Architecture

The canonical hierarchy remains `CardSet → Card`. Editions are scoped to a Set and Printings link to both an Edition and their existing canonical Card:

```text
CardSet
  ├── Cards
  └── Editions
       └── Printings
            └── Card
```

Edition is not part of canonical Card identity. Cards remain grouped by `(Set, printed identifier)`. Printing public IDs continue to use the existing fingerprint; the added Edition identifier does not enter that fingerprint.

## Schema Changes

- Added `Edition` in `app/models/edition.py` with UUID primary key, unique public ID, `set_id`, source-facing `name`, `normalized_name`, and timestamps.
- Edition identity is unique by `(set_id, normalized_name)`. The same label can therefore exist in different Sets.
- `edition_number` and a status field were omitted. The current source establishes labels but provides no independent edition metadata or status vocabulary; a Printing with no known Edition remains `edition_id = NULL`.
- `CardVariant` retains its transitional nullable `edition` text and gains nullable `edition_id` plus a Set owner key. Its new `edition_record` relationship avoids colliding with the existing text attribute.
- Composite foreign keys enforce both `Printing.card_id` and `Printing.set_id` against the owning Card, and `Printing.edition_id` and `Printing.set_id` against the owning Edition. The ORM fills the redundant Set key for existing `CardVariant(card_id=...)` insert call sites.
- PostgreSQL also checks that `normalized_name` matches the Edition label after normalization. The public API response models are unchanged.

## Normalization and Identity

Edition normalization is deliberately narrow: NFC normalization, trimming/collapsing whitespace, and lowercase comparison. Thus `1st edition` and `1st Edition` resolve to the same Edition within a Set. There is no fuzzy ordinal parsing or aliasing. Known first/second labels display as `1st Edition` and `2nd Edition`; other labels retain cleaned source spelling.

Edition public IDs are deterministic and Set-scoped, using a length-prefixed Set public ID plus normalized label and PostgreSQL-compatible MD5. They are opaque identifiers, not security tokens. Migration backfill and importer planning use the same derivation.

The existing Printing fingerprint and generated Printing public IDs are unchanged. The PostgreSQL semantic unique index now uses `edition_id` instead of normalized Edition text, while retaining the existing rarity, source variant, card version, and stamp dimensions. The importer detects a collision created by Edition normalization and aborts rather than merging records or changing their IDs.

## Migration

Revision `d13c20260926` follows `c13c20260916`. It:

1. Creates `editions` with Set-scoped normalized uniqueness and supporting indexes.
2. Adds nullable `card_variants.edition_id` and a backfilled `card_variants.set_id`.
3. Creates Edition rows only from nonblank existing Printing edition text, scoped to each Card’s Set.
4. Links those Printings; blank/whitespace-only values remain unassigned (`NULL`).
5. Checks that nonblank values resolved and that normalized Edition identity introduces no semantic Printing collisions; conflicts abort the transaction.
6. Adds composite same-Set foreign keys and rebuilds the semantic unique index using `edition_id`.
7. Leaves the old Printing edition text, all Card rows, and all existing Card/Printing public IDs untouched.

Downgrade refuses when Edition rows or linked Printings exist rather than discarding Edition identities. The complete Alembic chain compiles to PostgreSQL SQL in offline mode. Runtime upgrade/downgrade execution was not possible: the six PostgreSQL-backed tests fail before Alembic execution when Windows Application Control blocks PostgreSQL 18 `initdb` (`WinError 4551`). Offline compilation is not reported as a runtime migration pass.

## Importer Changes

- The local acquired-snapshot planner derives Edition records from the English reference observations only, keyed by Set and normalized Edition label.
- It stores `edition_public_id` on each Printing plan row. Blank source Edition stays null; localized Edition text remains in the translation/provenance observations.
- Language, source UID/SKU, and variant/treatment do not enter Edition identity.
- The dedicated transactional persistence helper resolves/creates Edition rows by `(set_id, normalized_name)` and links Printings while retaining raw Printing edition text.
- The normalized legacy importer also plans and writes Editions from explicit variant Edition values; it includes the Printing owner Set key and refuses in-place Edition reassignment.
- No importer command was run against a database or external source.

## Derived Inventory and Identity Counts

The read-only local snapshot plan reports:

| Set | Derived Editions | Canonical Cards | Printings |
|---|---:|---:|---:|
| Konoha Shidō | 2 | 158 | 394 |
| Shinobi Shiren | 1 | 160 | 242 |
| **Total** | **3** | **318** | **636** |

These Edition counts are derived from the acquired rows, not populated from a presumed future catalogue. Source Edition distribution remains 428 `1st edition`, 187 `2nd edition`, and 21 blank. All 21 blank records retain no Edition assignment. No Shinobi Shiren 2nd Edition rows were invented. The dry-run reports 636 accepted Printings, zero collisions, zero rejected rows, and plan SHA-256 `8006177e6e7299cc0a0195b77d243bcf2d9d6a4f88b79f07a3632e0bd77a09a2`.

The 318/636 figures are plan results. No database was queried, so this report does not claim deployed or persisted row counts.

## Validation Results

**Executed and passed**

- Full test suite: 748 passed.
- Focused Edition/importer/command regression set: 78 passed.
- Ruff check across the repository: passed.
- Ruff format check for all changed Python files: passed.
- Mypy `app importer scripts`: passed, 0 issues in 92 files.
- Pylance diagnostics on changed implementation files: no errors.
- Local-only `python -m importer.catalogue_importer`: 318 Cards, 636 Printings, 3 Editions, zero identity collisions.
- `alembic upgrade head --sql`: full PostgreSQL migration chain compiled successfully offline.
- `git diff --check`: passed.

**Blocked or not executed**

- Six PostgreSQL-backed tests in `tests/test_domain_schema.py` error before test assertions because Application Control blocks `initdb.exe`. The new migration has not been executed against PostgreSQL, so runtime upgrade, backfill, constraints, and downgrade remain unverified.
- No database import, live source acquisition, API deployment, Railway operation, or production access was performed.

## Unresolved Data Issues

- The 21 blank Edition records remain null; the importer does not infer an Edition for them.
- The snapshot has no verified Shinobi Shiren 2nd Edition.
- Source rarity/treatment labels are not a fully normalized taxonomy; values such as `CHIBI`, `SP`, `Shinobi`, `POP`, `Mission`, and the anomalous `Normale` still need reviewed mappings.
- Structured run sizes and per-copy serial numbers are not available in the acquired record set. They are not inferred or implemented here.
- A future source change that causes Edition normalization to collide with an existing Printing identity is rejected for review; no automatic Printing merge or public-ID rewrite is allowed.
