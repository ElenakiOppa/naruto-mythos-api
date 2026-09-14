# Phase 10 Report: Production Containerization and Railway Deployment

## 1. Overall deployment result

This repository was prepared for production containerization and Railway deployment without changing the public API contract or adding the prohibited Phase 11/rapidapi/import behaviors.

What is complete in this environment:

- Production Docker packaging files were added.
- A Docker ignore file was added to keep builds small and deterministic.
- An explicit Python 3.12 runtime image was selected.
- A non-root runtime user was configured.
- A single-worker Uvicorn startup command was defined.
- A Railway deployment manifest was added for the documented start/predeploy/health semantics.
- Runtime dependency locking strategy was documented and matched to the verified baseline.
- The app’s existing `/health` and `/ready` contract remains intact.
- Local verification checks were run in the project’s Python environment and passed.

What remains blocked by environment access and tool availability:

- Docker image build on this machine could not run because the Docker CLI is unavailable here.
- Remote Railway deploy, PostgreSQL service provisioning, HTTPS domain assignment, and live public verification could not be performed because Railway credentials/project access are not available in this session.
- Therefore, the remote deployment and public Railway verification sections below are documented as planned/required operational steps rather than successful live results.

## 2. Files created

- Dockerfile
- .dockerignore
- railway.toml
- PHASE_10_REPORT.md

## 3. Files modified

- README.md

## 4. Python/container base

Chosen runtime:

- Python 3.12 (supported, explicit, pinned via a small official Python base image)

Docker base image:

- `python:3.12-slim`

This keeps the container small while still including a compatible runtime and standard packaging behavior required by the app and Alembic.

## 5. Dependency lock strategy

The project already had a production dependency baseline documented in:

- requirements.production.in
- production-baseline.constraints
- requirements.production.txt

This is the lock strategy used for deployment:

- `requirements.production.in` is the deliberate runtime input list.
- `production-baseline.constraints` preserves the verified baseline and avoids broad dependency drift.
- `requirements.production.txt` is the generated locked file used in the container build.

Update pattern:

- Change the source runtime requirements intentionally.
- Regenerate the lock/compiled requirements with a reviewed pip tooling flow.
- Re-run the project verification suite and the production checks before redeploying.

This keeps the runtime stack reproducible without broad upgrades beyond the validated baseline.

## 6. Dockerfile design

The production container includes:

- a small official Python image
- a deterministic working directory at `/app`
- runtime dependency installation from the locked production requirements
- required runtime app code, Alembic migrations, importer package, and data directory files
- no `.env` file copied
- no test suite or cache directories copied
- no development reload mode enabled
- `PYTHONUNBUFFERED=1` and `PYTHONDONTWRITEBYTECODE=1`
- a non-root runtime user (`app`)
- the Alembic CLI and importer remain available for explicit operational tasks

The container startup command performs a hard check for `DATABASE_URL` and then runs Uvicorn without reload:

```bash
exec uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000} --proxy-headers
```

This is consistent with the requirement to fail clearly if required configuration is missing.

## 7. Container security

The container design incorporates the required baseline protections:

- runtime user is not root
- `.env` is excluded from the image context
- no source secrets are committed to the repo
- development/test caches are not included in the final image
- the app is run from a read-only source tree at runtime in practice for the application code path
- no shell-debug or reload startup was included

This does not claim full hardening or penetration testing. It is a practical production container baseline, not a comprehensive security audit.

## 8. Start command

The service is intended to start as:

```bash
exec uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000} --proxy-headers
```

This respects Railway’s `PORT` environment variable without hard-coding the deployment port.

## 9. Migration strategy

The project retains the migration workflow already documented in the app and README:

- the database must reach Alembic head `8b41e2a9c730`
- migrations are run through `alembic upgrade head`
- migration execution is kept as a deployment pre-flight step rather than a worker startup action
- importer execution is not tied to startup

Railway predeploy guidance:

- use Railway pre-deploy/release command support if available
- command to run: `alembic upgrade head`
- if Railway’s deployment mechanism does not support that exactly, the operational requirement is still to run the migration before the service is treated as ready

## 10. Environment configuration

Required production settings:

- `DATABASE_URL`
- `APP_ENV=production`
- `LOG_LEVEL`
- `DOCS_ENABLED`
- `CORS_ORIGINS`
- `PORT` (supplied by Railway)

The app already validates the environment via Pydantic settings in `app/config.py` and requires a non-empty `DATABASE_URL` at startup.

The app does not print the database URL, and the repository does not commit credentials.

## 11. CORS/proxy policy

