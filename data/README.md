# Approved local data

The Phase 8 importer accepts normalized, approved local JSON only. It does not scrape sites or download artwork.

- `schema/catalogue.schema.json`: generated importer JSON Schema.
- `examples/fictional-catalogue.json`: two fictional sets, keywords, variants, and external image URLs.
- See `../importer/README.md` for the complete contract and CLI usage.

Local `data/*.json` inputs remain git-ignored. Review authorization before committing any additional dataset.
