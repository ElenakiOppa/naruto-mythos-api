# Phase 13C.2 — Collectible Printing Variant Normalization

**Status: implemented locally; PostgreSQL runtime migration validation remains blocked by Windows Application Control.** No public API contract, pricing, deployment, external acquisition, or production data was changed.

The complete row-level cross-tab of the 636 English source records is available at [phase13c2_identity_crosstab.csv](data/acquisition/analysis/phase13c2_identity_crosstab.csv). It includes raw Set, Edition, printed ID, Rarity, Variant, CardVersion, Stamp, Illustration, CardType, UID/SKU, serial-related raw fields, and the current seven-field Printing fingerprint. It contains 636 data rows plus a header; no title, rules text, or image URL is included.

## A. Raw Rarity Analysis

The canonical Card column below counts distinct `(Set, printed ID)` groups represented by that raw rarity. “Multi-row Cards” counts those groups that have additional source rows elsewhere in the same Set/ID group, including other rarity or Edition records.

| Raw Rarity | Rows | Set / Edition counts | Raw Variant values | Cards / multi-row Cards | Examples | Assessment |
|---|---:|---|---|---:|---|---|
| `C` | 165 | Konoha 1st 55, 2nd 55; Shinobi 1st 55 | Full Art 150, Holo 15 | 110 / 56 | `001/130`, `001/140` | Common rarity; treatment is separate. |
| `UC` | 151 | Konoha 1st 48, 2nd 48; Shinobi 1st 55 | Full Art 135, Holo 16 | 103 / 49 | `001/140`, `002/130` | Uncommon rarity; treatment is separate. |
| `R` | 84 | Konoha 1st 27, 2nd 27; Shinobi 1st 30 | blank 84 | 57 / 54 | `104/130`, `105/130` | Rare. |
| `RA` | 80 | Konoha 1st 27, 2nd 27; Shinobi 1st 26 | blank 80 | 53 / 53 | `104/130`, `105/130` | Rare ART; represented in raw Rarity, not Variant. |
| `S` | 30 | Konoha 1st 10, 2nd 10; Shinobi 1st 10 | blank 30 | 20 / 16 | `131/130`, `132/130` | Secret. |
| `SV` | 12 | Konoha 1st 4, 2nd 4; Shinobi 1st 4 | blank 12 | 12 / 12 | `131/130`, `133/130` | Secret Variant. |
| `L` | 7 | Konoha 1st 1, 2nd 2; Shinobi 1st 4 | blank 5, Gold 2 | 7 / 7 | `117/130`, `133/130` | Legendary. Serialization is not established by row fields. |
| `M` | 39 | Konoha 1st 4, 2nd 4, blank Edition 21; Shinobi 1st 10 | blank 38, Normale 1 | 32 / 24 | `005/140`, `104/130` | Mythos; both Edition-bound and editionless records exist. |
| `Mission` | 30 | Konoha 1st 10, 2nd 10; Shinobi 1st 10 | blank 30 | 20 / 10 | `MSS 01`, `MSS 02` | Collector class: every row also has `CardType=Mission`. |
| `CHIBI` | 13 | Shinobi 1st 13 | blank 13 | 13 / 13 | `078/140`, `111/140` | Special-print/class interpretation is ambiguous. |
| `SP` | 11 | Shinobi 1st 11 | blank 11 | 10 / 10 | `112/140`, `114/140` | Special-print/class interpretation is ambiguous. |
| `Shinobi` | 10 | Shinobi 1st 10 | blank 10 | 10 / 10 | `111/140`, `112/140` | Special-print/class interpretation is ambiguous. |
| `POP` | 4 | Shinobi 1st 4 | blank 4 | 4 / 4 | `123/140`, `126/140` | Special-print class; structured serial data is absent. |

The latter four values occur in the source’s Rarity field and share printed IDs with other rarity rows. That supports treating them as distinct Printing values, but does not establish whether each is a gameplay rarity, treatment, or collector class. They remain unresolved in normalized rarity/class fields and retain their raw values.

## B. Raw Variant Analysis