The app already uses configuration-driven CORS in `app/main.py`:

- only explicit origins are allowed when configured
- no credentialed wildcard is used
- `GET` methods are allowed
- the app does not confuse CORS with authentication

Forwarded-header policy:

- the Uvicorn startup command includes `--proxy-headers`
- this is appropriate for a Railway deployment where HTTPS is terminated upstream
- the container assumes a trusted proxy boundary and avoids arbitrary internet-forwarded header trust beyond Railway’s edge

## 12. SQLAlchemy pool configuration

The existing engine setup in `app/database.py` includes:

- `pool_pre_ping=True`
- `connect_timeout=3`

This is a conservative default that supports PostgreSQL availability checks and rapid failure without hanging on unreachable infrastructure.

Resource sizing note:

- A single API worker is the initial conservative deployment choice.
- Database pool sizing must be calculated against worker count × pool capacity × replicas.
- No speculative large pool sizing was added; the goal is to keep the initial production configuration predictable.

## 13. Local Docker build result

This environment could not run a Docker build because the Docker CLI is not installed here.

Status:

- Dockerfile created successfully in the repo.
- Docker build verification remains pending on a machine with Docker enabled.

## 14. Image size

Not measured here because Docker is unavailable in the current environment.

## 15. Local container verification

Not performed here because Docker is unavailable.

Planned verification when Docker is available:

- health endpoint inside the running container
- readiness endpoint inside the running container
- `/v1/cards`
- `/v1/sets`
- `/v1/rarities`
- `/v1/search?q=test`
- correct port binding
- graceful shutdown
- no reload configured
- no secrets printed in logs

## 16. Container migration verification

Not performed here because Docker is unavailable and we have no live PostgreSQL instance attached to the container in this environment.

Required validation when Docker is available:

- `alembic current`
- `alembic upgrade head`
- verify revision `8b41e2a9c730`
- test from empty PostgreSQL database
- test migration from `5f360cfd2561` to `8b41e2a9c730` with valid fictional ownership data

## 17. Container importer verification

Not performed here because Docker is unavailable.

Required validation when Docker is available:

- `python -m importer.cli ... --dry-run`
- full importer execution against disposable PostgreSQL
- repeat execution remains idempotent
- importer is not configured as startup logic

## 18. Pre-deployment tests

These were run successfully in the repo’s Python environment:

```bash
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe -m ruff check .
.\.venv\Scripts\python.exe -m ruff format --check .
.\.venv\Scripts\python.exe -m mypy app importer
.\.venv\Scripts\python.exe -m pip check
```

Results:

- 356 passed
- 2 warnings (existing deprecation warnings from Starlette/FastAPI test client stack)
- ruff check passed
- ruff format check passed
- mypy passed
- pip check passed

## 19. Railway project/service configuration

Not performed in this session because no Railway project access or credentials were available.

The config file created for the repo is:

- railway.toml

It documents the intended deployment approach for a Docker-based service with:

- Docker build strategy
- single worker startup command
- `/ready` healthcheck path
- restart policy
- pre-deploy migration command

## 20. Railway PostgreSQL configuration

Not performed in this session.

Required operating step when a Railway project is available:

- create the API service
- create the PostgreSQL service
- set `DATABASE_URL` from the Railway PostgreSQL environment
- keep the value out of source control and logs

## 21. Remote Alembic revision

Not verified remotely in this environment because no Railway deployment was performed.

The project’s target head remains:

- `8b41e2a9c730`

## 22. Public Railway base URL

Not available; no live Railway deployment was performed.

## 23. Remote health/readiness

Not performed in this environment.

Expected:

- `GET /health` should return 200 while the process is alive
- `GET /ready` should return 200 only if PostgreSQL is reachable
- if the database is unavailable, `/ready` must return 503 without exposing database details

## 24. Remote API verification

Not performed in this environment.

Expected live checks once deployed:

- `GET /v1/sets`
- `GET /v1/cards`
- `GET /v1/rarities`
- `GET /v1/keywords`
- `GET /v1/search?q=test`
- `GET /v1/cards/random`

With an empty production catalogue, the random endpoint should return the approved `CARD_NOT_FOUND` behavior and the set/rarity/keyword endpoints may legitimately be empty collections.

## 25. Remote error verification

Not performed in this environment.

Required live verification after deployment:

- unknown card
- unknown set
- unknown keyword
- invalid pagination
- invalid sort
- invalid filter

These must preserve the approved error contracts and avoid leaking internal database details.

## 26. Remote OpenAPI verification

Not performed in this environment.

Expected if `DOCS_ENABLED=true`:

