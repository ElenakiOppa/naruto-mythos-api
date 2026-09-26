# Phase 13C.3 — Konoha Shidō 1st Edition Collector Catalogue

**Status: implemented and locally validated.** No live database import, production data access, deployment, Railway operation, or push occurred. The workbook was inspected read-only and remains unchanged.

## A. Workbook Structure

Input: `data/reference/konoha_shido_1st_edition_master.xlsx`
Workbook SHA-256: `f35825e0e2f1910562fe345703752c3b8b4e2c5187a957ab94e379a7bf233f78`

Sheets: `Checklist`, `Dashboard`.

`Checklist` has a title row at row 1, headers at row 2, and collectible entries in rows 3–398. Headers were found by name rather than column position:

`Owned`, `No.`, `Card`, `Rarity`, `Variant`, `Qty`, `Low Value (€)`, `Median Value (€)`, `High Value (€)`, `Total Low (€)`, `Total Median (€)`, `Total High (€)`.

The sheet has 396 nonempty collectible data rows, all 396 with `No.`, `Card`, `Rarity`, and `Variant` populated. The exact identity tuple has 396 unique values. The sheet also contains calculated total formulas; those are not imported. `Dashboard` has 23 nonempty rows and a displayed “Total collectible entries” metric of 396; the entry count was independently computed from the Checklist rows, not taken from the dashboard.

## B. Verified Checklist Count

**396 collectible entries.** The generator enforces the exact count and fails if it changes. The original workbook is retained as input; it was not edited.

## C. Reconciliation Algorithm

1. Read the generated JSON artifact, whose identity fields are raw collector number, card label, rarity, and Variant. Workbook row position is stored only for audit navigation, never used as identity.
2. Resolve each entry to an existing Set 1 canonical Card using the printed number namespace and primary card name. Missions resolve only against `CardType=Mission` and `MSS NN`; Rare ART `104A`–`130A` resolves to the same-number base Card only when the workbook rarity is Rare ART and source name evidence agrees.
3. The workbook’s `n/2000` Legendary label maps to the unique Set 1 Legendary Naruto Card by primary name and rarity. `n/2000` remains unchanged in reference provenance and is not interpreted as a serial number or total.
4. Within Konoha Shidō 1st Edition, a unique same-Card, same-rarity upstream Printing with the same explicit treatment is reused. If the upstream Variant is unspecified and there is only one same-rarity Printing, the checklist confirms it and a curated reference is attached. Otherwise one deterministic curated Printing is planned.
5. Duplicate canonical/Edition/rarity/treatment/collector-number identities, ambiguous matches, or a required new canonical Card abort reconciliation.

The reconciliation is read-only. Persistence is a separate transaction-taking function.

## D. Direct Matches

**184 workbook entries reuse existing upstream Printings.**

- 101 match the source’s explicit rarity and treatment.
- 83 attach curated confirmation to a same-rarity upstream Printing whose raw Variant is blank. This does not rewrite the raw source Variant.
- Each upstream UID is matched at most once.

## E. New Curated-Reference Printings

**212 new Printing rows are planned**, all under existing canonical Cards and Konoha Shidō 1st Edition:

- Common: 111
- Uncommon: 97
- Mythos: 4

By workbook treatment: Normal 103, Holographic 103, FullArt 2, Holographic / Micro-engraved 4. The two FullArt additions correspond to source records at `063/130` and `075/130` whose source Rarity conflicts with the workbook Rarity; those source Printings are retained separately below.

Curated Printings use a deterministic `prc_` public ID and `reference_identity`. They have no fabricated source UID/SKU, images, translations, prices, gameplay fields, serial values, or upstream SourceRecord.

## F. Source-Only Printings

Two Konoha Shidō 1st Edition upstream Printings are not represented by the workbook identity:

| Source UID | Source ID | Upstream Rarity / Variant | Checklist discrepancy |
|---:|---|---|---|
| 266 | `063/130` | UC / Full Art | Workbook says Common / FullArt. |
| 278 | `075/130` | C / Full Art | Workbook says Uncommon / FullArt. |

They remain upstream-only and unchanged. They are not merged into the conflicting checklist entries.

## G. Ambiguities and Conflicts

- Unresolved ambiguous Card matches: **0**.
- Unresolved ambiguous Printing matches: **0**.
- Duplicate checklist identities: **0**.
- Rarity conflicts: **2**, the source-only rows listed in section F.
- Source/workbook display-description differences: **83**. Primary card names and number-based canonical mappings agree; some workbook display suffixes differ from the source `Version` description. These labels remain separately preserved and do not overwrite canonical Card names.
- `104A`–`130A` map to the existing base-number Card where the same Rare ART name/rarity evidence agrees; the suffix is retained as the workbook collector number. No new Card IDs are made for the suffix.
- `n/2000` has a unique existing Card candidate, `133/130`, based on Naruto primary name plus the unique Legendary row. The workbook descriptor (“The greatest Hokage!”) differs from upstream Version (“I’ll be the greatest Hokage”); both strings are preserved. No serial total is populated.