| Raw Variant | Rows | Set / Edition | Raw Rarity pairings | Cards / multi-row Cards | Examples | Assessment |
|---|---:|---|---|---:|---|---|
| blank | 317 | Konoha 1st 83, 2nd 82, editionless 21; Shinobi 1st 131 | `R` 84, `RA` 80, `S` 30, `SV` 12, `L` 5, `M` 38, `Mission` 30, `CHIBI` 13, `SP` 11, `Shinobi` 10, `POP` 4 | 106 / 81 | `104/130`, `131/130` | Unspecified, not Normal. |
| `Full Art` | 285 | Konoha 1st 103, 2nd 103; Shinobi 1st 79 | `C` 150, `UC` 135 | 182 / 105 | `001/130`, `001/140` | Direct treatment mapping to `FullArt`. |
| `Holo` | 31 | Shinobi 1st 31 | `C` 15, `UC` 16 | 31 / 0 | `079/140`, `080/140` | Direct treatment mapping to `Holographic`; all rows are Attachments. |
| `Gold` | 2 | Konoha 2nd 2 | `L` 2 | 2 / 2 | `117/130`, `136/130` | Direct Gold treatment. |
| `Normale` | 1 | Shinobi 1st 1 | `M` 1 | 1 / 1 | `005/140` | Unresolved; context below. |

The 31 `Holo` rows do not share a canonical Card with another source row in this snapshot. The cached Set 2 guide describes standard and holographic Attachment versions, consistent with the observed raw value. It does not establish missing Konoha holographic rows.

## C. Rarity × Variant Matrix

Counts below aggregate all Sets and Editions. The row-level CSV provides the complete Set/Edition/ID/CardVersion/Stamp/Illustration cross-tab.

| Raw Rarity | blank | Full Art | Holo | Gold | Normale |
|---|---:|---:|---:|---:|---:|
| `C` | 0 | 150 | 15 | 0 | 0 |
| `UC` | 0 | 135 | 16 | 0 | 0 |
| `R` | 84 | 0 | 0 | 0 | 0 |
| `RA` | 80 | 0 | 0 | 0 | 0 |
| `S` | 30 | 0 | 0 | 0 | 0 |
| `SV` | 12 | 0 | 0 | 0 | 0 |
| `L` | 5 | 0 | 0 | 2 | 0 |
| `M` | 38 | 0 | 0 | 0 | 1 |
| `Mission` | 30 | 0 | 0 | 0 | 0 |
| `CHIBI` | 13 | 0 | 0 | 0 | 0 |
| `SP` | 11 | 0 | 0 | 0 | 0 |
| `Shinobi` | 10 | 0 | 0 | 0 | 0 |
| `POP` | 4 | 0 | 0 | 0 | 0 |

`Illustration` is `Standard` on all 636 rows and currently distinguishes no Printing. `CardVersion` counts are Konoha 1st `V1=186`, Konoha 2nd `V1=187`, Konoha blank-Edition `V1=15/V2=6`, Shinobi 1st `V1=233/V2=9`. Stamp counts are blank 617, Regional Championship 7, Release Event 2, Store Championship 2, Weekly Tournaments 8. The cross-tab records the exact Set/Edition distribution for each value.

No raw source fields match serial, population, print-run, or total-related names; **0/636** rows carry a structured serial field. `serial_numbered` and `serial_total` in the application were model conveniences, not populated source evidence. New source-derived Printings leave both unset. The DB column is nullable for that unknown state; the current API continues to serialize its existing boolean shape.

## D. Konoha Shidō 1st Edition

| Measure | Source-derived value |
|---|---:|
| Printing rows | 186 |
| Canonical Cards (`Set`, printed ID) | 154 |
| Cards with multiple source rows in this Edition | 31 |
| Cards with one source row in this Edition | 123 |
| Rows with blank Variant | 83 |
| Canonical Cards represented by blank-Variant rows | 51 |
| Editionless Set 1 rows excluded | 21 |
| Distinct editionless printed IDs | 15 |
| Editionless IDs also present in 1st Edition | 15 |

**Rows by raw Rarity:** `C=55`, `UC=48`, `R=27`, `RA=27`, `S=10`, `SV=4`, `L=1`, `M=4`, `Mission=10`.

