# Phase 11 RapidAPI export compatibility review

Reviewed on 15 September 2026. Source: the user-supplied
`C:\Users\elena\Downloads\naruto-mythos-api-phase4\naruto-mythos-api-dl.zip`.
Changes were made in a separate working copy. The original ZIP was not changed.

## Finding about the reported 109 errors/warnings

The supplied `docs/generated/openapi.rapidapi.json` already declares OpenAPI
3.0.2, matches the supplied exporter, and passes OpenAPI 3.0 specification
validation with zero errors. No invalid paths, parameters, operation IDs,
references, response objects, or schemas were found in that artifact.

The canonical FastAPI 3.1 schema has exactly **109 conversion sites**:

| Construct | Count | RapidAPI export representation |
| --- | ---: | --- |
| Null branches in optional unions | 44 | Typed nullable schemas |
| Schema-level `examples` arrays | 62 | Singular `example` |
| `const` discriminators | 3 | Single-value `enum` |

These were already converted in the supplied artifact. The five legal named
media-type `examples` maps are preserved. The numerical match suggests that the
canonical `/openapi.json` or an earlier unconverted artifact may have been
submitted to RapidAPI. This is an inference, not a verified cause: the original
RapidAPI diagnostics were not supplied, and no portal import was performed.

## Exporter problems found and changes made

These are converter edge-case defects and missing safeguards; they were not
present as validation errors in the supplied generated JSON.

1. Recursive rewriting treated arbitrary example/default/vendor-extension
   payloads as schemas. Conversion now visits only Schema Objects and preserves
   instance data literally, including keys named `const`, `type`, or `$ref`.
2. Empty schemas `{}` were incorrectly identified as null branches. Actual null
   branches are identified before conversion; unconstrained branches stay intact.
3. Standalone null schemas became unconstrained objects. They now become a typed
   nullable schema with `enum: [null]`, accepting only null.
4. Multi-branch nullable unions lost effective null support; `oneOf` null handling
   could create an unconstrained branch. Complex unions now retain a null-only
   branch. Simple primitive unions become typed nullable schemas. Nullable enum
   branches include null without weakening constraints outside the union.
5. Nullable references could produce ignored `$ref` siblings. Nullable referenced
   schemas retain their union; other Schema Object reference siblings move into
   `allOf`, retaining descriptions and validation constraints.
6. Numeric exclusive bounds were left in the incompatible 3.1 form. They now use
   boolean exclusive bounds plus `minimum`/`maximum`, preserving stricter existing
   inclusive bounds, including zero-valued boundaries.
7. Type arrays were not converted. They now use composition, including explicit
   null handling, without replacing pre-existing composition constraints.
8. `const` with an existing enum could be silently discarded. It now narrows to
   the constant; contradictory constant/enum combinations fail explicitly.
9. The examples heuristic could mishandle legal external/reference Example
   Objects or accidentally accept illegal Schema Object examples. Schema arrays
   become a single example, an existing singular example takes precedence, and
   legal named media examples remain unchanged.
10. Boolean schemas were left invalid for 3.0 schema positions. `true` becomes
    `{}`; `false` becomes `not: {}`. Boolean `additionalProperties` stays intact.
11. Other unsupported 3.1 keywords could pass through without detection. Dialect
    and comment annotations are removed. Unrepresentable validation keywords
    (including conditional, tuple, dependent, and unevaluated constraints) now
    fail closed rather than silently weakening the contract.
12. Exporting did not validate the output. The exporter now validates version,
    the exact public GET surface, actual duplicate route registrations, operation
    IDs, parameter declarations and duplicates, component references, response
    objects/schemas, and excluded credentials/security schemes before writing.
    Serialization rejects non-finite JSON numbers and duplicate JSON keys.
13. The existing tests imported an undeclared OpenAPI validator dependency.
    Both OpenAPI validators are now declared in the development extra only;
    production dependencies and deployment files are unchanged.
14. Output depended on the caller's current directory. The default output is now
    anchored to the project directory and the command prints its absolute path.

The route audit handles both flat route lists and the included-router contexts
used by the installed FastAPI version. Fifty new regression tests cover semantic
equivalence, examples, references, unsupported keywords, contract preservation,
duplicate declarations, invalid exports, and deterministic file generation.

## Files changed

- `scripts/export_rapidapi_openapi.py`: conversion and validation safeguards.
- `tests/test_rapidapi_export.py`: 50 new regression test cases.
- `pyproject.toml`: development-only OpenAPI validator dependencies.
- `docs/RAPIDAPI.md`: regeneration, upload selection, and validation instructions.
- `docs/generated/openapi.rapidapi.json`: regenerated and validated; JSON content
  remains semantically identical to the supplied valid artifact. Object member
  ordering and final newline may differ.
- `docs/RAPIDAPI_EXPORT_REVIEW.md`: this review report.

## Final document inventory and validation

| Check | Result |
| --- | --- |
| OpenAPI version | 3.0.2 |
| Paths | 12 |
| Operations | 12, all GET |
| Parameters | 38: 34 query and 4 required path declarations |
| Component schemas | 23 |
| Response objects | 42 |
| Component reference occurrences | 61, all resolve |
| Schema examples | 77 validated: 62 converted and 15 existing singular examples |
| Response examples | 18 validated |
| Nullable schemas | 44 |
| Operation IDs | 12 valid, unique, unchanged |
| Duplicate JSON keys/routes/operations | None |
| Canonical schema comparison | Unchanged after export |
| Application/importer/migration files vs ZIP | Byte-for-byte unchanged |
| Origin credentials or consumer security schemes in export | None |

`/health` and `/ready` remain present. All paths, parameters, operation IDs, tags,
descriptions, response schema meanings, and `/v1/*` runtime security are preserved.
The existing middleware tests still verify optional gateway-secret behavior.

## Commands and results

Python 3.12.14; dependencies installed using the repository's
`production-baseline.constraints`, plus the development validators.

| Command | Result |
| --- | --- |
| Baseline `python -m pytest -q` | 360 passed |
| Final `python -m pytest -q` | 410 passed, zero failures or skips |
| `python -m ruff check .` | All checks passed |
| `python -m mypy app importer scripts` | No issues in 55 source files |
| `python -m openapi_spec_validator docs/generated/openapi.rapidapi.json` | OK |
| Explicit `OpenAPIV30SpecValidator` | Passed before and after regeneration |
| `OAS30Validator` example/semantic checks | Passed |

Three pre-existing dependency deprecation warnings remain: Starlette's HTTPX
TestClient integration, AnyIO's BlockingPortal alias, and the legacy
`validate_spec` shortcut used by an existing test. The new exporter uses the
explicit 3.0 validator and does not introduce these warnings.

The full existing suite uses isolated SQLite fixtures and mocked readiness checks;
this is not a live PostgreSQL integration or deployment test. No production
database connection or catalogue import was performed.

## Exact output

`C:\Users\elena\Documents\New project\naruto-mythos-api-rapidapi-review\docs\generated\openapi.rapidapi.json`

SHA-256:
`9c76bca79d0056051dc2538e6b6b45382bb5275699d25e941fc82dbc5311d386`

Upload this file to RapidAPI, not the canonical origin `/openapi.json`. Local
standards validation has passed; acceptance by RapidAPI's proprietary importer
has not been claimed or tested. No deployment, commit, push, or Phase 12 work
was performed.

Reference specifications:
[OpenAPI 3.0.2](https://spec.openapis.org/oas/v3.0.2.html) and
[RapidAPI OpenAPI import documentation](https://docs.rapidapi.com/docs/adding-and-updating-openapi-documents).