## H. Final Konoha 1st Edition Collector Count

**396 exactly once each:** 184 references attach to existing upstream Printings and 212 attach to new curated-reference Printings. The internal collector-reference view consists of the 396 `PrintingReference` records and contains no duplicate reference keys or collectible identities.

## I. Provenance Design

Added `PrintingReference`, a separate relationship keyed by `(source_name, reference_key)`. It stores workbook SHA, worksheet/row, raw collector number, card label, raw rarity/Variant, and normalized collector taxonomy. A reference links to its Printing; it never creates a `SourceRecord`.

Printing origin is derived from provenance relationships:

| Origin | Distinct Printing rows |
|---|---:|
| `UPSTREAM` only | 452 |
| `UPSTREAM_AND_CURATED` | 184 |
| `CURATED_REFERENCE` only | 212 |

No curated entry is relabeled as an upstream record.

## J. Schema and Migration Changes

Added nullable `card_variants.reference_identity`, appended to the semantic unique index so distinct curated identities can coexist without changing existing upstream identities. Added `printing_references` with Printing FK, deterministic source/reference uniqueness, raw and normalized collector fields, workbook hash, and row provenance. The database/API public response contract was not changed.

Migration `f13c20260926_printing_references` follows `e13c20260926`. It preserves existing Cards, Printings, Edition IDs, and provenance. Downgrade refuses when references or curated identity discriminators exist. PostgreSQL offline SQL compilation passed; runtime migration execution was blocked by the local `initdb` policy.

## K. Canonical Card Count

**318**, unchanged. The workbook maps to 158 distinct Konoha Shidō canonical Card identities; those all resolve to existing Set 1 `(Set, printed ID)` Cards, including IDs already represented in another Edition. No 319th Card was created.

## L. Upstream Printing Count

**636**, unchanged in the source-only dry-run. No upstream rows were deleted or rewritten.

## M. Total Collectible Printing Counts

| Measure | Count | Meaning |
|---|---:|---|
| Canonical Cards | 318 | Existing Card identities. |
| Upstream Printings | 636 | Source-derived rows across both Sets. |
| Curated reference entries | 396 | Checklist observations, including overlap. |
| Curated-reference-only Printings | 212 | New collectible Printing rows required by the checklist. |
| Upstream/checklist overlap | 184 | Existing Printings confirmed by checklist references. |
| Total distinct Printing rows | 848 | 636 upstream plus 212 curated-only. |
| Konoha 1st Edition collector view | 396 | Exactly the supplied checklist identities. |

These are planned/persistence-test counts. No application database was modified.

## N. Tests and Validation

**Passed:**

- Full pytest: 783 passed.
- Focused catalogue/importer/reference/API tests: 224 passed.
- Ruff repository check: passed.
- Ruff format check: passed.
- Mypy `app importer scripts`: 0 issues in 99 source files.
- Pylance diagnostics on changed implementation files: no errors.
- Workbook converter `--check`: passed, 396 entries and matching source hash.
- Reconciliation CLI: passed; 318/636 baseline, 396 references, 184 overlap, 212 curated-only, two source-only, zero ambiguity.
- Source-only dry-run: 318 Cards, 636 Printings, zero identity collisions.
- SQLite persistence/idempotency fixture: 318 Cards, 636 upstream Printings retained, 396 references, 212 curated-only Printings, 848 total.
- Offline Alembic compilation through `f13c20260926`: passed.
- `git diff --check`: passed.

**Blocked:** six PostgreSQL-backed tests in `tests/test_domain_schema.py` fail during `initdb.exe` startup with Windows Application Control `WinError 4551`, before Alembic/test assertions. No PostgreSQL runtime migration pass is claimed.

## O. Remaining Data Gaps

- The two checklist/source Rarity disagreements remain intentionally separate; an authoritative correction is still needed.
- The 83 display-description differences are preserved in reference provenance; they are not used to rename canonical Cards.
- `n/2000` remains a literal collector label; no serial number or population is derived from it.
- Workbook Variant strings such as `Special Numbered /75` are retained as collector terminology only; `serial_numbered` and `serial_total` remain unset absent a structured serial field.
- Workbook-owned quantities/prices/formulas are excluded from the generated artifact and not imported.
- Public API presentation of Printing origin and reference-backed collector data is deferred to Phase 13C.4.

## P. Recommendation for Phase 13C.4

Design the public Printing/collector view to expose the 396 Edition-scoped identities exactly once, with provenance-derived origin (`UPSTREAM`, `CURATED_REFERENCE`, or `UPSTREAM_AND_CURATED`). Keep source-only upstream rows queryable and expose the two Rarity conflicts transparently. Do not change canonical Card identities or infer prices, serial totals, or images.