**Rows by raw Variant:** `Full Art=103`, blank `=83`; no `Holo`, `Gold`, `Normal`, or `Normale` rows occur in this Edition.

**Rarity × Variant:** `C/Full Art=55`, `UC/Full Art=48`, `R/blank=27`, `RA/blank=27`, `S/blank=10`, `SV/blank=4`, `L/blank=1`, `M/blank=4`, `Mission/blank=10`.

The Editionless 21 records are Mythos and stay excluded from these 186 rows; their 15 printed IDs overlap IDs in the 1st Edition, so they do not imply 15 extra canonical Cards.

## E. Comparison With the 396-Entry Collector Model

The external target is 396 entries; no row-level checklist file was present in the workspace. The source contributes **186** Konoha 1st Edition rows, a numerical difference of **210**. The source’s 55 Common and 48 Uncommon rows are all `Full Art`; it contains no explicit Normal or Holo rows for these 1st Edition categories. It does contain 31 Holo rows in the other Set, all on Attachments.

If the collector model expects all 55 Common and 48 Uncommon source IDs to each have Normal, FullArt, and Holographic entries, that would imply 206 Common/Uncommon rows beyond the 103 Full Art rows present. Under that conditional interpretation, the listed remaining source classes total 83, producing 392 rather than 396; the residual four cannot be explained without the checklist’s item-level data. The stated 396 total alone does not prove that every C/UC ID has all three treatments or identify those four entries. No missing Printing is fabricated.

## F. Missing and Ambiguous Classes

- **Common/Uncommon Normal:** no raw `Variant="Normal"` row; blank remains unspecified.
- **Common/Uncommon Holographic in Konoha 1st Edition:** not present there. Holo occurs only on 31 Shinobi Attachments.
- **Rare ART:** represented under raw `Rarity="RA"`. In Konoha 1st Edition, `104/130` appears once with `R` and once with `RA`; both remain Printings of the existing Set/ID Card. The source does not use `104A` for this pair.
- **Secret / Secret Variant:** represented under raw Rarity `S`/`SV`; for example `131/130` has one row of each. Both remain Printings of the same canonical Card.
- **Mythos:** 4 Konoha 1st Edition rows are Edition-bound; 21 other Set 1 Mythos rows have blank Edition and remain excluded from the Edition. Mythos is not synonymous with editionless.
- **CHIBI/SP/Shinobi/POP:** present as distinct raw Rarity values, often alongside other rarities for the same Set/ID, but their semantic axis is unresolved.
- **Normale:** one row, Shinobi 1st Edition `005/140`, `M`, `CardType=Character`, `CardVersion=V2`, Stamp `Regional Championship`, UID `864`, SKU `NM-S2E0-M005V2-RC`. Each locale feed repeats `Normale`; this is not an Italian-only translation leak. The row’s raw Edition says `1st edition` while its SKU contains `E0`, another reason not to reinterpret it as Normal. It remains unresolved.
- **Serialization:** no structured per-row serial evidence or total; do not infer serial status or counts from rarity, Stamp, or SKU.

## G. Normalized Taxonomy

The implementation separates normalized dimensions while retaining the existing raw columns:

| Raw field | Normalized field | Reviewed mapping |
|---|---|---|
| `Rarity` | `normalized_rarity` | `C→Common`, `UC→Uncommon`, `R→Rare`, `RA→Rare ART`, `S→Secret`, `SV→Secret Variant`, `L→Legendary`, `M→Mythos` |
| `Rarity=Mission` plus `CardType=Mission` | `collector_class` | `Mission`; mismatched CardType stays unresolved |
| `Variant` | `normalized_treatment` | exact `Normal→Normal`, `Full Art→FullArt`, `Holo→Holographic`, `Gold→Gold` |
| blank `Variant` | `normalized_treatment` | null with status `UNSPECIFIED`; never Normal |
| `Normale` and unknown values | normalized field | null with status `UNRESOLVED`; raw value retained |

Exact canonical labels are accepted as inputs so repeated normalization is idempotent. No fuzzy matching or inference from rarity is used. `CHIBI`, `SP`, `Shinobi`, and `POP` stay unresolved in normalized rarity/class fields.

