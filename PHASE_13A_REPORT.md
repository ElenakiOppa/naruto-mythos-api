# Phase 13A — Real Naruto Mythos source acquisition & raw data audit

Status: LOCAL ACQUISITION COMPLETE — read-only discovery and audit only. Not committed. Phase 13B not started.

Recommendation: **CONDITIONAL GO** for Phase 13B (production-quality parser/normalizer design), conditioned on the model extensions and open questions in sections 24/27/28 being resolved by a human reviewer before any schema or importer change is made.

## 1. Executive summary

This phase acquired real, official, public Naruto Mythos TCG catalogue data for the first time in the project, strictly as read-only discovery. It did **not** touch the production database, did not download artwork, and did not change the public API.

Ten distinct official documents/pages plus four API responses were retrieved (14 fetch attempts, 12 distinct content hashes — two `lang=it`/`lang=en` API responses were byte-identical). Beyond the six HTML pages named in the brief, the acquisition also discovered and called a first-party, unauthenticated, same-domain JSON API (`https://cards.narutotcgmythos.com/api/cards`) that the public Card Gallery page itself calls client-side. That API returned **636 real card print-records** across Set 1 and Set 2, with full field-level detail (rarity, card type, edition, variant, SKU, keywords, chakra/power, text, etc.). This is dramatically richer ground truth than the HTML pages alone would have provided, and it directly falsifies several assumptions the current importer/staging model makes (see section 24).

