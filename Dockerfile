FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    APP_ENV=production

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends libpq5 ca-certificates \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.production.txt ./requirements.production.txt
COPY production-baseline.constraints ./production-baseline.constraints

RUN python -m pip install --upgrade pip \
    && python -m pip install --no-cache-dir -r requirements.production.txt

COPY alembic.ini ./alembic.ini
COPY app ./app
COPY importer ./importer
COPY migrations ./migrations
COPY data ./data

RUN groupadd --system app && useradd --system --gid app --create-home --home-dir /home/app app \
    && chown -R app:app /app

USER app

EXPOSE 8000

CMD ["sh", "-c", "test -n \"$DATABASE_URL\" || { echo 'DATABASE_URL is required for runtime.' >&2; exit 1; }; exec uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000} --proxy-headers"]