## H. Schema Changes

Added nullable `normalized_rarity`, `collector_class`, and `normalized_treatment`, plus `rarity_resolution_status` and `variant_resolution_status`. The old `rarity_override`, `source_variant`, `variant_type`, `finish`, `Edition`, Card identity, and Printing identity columns remain. The taxonomy fields do not participate in the unique Printing index. `serial_numbered` is nullable internally so source absence is distinct from a measured false; the public response remains Boolean via a compatibility validator.

## I. Importer Changes

The read-only source plan computes supplemental taxonomy and candidate normalized Printing identity. Unknown values use explicit unresolved tokens for collision checking; blank Variant has a distinct unspecified token. A collision aborts planning. Persistence writes normalized fields and null serial values beside unchanged raw identity fields and provenance. The generic normalized importer writes the same taxonomy fields and stores the original input type in `source_variant` before applying its existing alias to `variant_type`.

## J. Identity Safety Analysis

- Current seven-field fingerprints: **636 unique / 0 duplicate groups**.
- Candidate Edition/taxonomy-normalized identities: **636 unique / 0 collision groups**.
- The current Edition labels were already canonical: 428 `1st edition`, 187 `2nd edition`, 21 blank; normalization changed **0** values.
- All 636 legacy Printing public IDs computed from the old raw Edition component equal the new normalized-Edition IDs.
- Canonical grouping still has 318 `(Set, printed ID)` keys and zero title/CardType conflicts.

Rarity/treatment normalizations are supplemental. The existing seven fingerprint components and unique index remain; their raw rarity, raw variant, CardVersion, and Stamp are retained. Canonical Card identity is unchanged.

## K. Migration Behavior

Added revision `e13c20260926_printing_taxonomy`, following `d13c20260926`. It adds the five normalized/status columns, backfills exact supported values from `rarity_override`, `source_variant`, and CardType, and marks all other values unresolved/unspecified. It preserves raw values and does not alter the Printing unique index. It relaxes internal `serial_numbered` nullability without rewriting existing booleans. Downgrade refuses when normalized taxonomy values, non-default resolution statuses, or null serialization evidence would be lost.

The full Alembic chain compiles in offline PostgreSQL mode. Runtime migration execution was not validated.

## L. Tests Passed

- Full pytest: 778 passed.
- Focused taxonomy/importer/model/API set: 266 passed.
- Ruff repository check: passed.
- Ruff formatter check for changed Python files: passed.
- Mypy `app importer scripts`: 0 issues in 94 source files.
- Pylance diagnostics on implementation files: no errors.
- Guarded local dry-run and source-drift plan guard: passed; 318 Cards, 636 Printings, 3 Editions, zero normalized collisions.
- Offline Alembic SQL compilation: passed.
- `git diff --check`: passed.

## M. Tests Blocked / Not Run

Six PostgreSQL-backed tests in `tests/test_domain_schema.py` error before assertions because Windows Application Control blocks PostgreSQL `initdb.exe` (`WinError 4551`). The new migration was not run against PostgreSQL; offline SQL compilation is not runtime validation. No live acquisition, import, database access, production data, or deployment was performed.

## N. Final Canonical Card Count

**318 canonical Cards** in the local source-derived plan; the `(Set, printed ID)` identity rule is unchanged.

## O. Final Source-Derived Printing Count

**636 Printings**, one per accepted English source row/UID in the local plan. All four locale observations remain localizations/provenance, not extra Printings.

## P. Remaining Data Gaps

- The collector’s 396-entry checklist was not available row-by-row, so the residual four-entry difference under the conditional C/UC triple-treatment calculation cannot be reconciled.
- Konoha 1st Edition Normal and Holographic C/UC rows are absent from the source snapshot; do not synthesize them.
- Blank Variant and `Normale` remain distinct unresolved states.
- CHIBI/SP/Shinobi/POP need source-owner taxonomy clarification.
- The source has no serial field; serialized status and totals remain unknown.
- Raw ID `104/130` and `RA` distinguish Rare Art in source, while the external `104A` style is not present in this feed; any canonical ID remapping needs separate reviewed evidence.
