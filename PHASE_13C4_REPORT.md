# Phase 13C.4 — Public Collector Catalogue API

**Status: implemented and locally validated.** This phase exposes the Edition and Printing model created in Phase 13C.3. It does not change catalogue source data or add a migration. No production database, deployment, push, pricing, image acquisition, or serial-number inference was performed.

## A. Compatibility Contract

- `/v1/cards` remains the canonical Card collection and preserves its existing filtering and pagination contract.
- Card detail retains the legacy `variants` field and adds the clearer `printings` projection; neither representation changes the Card identity model.
- Legacy `/v1/rarities` remains a Card-rarity catalog. Printing-level rarity counts are available separately from `/v1/printing-rarities`.
- New response fields and routes are additive. Set summary payloads remain unchanged; Set detail/list responses add the requested catalog counts and Edition summaries.

## B. Public Routes

- `GET /v1/sets/{set_id}/editions` lists Editions for a Set.
- `GET /v1/editions/{edition_id}` returns Edition detail and collector-reference status/counts.
- `GET /v1/editions/{edition_id}/printings` returns the verified collector-reference view for an Edition.
- `GET /v1/printings` lists persisted Printing rows with filters and pagination.
- `GET /v1/printings/{printing_id}` returns Printing detail.
- `GET /v1/printing-rarities` returns Printing-level rarity counts.

The general Printing endpoint includes source-only rows. The Edition collector endpoint is restricted to persisted `PrintingReference` identities and reports `COLLECTOR_REFERENCE_NOT_FOUND` for Editions without a verified collector reference.

## C. Origins and Collector Semantics

Printing origin is derived from existing relationships, not a mutable origin flag:

- `UPSTREAM`: SourceRecord provenance only.
- `UPSTREAM_AND_CURATED`: both SourceRecord and PrintingReference provenance.
- `CURATED_REFERENCE`: PrintingReference provenance only.

Rows without typed provenance use the `UPSTREAM` compatibility fallback for legacy records. Source-only Printings remain queryable in the general endpoint and are excluded from the verified collector view.

## D. Filters and Card Semantics

The Printing list supports Set, Edition, normalized rarity, treatment, collector class, Card, and origin filters. Card list rarity/treatment/Edition filters evaluate related Printings while returning distinct canonical Cards, preventing duplicate Cards when multiple Printings match.

## E. Counts and Reconciliation

The counts below reflect the Phase 13C.3 source/reference reconciliation and the API's distinct views:

| Measure | Count | Meaning |
|---|---:|---|
| Canonical Cards | 318 | Existing canonical Card identities. |
| Upstream Printings | 636 | Source-derived Printing rows. |
| Curated reference entries | 396 | Konoha Shidō 1st Edition checklist identities. |
| Upstream/reference overlap | 184 | Existing upstream Printings confirmed by the checklist. |
| Curated-reference-only Printings | 212 | Additional Printing rows represented by the checklist. |
| Total persisted collectible Printings | 848 | 636 upstream plus 212 curated-reference-only rows. |
| Konoha Shidō 1st Edition collector view | 396 | Exactly the verified checklist identities. |

The Konoha Shidō Set has 158 canonical Cards and 606 Set-level collectible Printings (394 upstream Set rows plus 212 curated-only rows). Its verified 1st Edition collector view has 396 references; the general 1st Edition query has 398 rows because it also includes two source-only Printings. Set 2's existing Edition status remains `NONE`.

## F. Set and Edition Status

Set detail/list responses expose `canonical_card_count`, `collectible_printing_count`, and Edition summaries. Edition responses expose verified collector status and reference count. Set-level Printing totals count persisted Printing rows; Edition collector totals count reference identities, so overlap is not double-counted in the collector view.

## G. Source-Only Discrepancies

The two source-only Konoha 1st Edition rows, `063/130` and `075/130`, remain unchanged and visible through the general Printing API. They are excluded from the 396-entry collector-reference view because their upstream Rarity conflicts with the checklist. No source record was overwritten or merged to conceal the discrepancy.

## H. Images, Prices, and Serials

The API exposes only image references already attached to a Printing. No image was created or acquired. Pricing is not implemented. Collector strings such as `n/2000` remain literal reference values and do not populate serial number or serial total fields. No missing gameplay or source fields were fabricated.

## I. Schema and Migration Impact

No Phase 13C.4 migration was added. Existing Phase 13C.3 Edition and PrintingReference relationships already support these read paths. Public schemas were added for Edition, Printing, pagination metadata, and Printing rarity responses; existing Card/Set schemas were extended additively where required.

## J. OpenAPI and RapidAPI Export

The RapidAPI export allowlist now includes the six additive routes. The generated `docs/generated/openapi.rapidapi.json` is OpenAPI 3.0.2 and validates with **18 unique GET operations**. The canonical FastAPI OpenAPI document and exporter remain deterministic; no secret or write route is exposed.

## K. Tests and Validation

- Focused collector/Card/Set/OpenAPI/RapidAPI suite: **209 passed**.
- Full non-PostgreSQL suite: **789 passed**, 3 dependency deprecation warnings.
- Ruff lint: passed.
- Ruff format check: passed, 138 Python files formatted.
- Mypy `app importer scripts`: passed, 0 issues in 105 source files.
- RapidAPI OpenAPI export and validation: passed.
- Offline Alembic SQL compilation through existing head `f13c20260926`: passed; no C4 migration was generated.
- `git diff --check`: passed (Git reports only existing LF-to-CRLF working-copy notices).

The six PostgreSQL-backed migration tests in `tests/test_domain_schema.py` were excluded from the final non-PostgreSQL run. Local disposable PostgreSQL initialization is blocked by Windows Application Control (`initdb`/`WinError 4551`), as recorded in the preceding phase report; this phase makes no claim of a new local PostgreSQL runtime migration pass.

## L. Local Data and Safety

No application database was modified and no catalogue import was run against a database. The existing source-only dry-run and reconciliation results remain: 318 Cards, 636 upstream Printings, 396 references, 184 overlaps, 212 curated-only Printings, two source-only rows, and zero ambiguities. No deployment, push, or pricing work was performed.

## M. Handoff

Phase 13C.4 delivers additive public Edition/Printing APIs while preserving canonical Cards and legacy variants. The API distinguishes the broad persisted Printing inventory from the verified Edition collector view, derives origins from provenance, and documents the two known source-only discrepancies. Changes are local and are committed as `Phase 13C.4: expose collector catalogue API`; they have not been pushed or deployed.