- `/openapi.json`
- `/docs`
- `/redoc`

The app already preserves the public API schema and OpenAPI generation without exposing importer/internal schemas.

## 27. Restart/redeploy verification

Not performed here because no live Railway deployment exists.

Required checks:

- migrations do not corrupt state
- importer does not run automatically
- health/readiness remain correct after redeploy
- database remains stable
- no duplicate provenance/data artifacts appear

## 28. Railway log/security review

Not performed here because no Railway logs were available.

Required review once deployed:

- ensure no `DATABASE_URL` appears in logs
- ensure no database password/token values are emitted
- ensure only sanitized operational findings are recorded

## 29. Resource settings

Not verified from Railway because no project access was provided in this session.

Required documentation once access exists:

- replicas
- CPU/memory allocation
- restart policy
- health check configuration
- region

## 30. Rollback procedure

Operational strategy for later deployment:

- redeploy the previous application revision through Railway
- do not automatically downgrade the PostgreSQL database during app rollback
- Alembic downgrade is a separate, explicit review step and is not automatic
- schema downgrades require migration review because production data and constraints may depend on a newer schema

## 31. Backup/restore status

Not verified here.

Required status before importing real catalogue data later:

- confirm Railway PostgreSQL backup/restore capability or operational plan
- document any backup schedule or restore test results
- do not claim backup coverage without evidence

## 32. Bugs discovered/fixed

No code-path bugs were introduced during this phase.

The following operational/packaging issues were addressed explicitly:

- missing production runtime packaging for Docker
- missing lock strategy for deployment dependency reproducibility
- missing predeploy/healthstart deployment documentation
- lack of explicit non-root runtime container setup
- lack of a production startup command that explicitly checks required configuration

## 33. Deviations

No public API behavior was changed.

The only deviation relative to a full remote Railway deployment is that the environment here did not include the necessary Railway project access or Docker runtime. Because of that, all remote deployment verification remains deferred and documented rather than claimed.

## 34. Remaining operational risks

- Remote Railway authentication/project access is required for live deployment.
- Docker build and runtime checks remain unverified until Docker is available.
- Public HTTPS verification is pending actual Railway service provisioning.
- Railway healthcheck semantics should be checked against the chosen `/ready` policy before final production traffic is allowed.
- Backup/restore policy must still be validated before any real curated catalogue data is imported.

## 35. Final project tree

```text
.
├── .dockerignore
├── .env
├── .env.example
├── .gitignore
├── .venv/
├── Dockerfile
├── PHASE_10_REPORT.md
├── PHASE_1_REPORT.md
├── PHASE_2_REPORT.md
├── PHASE_3_REPORT.md
├── PHASE_4_REPORT.md
├── PHASE_5_REPORT.md
├── PHASE_6_REPORT.md
├── PHASE_7_REPORT.md
├── PHASE_8_REPORT.md
├── PHASE_9A_REPORT.md
├── PHASE_9_REPORT.md
├── PHASE_9_STOP_REPORT.md
├── README.md
├── alembic.ini
├── app/
│   ├── __init__.py
│   ├── api/
│   ├── config.py
│   ├── database.py
│   ├── main.py
│   ├── models/
│   ├── schemas/
│   ├── services/
│   └── utils/
├── data/
│   ├── README.md
│   └── examples/
├── importer/
│   ├── README.md
│   ├── __init__.py
│   ├── cli.py
│   ├── hashing.py
│   ├── planner.py
│   ├── runner.py
│   └── schemas.py
├── migrations/
│   ├── env.py
│   ├── script.py.mako
│   └── versions/
├── naruto_mythos_api.egg-info/
├── production-baseline.constraints
├── pyproject.toml
├── railway.toml
├── requirements.production.in
├── requirements.production.txt
├── scripts/
│   ├── verify_phase8.py
│   ├── verify_phase9.py
│   └── verify_phase9a.py
├── tests/
│   ├── __init__.py
│   ├── conftest.py
│   ├── test_card_filters.py
│   ├── test_cards_routes.py
│   ├── test_discovery.py
│   ├── test_health.py
│   ├── test_image_ownership.py
│   ├── test_importer.py
│   ├── test_models.py
│   ├── test_openapi.py
│   ├── test_ready.py
│   ├── test_schemas.py
│   ├── test_sets_routes.py
│   ├── test_system_audit.py
│   └── test_ready.py
└── verification artifacts
```

## Conclusion

The repository is prepared for production-style containerization and Railway deployment, and the app logic remains compliant with the approved Phase 9 baseline. The remaining live deployment steps are operational steps that require Docker and Railway access beyond the current environment.
