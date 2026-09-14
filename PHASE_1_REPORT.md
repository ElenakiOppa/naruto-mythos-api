# Naruto Mythos TCG Developer API — Phase 1 Report

**Date:** September 2026
**Scope:** Phase 1 only (project scaffolding + health check), per the phased implementation plan in the project spec.
**Status:** ✅ Complete and verified

---

## 1. Objective

Stand up the foundational project skeleton for a public, versioned REST API for
Naruto Mythos TCG catalogue data — without touching the database schema,
catalogue endpoints, or importer logic, which are reserved for later phases.

Deliverables required for Phase 1:

1. Repository structure
2. `pyproject.toml` with dependencies
3. `.env.example`
4. `.gitignore`
5. Minimal FastAPI application
6. `GET /health` endpoint
7. A working dev server
8. A passing health endpoint test

---

## 2. What Was Built

### 2.1 Project structure

```
naruto-mythos-api/
├── app/
│   ├── main.py          FastAPI app instance, CORS config, router mount
│   ├── config.py         Environment-driven settings (Pydantic Settings)
│   ├── database.py       SQLAlchemy engine/session setup
│   ├── models/           (empty — Phase 2)
│   ├── schemas/health.py Health response schema
│   ├── services/         (empty — later phases)
│   ├── utils/            (empty — later phases)
│   └── api/
│       ├── router.py     Aggregates versioned + unversioned routers
│       └── v1/health.py  GET /health handler
├── importer/              (empty — Phase 8)
├── data/README.md         Explains git-ignored, authorized-only data policy
├── migrations/            (empty — Phase 2, Alembic)
├── tests/test_health.py   2 tests covering /health
├── .env.example
├── .gitignore
├── pyproject.toml
└── README.md
```

### 2.2 Key design decisions

| Decision | Rationale |
|---|---|
| `/health` mounted unversioned, `/v1` reserved for catalogue endpoints | Matches spec; keeps a clean separation between system and public API surface |
| CORS defaults to **zero** allowed origins if unset, and `allow_credentials=False` always | Public read-only API — avoids ever pairing `*` with credentials |
| `DATABASE_URL` validated as required at app startup | Fail fast on misconfiguration rather than surfacing confusing errors later |
| `/health` does a best-effort DB ping but never fails the endpoint if the DB is unreachable | Health should reflect service liveness, not full infra readiness, at this stage |
| DB engine configured with a 3-second `connect_timeout` | **Bug found and fixed during testing** — see Section 4 |
| Settings cached via `lru_cache` | Avoids re-parsing environment variables on every request |

---

## 3. Verification Results

All verification was done by actually running the code on the developer's
Windows 11 / Python 3.14 machine — not just static review.

| Check | Result |
|---|---|
| `pip install -e ".[dev]"` | ✅ Succeeded — all dependencies resolved and installed cleanly |
| `uvicorn app.main:app --reload` | ✅ Server started successfully |
| `GET /health` (browser) | ✅ Returned exact expected shape: `{"status": "ok", "version": "1.0.0"}` |
| `GET /docs` (Swagger UI) | ✅ Reachable |
| `pytest` | ✅ **2 passed**, 0 failed |
| Test runtime | 13.15s (after fix — see below) |

### Test coverage

- `test_health_returns_ok_status_and_version` — confirms status code 200 and exact response body
- `test_health_response_has_no_extra_sensitive_fields` — confirms no unexpected fields (e.g. no leaked config/DB details) are present in the response

---

## 4. Issue Found and Fixed During Testing

**Symptom:** On the developer's machine (no local PostgreSQL running), `pytest`
appeared to hang indefinitely after the first test. It eventually completed
after **491 seconds (~8 minutes)** for a single test, forcing a manual
Ctrl+C on the second.

**Root cause:** The `/health` endpoint's best-effort database ping used
SQLAlchemy's `create_engine()` with no connection timeout configured. When
Postgres wasn't reachable, the underlying `psycopg` connection attempt fell
back to the OS-level TCP timeout on Windows, which can take several minutes
rather than failing immediately (as it typically would with an instant
"connection refused" on Linux/Mac in this environment).

**Fix:** Added `connect_args={"connect_timeout": 3}` to the engine
configuration, so an unreachable database now fails within ~3 seconds
instead of minutes.

**Result after fix:** Full test suite (2 tests, each independently pinging
the DB) completed in 13.15 seconds — consistent with two ~3-6 second
timeouts plus normal test overhead.

This was a genuine latent bug that would have made local development and
CI painfully slow (or seemingly "frozen") for any contributor without a
database running — worth having caught before Phase 2 introduces real
database dependencies.

---

## 5. Explicitly Out of Scope for Phase 1 (confirmed not built)

Per the phased plan, none of the following exist yet:

- Database models (Sets, Cards, Variants, Keywords, Images, Source Records)
- Alembic migrations
- `/v1/cards`, `/v1/sets`, `/v1/rarities`, `/v1/keywords`, `/v1/search` endpoints
- Pagination, filtering, sorting logic
- The importer package
- Docker / docker-compose
- Railway-specific deployment config
- Any real Naruto Mythos card data (per project rules, none will be invented or scraped)

---

## 6. Recommendation

Phase 1 is stable, tested, and verified end-to-end on the target developer
machine. Recommend proceeding to **Phase 2: Database Models + Initial
Alembic Migration**, covering:

- `sets`, `cards`, `card_variants`, `keywords`, `card_keywords`,
  `card_images`, `source_records` tables
- Required indexes (`public_id`, `set_id`, `card_number`, `name`,
  `rarity`, `card_type`)
- Initial Alembic migration generation and a local `alembic upgrade head`
  verification against a real PostgreSQL instance

---

*Report reflects only what has been implemented and verified as of Phase 1
completion. No card data, artwork, or third-party catalogue content is
included in this project.*
