# Curated Collector References

`konoha_shido_1st_edition_master.xlsx` is the reviewed collector checklist input for Konoha Shidō 1st Edition. Keep the workbook unchanged as the reference source.

`konoha_shido_1st_edition_master.json` is generated deterministically from the workbook by:

```powershell
python scripts/build_konoha_reference.py
```

Verify that the committed JSON matches the workbook without rewriting it:

```powershell
python scripts/build_konoha_reference.py --check
```

The generated artifact includes the original collector number, card label, raw rarity, raw Variant, worksheet row for audit navigation, and stable reference key. It deliberately excludes Owned, Qty, prices, totals, formulas, image references, and serial totals. Its `source_sha256` binds it to the unmodified workbook.

The reconciliation uses local acquired upstream source data and the generated JSON. It never fetches data or writes to a database. Import persistence is a separate explicit function that records the curated reference relationship; workbook rows are never emitted as upstream SourceRecords.