Key findings: the Card Gallery is **not** currently under maintenance (contrary to the brief's premise); real printed identifiers collide heavily (185 of 318 unique printed numbers map to more than one distinct catalogue record); Set 2's marketing "140-card set" figure does not match the raw catalogue count (242 records); Italian localization is not actually distinct from English in the live data; and the existing `Card(set_id, card_number)` uniqueness constraint would reject a naive direct import of the real numbering scheme.

## 2. Baseline

- Branch: `main`. Working tree: clean. HEAD: `9f20e0539175e7857d56ef488d7cc768e59eed62` — matches the expected starting HEAD exactly.
- Phase 12B, 12C and 12D reports and packages are present in the repository.
- Pre-existing baseline test suite: **626 passed**, 0 failed (before any Phase 13A file was added).
- Ruff check, Ruff format check and Mypy (`app importer`) all passed on baseline.
- Railway Auto Deploy is recorded as intentionally OFF per owner-confirmed project state; Railway was not queried. Production PostgreSQL was not queried. `.env` was not read.

## 3. Acquisition methodology

New read-only tooling was added under `scripts/acquisition/` (no new dependency — stdlib `urllib` only):

- `fetch.py` — enforces a host allowlist (`narutotcgmythos.com`, `www.narutotcgmythos.com`, `cards.narutotcgmythos.com`, `irp.cdn-website.com`) on both the initial request and every redirect hop; 15s timeout; 25MB body ceiling; ~1 request/second rate limiting; retries only safe transient 5xx failures (max 2); optional MIME-type validation; SHA-256 of every response body.
- `storage.py` — content-addressed, immutable raw storage (`data/acquisition/raw/<sha256>.<ext>`, never overwritten) and an append-only `manifest.json`.
- `sources.py` — the approved source inventory (pages, PDF documents, API endpoints).
- `run_acquisition.py` — CLI that fetches every approved source and writes manifest + small observation records.
- `analyze_cards.py` — read-only statistical counting over the acquired API JSON (no normalization, no identity generation).
- `tests/test_acquisition.py` — 16 tests against a local HTTP server (no live-site dependency): allowlist rejection, redirect-outside-allowlist rejection, timeout, size limit, MIME mismatch, deterministic hashing, immutable storage, append-only manifest, manifest validation, and structural checks that no artwork URLs or identity/normalization helpers exist in this tooling.

Raw bytes are stored under `data/acquisition/raw/` which is now `.gitignore`d (copyrighted third-party documents/pages stay local, never committed). `manifest.json`, `observations/*.json` and `card_data_audit.json` contain only metadata/counts and are safe to track (nothing was committed this phase regardless).

## 4. Rights/access boundary

- `https://www.narutotcgmythos.com/robots.txt` was checked: `User-agent: *` with no `Disallow` rules and `Content-Signal: search=yes, ai-input=yes, ai-train=yes`. No automated-acquisition restriction was found.
- No authentication, paywall, or anti-bot control was encountered or bypassed.
- No card artwork was downloaded; image URLs appearing in HTML/API responses were recorded as text references only.
- The four collection-guide/rulebook PDFs are official documents the site itself offers as public downloads (`/collection-guide` page, "DOWNLOAD THE COLLECTION GUIDE" section). They were retrieved and hashed but kept untracked locally, per the phase's copyright-caution guidance.

## 5. Official source inventory

| # | URL | Type | Status | Content-Type | Bytes | SHA-256 |
|---|---|---|---|---|---|---|
| 1 | `/` | HTML_PAGE | 200 | text/html | 456,060 | `0b14f073…bb90e` |
| 2 | `/collection-guide` | HTML_PAGE | 200 | text/html | 282,076 | `0737e6a8…388499` |
| 3 | `/card-gallery` | HTML_PAGE | 200 | text/html | 212,808 | `86302e52…003566` |
| 4 | `/set-1-konoha-shido` | HTML_PAGE | 200 | text/html | 241,468 | `0e4191a1…711a7f442` |
| 5 | `/set-2--shinobi-shiren` | HTML_PAGE | 200 | text/html | 225,748 | `99f6d763…ce3c271f` |
| 6 | `/products` | HTML_PAGE | 200 | text/html | 305,557 | `4a63a3be…9cac41ad` |
| 7 | Collection guide Set 1, 1st ed. (PDF) | PDF_GUIDE | 200 | application/pdf | 3,549,092 | `1d58f134…6754c54178` |
| 8 | Collection guide Set 1, 2nd ed. (PDF) | PDF_GUIDE | 200 | application/pdf | 4,078,223 | `203c1291…8134b1549bd` |
| 9 | Collection guide Set 2, 1st ed. (PDF) | PDF_GUIDE | 200 | application/pdf | 8,166,876 | `f0cf8aac…3ef672261a8a` |
| 10 | Rulebook (PDF) | PDF_GUIDE | 200 | application/pdf | 5,014,702 | `1a6ac889…8ef622100d307` |
| 11 | `cards.narutotcgmythos.com/api/cards?lang=en` | API_RESPONSE | 200 | application/json | 411,351 est. | `83f73c06…0745f1fd85` |
| 12 | same, `lang=fr` | API_RESPONSE | 200 | application/json | — | `c7e60efa…97ffc3a3d` |
| 13 | same, `lang=it` | API_RESPONSE | 200 | application/json | — | `83f73c06…0745f1fd85` (**identical to #11**) |
| 14 | same, `lang=es` | API_RESPONSE | 200 | application/json | — | `c6d72561…ddbaae068` |

All retrievals succeeded (HTTP 200); nothing was blocked by robots/access controls. Full metadata is in `data/acquisition/manifest.json`; raw bytes are in `data/acquisition/raw/` (untracked).

## 6. Website implementation findings

The public pages are **not** simple static catalogues: the Card Gallery page ships un-minified, Italian-commented client-side JavaScript (readable directly in the fetched HTML) that:

- Declares a direct, same-domain, unauthenticated JSON API: `https://cards.narutotcgmythos.com/api/cards?lang={en|fr|it|es}` (confirmed live by a single on-allowlist GET request — see section 21 for the exact evidence).
- Normally routes through a **third-party proxy** (`https://services.agenziamarketingcarpi.it/proxy/naruto/proxy.php`) whose documented purpose (per the page's own code comments) is to hide the backend domain and add CORS headers for the browser — not to add authentication. The proxy domain is **not** on `narutotcgmythos.com` and was **not** added to the acquisition allowlist or queried; only the first-party direct API on the official subdomain was used.
- Response shape: `[{"Title": "...", "Cards": [ {…card fields…}, … ]}]`.
- The front-end merges the four per-language responses client-side using a `Uid` field as the true unique key (documented in a code comment as necessary because the same printed number can have multiple distinct prints across rarity/edition).

This is a first-party, naturally-exposed mechanism (the exact request the public gallery page makes on load), not a private/internal endpoint, and it was reached without bypassing any restriction.

## 7. Card Gallery status

**Not under maintenance** at acquisition time (2026-09-15). It rendered live content and successfully drove the discovery in section 6. The brief's premise of an under-maintenance gallery did not hold; this is recorded as a factual, dated observation rather than assumed.

## 8. Collection guides discovered

Three collection-guide PDFs plus one rulebook PDF, all linked from `/collection-guide` and/or the homepage:

- Collection guide, Set 1: Konoha Shidō, 1st edition (`Naruto_TCG_Collection_Guide_EN.pdf`)
- Collection guide, Set 1: Konoha Shidō, 2nd edition (`Naruto_TCG_Collection_guide_EN_v2-a83b0a03.pdf`)
- Collection guide, Set 2: Shinobi Shiren, 1st edition (`Collection+guide+Shinobi+Shiren+EN.pdf`)
- Rulebook (`Naruto-Mythos-TCG-Rulebook-EN.pdf`) — gameplay rules, not catalogue data.

All four were retrieved, hashed and stored untracked; their text/table content was **not** parsed in this phase (see section 30 — this requires a PDF-parsing dependency, which is a stop condition, not silently added).

## 9. Expansion inventory

| Set | Catalogue records (raw, all treatments) | Status |
|---|---|---|
| Set 1: Konoha Shidō | 394 | Released, two editions |
| Set 2: Shinobi Shiren | 242 | Released, one edition so far |
| Set 3: Akatsuki | 0 | "Coming soon" (products page only) |

## 10. Edition findings

Set 1 splits into `1st edition` (186), `2nd edition` (187), and **blank edition** (21 — every one of these is `Rarity=M` Mythos/promo, distributed via weekly tournaments, store championships, release events, or specific expos; see section 19). Set 2 currently shows only `1st edition` (242).

Structural note: the current `CardSet` model has an `edition` column at the **set** level (one row per set+edition combination is implied), but the real API attaches `Edition` at the **card-record** level within a single `Set` value. Mythos/promo cards have no edition at all. This is a genuine mismatch, not resolved here (see section 24).

## 11. Card types

Raw `CardType` values observed: `Character` (574), `Attachment` (32 — Set 2 only, exactly matching the site's "Thirty-two to collect" claim), `Mission` (30). Note: `Rarity` also literally contains the value `"Mission"` for mission cards (a CardType is echoed into the Rarity field) — a modeling quirk in the source itself, not just our interpretation.

## 12. Numbering systems

- Ordinary cards: printed ID format `NNN/130` for Set 1 (denominator = base set size) and `NNN/140` for Set 2, zero-padded to 3 digits (e.g. `001/130`, `078/140`).
- Missions: `MSS NN` (space-separated, e.g. `MSS 01`), repeated identically across the 1st and 2nd edition SKU prefixes (`NM-S1E1-MSS001V1` vs `NM-S1E1-MSS002V1`... `NM-S1E2-MSSxxxV1`), i.e. the same printed Mission ID recurs per edition as a distinct catalogue record.
- A separate, structured internal `SKU` field exists (e.g. `NM-S1E1-L133V1`, `NM-S1E1-C001FAV1`, `NM-S2E1-C079HV1`) encoding set/edition/rarity/number/treatment/version — a stronger stable identifier candidate than the printed `ID` alone.
- **Important caution**: card *image asset filenames* (e.g. `78140-en-520646d5.webp`, `mss1140-en-1af17f53.webp`) use a completely different internal numbering convention than the printed/API `ID` field (`078/140`, `MSS 01`). These must not be conflated; the asset filename is not the printed collector number.
- 185 of 318 unique printed `ID` values map to more than one distinct catalogue record (see section 23).

## 13. Rarity vocabulary

Raw `Rarity` field values and counts (en, 636 records): `C` 165, `UC` 151, `R` 84, `RA` 80, `M` 39, `S` 30, `Mission` 30 (pseudo-rarity, see section 11), `CHIBI` 13, `SV` 12, `SP` 11, `Shinobi` 10, `L` 7, `POP` 4.

The `/collection-guide` page groups these narratively as: Common/Uncommon (with Normal/Full-Art/Holo *finish* variants), Rare, Rare Art, Special, Chibi, Shinobi, POP, Secret/Secret Variant, Legendary, Mythos — this prose grouping does not map 1:1 onto the raw `Rarity` codes (e.g. "Common"/"Uncommon" finish differences live in the separate `Variant` field, not in `Rarity`).

## 14. Variant/treatment findings

A distinct `Variant` field exists, independent of `Rarity`: `''` (none) 317, `Full Art` 285, `Holo` 31, `Gold` 2, and **one anomalous `Normale`** (Italian word) leaking into the English-language response — a data-quality defect in the source, not our error. Classification:

- `Rarity` codes `C`/`UC`/`R`/`RA`/`S`/`SV`/`M`/`L` — **RARITY**.
- `Variant` values `Full Art`/`Holo`/`Gold` — **TREATMENT/FINISH**, orthogonal to rarity.
- Set-2-introduced `CHIBI`/`SP`/`Shinobi`/`POP` — live in the **`Rarity`** field per the source, even though the collection-guide prose describes them as visually distinctive treatments. **AMBIGUOUS**: the source itself blends rarity and treatment for these four; we do not force a resolution.
- `Illustration` field is constant `"Standard"` across all 636 records in this snapshot — currently non-discriminating; NOT_FOUND for any other value.

## 15. Serialization findings

- POP: exactly 4 distinct catalogue designs (matches site's "four designs, 300 individually serialized copies each"); the API carries no serial-run-count field — the "300 copies" figure exists only in site prose, not in the structured data.
- Legendary: 7 distinct catalogue designs across both sets (3 in Set 1, 4 in Set 2), described narratively as "unique pieces, individually numbered" 22K gold cards. The API does not expose a serial-count or per-copy identifier field either.
- Per section 13 of the brief, no per-physical-copy record was created; catalogue-level (design-level) records were counted, consistent with the API's own 1-row-per-design structure.

## 16. Card field availability

| Field | Presence (en, n=636) | Classification |
|---|---|---|
| ID, Uid, SKU, CardType, CardVersion, Group, Langs, Order, Rarity, Set, Title | 636/636 | ALWAYS |
| Image | 636/636 | ALWAYS (URL reference only; never downloaded) |
| Illustration | 636/636 | ALWAYS, but constant value in this snapshot |
| Edition | 615/636 | USUALLY (missing only for blank-edition Mythos promos) |
| Chakra, Power | 606/636 | TYPE_SPECIFIC (absent exactly for Mission cards) |
| Text | 629/636 | USUALLY |
| Version | 574/636 | USUALLY |
| Keyword1 | 565/636 | USUALLY |
| Variant | 319/636 | SOMETIMES |
| Keyword2 | 304/636 | SOMETIMES |
| Points | 30/636 | TYPE_SPECIFIC (Mission/Attachment scoring only) |
| Obtain | 51/636 | RARITY_SPECIFIC / SOURCE_SPECIFIC (concentrated in Mythos promos) |
| Stamp | 19/636 | RARITY_SPECIFIC, and **inconsistent**: some Mythos promos have descriptive `Obtain` text but a blank `Stamp` enum, so `Stamp` alone under-counts distribution-channel cards |

No missing value was inferred or filled in.

## 17. Language/territory findings

The client declares `SUPPORTED_LANGS = ["en","fr","it","es"]`, but the real data shows: 393/636 records support `en+fr`, 241/636 support `en` only, and only 2/636 touch `es`. The `lang=it` API response was **byte-for-byte identical** to `lang=en` — Italian is not currently served as distinct content despite being declared supported. Card identity (the set of 636 `ID`/`Uid` values) is identical across `en`/`fr`/`es` responses — language affects only presentational fields (`Title`, `Version`, `Text`, `Obtain`, localized `Edition` label), never numbering or card existence. Territory was not separately observed as a concept distinct from language in any source.

## 18. Set 1 findings

394 raw catalogue records: `1st edition` 186, `2nd edition` 187, blank-edition Mythos promos 21. Rarities present: C 110, UC 96, R 54, RA 54, M 29, S 20, Mission 20, SV 8, L 3. The 21 blank-edition Mythos cards are distribution-channel promos (Weekly Tournaments, Store Championship, Release Event, "UK GAMES EXPO", and unlabeled) layered on top of, not instead of, the two numbered editions.

## 19. Set 2 findings

242 raw catalogue records, one edition (`1st edition`) so far. Introduces `Attachment` CardType (32, matches marketing exactly) and four new `Rarity` codes: `CHIBI` 13, `SP` 11, `Shinobi` 10, `POP` 4. Full `Rarity` distribution for Set 2: UC 55, C 55, R 30, RA 26, CHIBI 13, SP 11, Shinobi 10, M 10, S 10, Mission 10, L 4, POP 4, SV 4 — **13 distinct raw `Rarity` values** (or 12 excluding the `Mission` pseudo-rarity), which does not cleanly match the site's marketing claim of "ten rarities and four brand-new ones" for Set 2 (see section 21). The marketing "140-card set" figure also does not equal the raw catalogue count of 242 records; the source does not define what subset (unique designs vs. all treatments vs. excluding promos/Mythos) would reduce 242 to 140, so no total is asserted here.

## 20. Set 3 findings

`Akatsuki` appears only on the `/products` page as "Coming soon", classified **ANNOUNCED**. Zero catalogue records exist for it in the card API (`Set` field never contains a "Set 3" value). No further detail (release date, card count) was found in the acquired sources.

## 21. Cross-source disagreements

1. **Gallery UI count vs. marketing count**: the rendered gallery's own default filter view is driven by the same 242-record Set 2 catalogue, matching this audit's raw count — but the Set 2 page's prose says "a 140-card set." Neither source defines the reduction from 242 raw records to 140; not resolved here.
2. **Rarity count claim vs. raw vocabulary**: "ten rarities" (Set 2 page) vs. 12–13 distinct raw `Rarity` values actually present for Set 2, depending on whether the `Mission` pseudo-rarity is counted.
3. **Language completeness claim vs. reality**: 4 languages are declared supported; Italian (`it`) is currently indistinguishable from English in the live API.
4. **Collection-guide narrative grouping vs. raw codes**: the guide page's "Secret and Secret Variant" combined heading doesn't expose the underlying `S`/`SV` code split that the API uses.

None of these were resolved by picking a winner; all are reported as-is per the brief.

## 22. Count reconciliation

| Metric | Count | Source |
|---|---|---|
| Raw catalogue print-records (en/fr/es) | 636 | API, `Cards` array length |
| Unique `Uid` values | 636 | API (fully unique — true per-print key) |
| Unique printed `ID` values | 318 | derived |
| `ID` values mapping to >1 distinct `Uid` | 185 | derived (58% of unique IDs) |
| Set 1 records | 394 | API `Set` field |
| Set 2 records | 242 | API `Set` field |
| Set 3 records | 0 | API `Set` field |
| `it` response vs `en` response | identical (0 unique) | SHA-256 comparison |

No total is claimed to be "complete" beyond what the API itself returned; the API returned a fixed 636-row array on both requests made, but repeatability across time was not tested (a second acquisition run reused the identical cached content by hash, so no drift was observed between the two runs performed today).

## 23. Collision analysis

The strongest, most concrete finding of this phase. Example `ID → {Uid}` collisions (from 185 total):

- `133/130` → 6 distinct `Uid`s (includes a Legendary `L` print and multiple Secret Variant `SV` prints of "Naruto Uzumaki").
- `131/130`, `136/130`, `137/130` → 3–4 distinct `Uid`s each (Secret Variant prints of Tsunade/Sasuke/Kakashi).
- `001/130` through `130/130` (ordinary Common/Uncommon range) → mostly 2 distinct `Uid`s each, corresponding to a Normal print and a Full-Art print sharing the same printed number.
- `MSS 01`–`MSS 10` recur once per Set 1 edition (`E1` and `E2` SKU prefixes), i.e. the same printed Mission ID is a different catalogue record per edition.

This directly demonstrates that `printed ID` alone is not a unique key even within one `(set, edition)` scope in the common case (Normal vs Full-Art pairing), and is very much not unique when Secret Variant/Legendary/Mythos prints reuse a base card's number. The only field observed to be unique across all 636 records is the opaque `Uid`.

## 24. Compatibility with Phase 12B

| Real-world concept | Classification | Notes |
|---|---|---|
| `Uid` as true per-print identity | REQUIRES_MODEL_EXTENSION | No current staging/identity concept maps to an opaque vendor-side per-print primary key distinct from public ID and from printed number. |
| `Card(set_id, card_number)` uniqueness | UNSUPPORTED (as literally mapped) | The existing constraint `uq_cards_set_id_card_number` would reject real data if `card_number` is naively set to the raw printed `ID`, because 185 printed IDs recur with different rarity/edition/variant within one set. |
| Rarity/treatment split for `CHIBI`/`SP`/`Shinobi`/`POP` | AMBIGUOUS | Source blends rarity-as-treatment for these four; `Card.rarity` (single string) could hold the raw code, but treatment semantics would need `CardVariant.variant_type`/`finish` to carry the visual distinction, which the source does not cleanly separate either. |
| `CardVariant.collector_number`, `.rarity_override`, `.edition`, `.language`, `.serial_numbered/.serial_total` | SUPPORTED_WITH_MAPPING | These free-text/nullable fields could represent per-print rarity/edition/variant if `Card` represents a base design and `CardVariant` rows represent the distinct prints sharing a number — but this requires deciding which of the 636 records become `Card` rows vs `CardVariant` rows, which is a modeling decision, not made here. |
| Mission-specific fields (`Chakra`/`Power` absent, `Points` present) | SUPPORTED | `Card.chakra`/`Card.power` are already nullable; `Points` has no current column (`REQUIRES_MODEL_EXTENSION` for a scoring field). |
| Attachment card type | REQUIRES_MODEL_EXTENSION | `card_type` is a free string already, so the value itself is SUPPORTED, but Attachment-specific semantics (attach target, etc.) are not modeled. |
| Edition attached per-card rather than per-set | REQUIRES_MODEL_EXTENSION | `CardSet.edition` is a set-level column; the real vendor data attaches `Edition` per card record within one `Set` grouping, and 21 Mythos cards have no edition at all. |
| Language as presentation-only, not identity | SUPPORTED | Matches `CardVariant.language` being a separate, non-identity-bearing field; no numbering/identity variance by language was observed. |
| Image URL references | SUPPORTED | `CardImage`/URL-reference storage already exists; no image bytes were or should be stored. |

## 25. Compatibility with Phase 12C

Not exercised against real data in this phase (no projection/planning was run). Structurally, the same open questions as section 24 apply: Phase 12C's canonical snapshot/projection logic assumes the Phase 12B identity model, so the `Uid`-vs-`card_number` and edition-per-card findings above would need resolution before any real-data projection could be attempted.

## 26. Compatibility with Phase 12D

Not exercised (no snapshot/execution was run; this phase has no database session). The same identity ambiguity would block `SnapshotScope`/`ExecutionCandidate` construction for real Naruto Mythos data until Phase 12B's identity rules are extended to cover multi-print-per-number collisions.

## 27. Required model extensions

1. A true per-print stable key distinct from the printed collector number (candidate: vendor `Uid`, or the structured `SKU`).
2. Either a composite uniqueness key (`set_id`, `card_number`, `rarity`, `edition`, `variant`) or an explicit `Card`-vs-`CardVariant` split that accommodates 185 known real collisions.
3. A `Points` (Mission/Attachment scoring) field.
4. A decision on whether `CHIBI`/`SP`/`Shinobi`/`POP` are rarities, treatments, or both.
5. A decision on how to represent per-card (not per-set) edition, including cards with no edition at all (Mythos promos).
6. A decision on how to represent distribution-channel/promo provenance (`Stamp` enum + freeform `Obtain` text), which is currently inconsistent even in the source.

None of these were implemented; all require human review per the brief's mandate.

## 28. Unresolved questions

- What does the marketing "140-card set" for Set 2 actually count, given the raw catalogue has 242 records?
- Is `Mission` truly a `Rarity` value, or is that a source-side implementation shortcut that should never be treated as a rarity?
- Are `CHIBI`/`SP`/`Shinobi`/`POP` rarities, treatments, or a new orthogonal axis?
- Does `Uid` guarantee long-term stability (is it safe to treat as a permanent identity), or is it merely an internal database auto-increment that could be reassigned?
- Why is the anomalous `Normale` value present in one English-language `Variant` field — a one-off data entry error, or evidence of deeper per-record data-quality issues?
- Will Italian localization ever diverge from English, or is `it` support aspirational/unfinished?
- What is the actual Set 2 rarity count intended by "ten rarities," and which four are "new" if 12–13 raw codes are observed?

## 29. Rights/redistribution observations

Card artwork was never downloaded; only URLs were recorded as text. The four PDFs are official downloads intended by the publisher for public checklist use, but were kept **untracked** locally (not committed) out of caution, since public accessibility does not itself establish redistribution permission. HTML pages were retrieved as ordinary read-only browsing; robots.txt permits automated access with no restriction. No claim of redistribution rights is made over any acquired content.

## 30. Files created

- `scripts/__init__.py`, `scripts/acquisition/__init__.py`, `scripts/acquisition/fetch.py`, `scripts/acquisition/storage.py`, `scripts/acquisition/sources.py`, `scripts/acquisition/run_acquisition.py`, `scripts/acquisition/analyze_cards.py`
- `tests/test_acquisition.py`
- `data/acquisition/README.md`, `data/acquisition/manifest.json`, `data/acquisition/observations/*.json` (13 files), `data/acquisition/card_data_audit.json`
- `data/acquisition/raw/*` (10 files: 6 HTML, 4 PDF, plus 4 JSON API responses — 12 unique hashes total since `en`/`it` API responses are identical; **untracked**, added to `.gitignore`)
- `.gitignore` modified to exclude `data/acquisition/raw/`
- `PHASE_13A_REPORT.md` (this file)

No existing tracked file was changed except `.gitignore`. No migration, no model change, no API/route/schema/OpenAPI/RapidAPI change.

## 31. Tests/validation

- New: `tests/test_acquisition.py` — 16/16 passed.
- Full suite: **642 passed**, 0 failed (626 baseline + 16 new).
- Ruff check: passed (0 errors), whole repo.
- Ruff format --check: passed, 124 files already formatted.
- Mypy (`app importer scripts`): passed, 0 issues in 78 source files.
- RapidAPI/OpenAPI regression (`test_rapidapi_export.py`, `test_rapidapi.py`, `test_openapi.py`): 54 passed.
- RapidAPI artifact SHA-256 verified unchanged: `9c76bca79d0056051dc2538e6b6b45382bb5275699d25e941fc82dbc5311d386`.

## 32. Risks/limitations

- PDF collection guides were retrieved and hashed but **not text-parsed**: no PDF-extraction library (`pypdf`/`pdfplumber`/etc.) is installed, and adding one is a new dependency — a documented STOP condition rather than an improvised workaround (see section 33.4 below and the note added to the recommendation).
- The real card API could change or be taken down at any time; this phase's raw captures are a point-in-time snapshot (2026-09-15), not a live feed.
- The third-party proxy domain (`services.agenziamarketingcarpi.it`) was deliberately not queried; if the direct API is ever disabled again, future acquisition would need a documented, human-approved allowlist change to use the proxy instead.
- Findings on rarity/treatment/edition semantics are based on one snapshot in one language pass each; recurring acquisition would strengthen confidence before Phase 13B normalization work begins.

## 33. Recommendation for Phase 13B

**CONDITIONAL GO.** The real data source is far richer and more directly machine-readable (a first-party JSON API) than anticipated, which is good news for Phase 13B's parser/normalizer design — but the collision and edition-per-card findings in sections 23–24 mean Phase 13B cannot simply map the real `ID` field onto `Card.card_number` without first resolving the identity-model questions in section 27. Recommend Phase 13B begin with an identity-design sub-phase (mapping `Uid`/`SKU` to a stable internal key and resolving the `Card`/`CardVariant` split) before writing any parser/normalizer code, and recommend a human decision on the PDF-parsing dependency question before attempting to corroborate the API data against the official printed collection guides.

---

## Final response summary

- Real public Naruto Mythos data accessed: **YES**
- Official public HTML accessed: **YES**
- Official public guides accessed: **YES** (PDFs retrieved and hashed; text not parsed — see limitations)
- Official artwork downloaded/stored: **NO**
- Authentication bypassed: **NO**
- Access controls bypassed: **NO**
- Production DB accessed: **NO**
- Production DB modified: **NO**
- Real catalogue imported: **NO**
- Railway modified: **NO**
- RapidAPI modified: **NO**
- Deployment performed: **NO**
- Migration created: **NO**
- `.env` read: **NO**
- Commit created: **NO**
- Push performed: **NO**
- Phase 13B started: **NO**

**Git status at end of phase:** `main` branch, working tree modified but **nothing committed**. Modified: `.gitignore` (added `data/acquisition/raw/` ignore rule). New/untracked: all files listed in section 30, including `data/acquisition/raw/*` which git ignores by design. No file was staged or committed. Human review requested before any commit.
