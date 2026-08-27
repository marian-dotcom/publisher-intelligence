# EP-026 local/production-like backend image.
# One shared codebase, multiple process types (ADR-078/ADR-083):
#   api            -> uvicorn app.main:app
#   worker         -> python -m app.worker
#   scheduler      -> python -m app.scheduler
#   migrate        -> alembic upgrade head  (one-off)
#   browser-worker -> python -m app.browser_worker  (see `browser` target below)

FROM python:3.12-slim AS base

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy

WORKDIR /app

RUN groupadd --system app && useradd --system --gid app --create-home appuser

COPY --from=ghcr.io/astral-sh/uv:0.7 /uv /usr/local/bin/uv

# Locked dependency install first (cached layer).
COPY pyproject.toml uv.lock ./
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev --no-install-project

# Application source (shared by every process type).
COPY alembic.ini ./
COPY migrations ./migrations
COPY app ./app
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev

USER appuser

FROM base AS api
EXPOSE 8000
ENV PATH="/app/.venv/bin:$PATH"
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]

FROM base AS worker
ENV PATH="/app/.venv/bin:$PATH"
CMD ["python", "-m", "app.worker"]

FROM base AS scheduler
ENV PATH="/app/.venv/bin:$PATH"
CMD ["python", "-m", "app.scheduler"]

FROM base AS migrate
# One-off migration runner; safe to repeat (alembic upgrade head is idempotent).
ENV PATH="/app/.venv/bin:$PATH"
CMD ["alembic", "upgrade", "head"]

# Browser process type: adds Playwright Chromium + system dependencies and the
# dedicated non-root runtime user required by the enabled Chromium sandbox
# (SECURITY.md §41: --no-sandbox in production requires explicit security review).
FROM base AS browser
# Shared, non-home browser cache so the non-root runtime user finds Chromium.
ENV PLAYWRIGHT_BROWSERS_PATH=/opt/ms-playwright
USER root
RUN mkdir -p /opt/ms-playwright \
    && /app/.venv/bin/playwright install --with-deps chromium \
    && chown -R appuser:app /opt/ms-playwright /app
USER appuser
ENV PATH="/app/.venv/bin:$PATH"
CMD ["python", "-m", "app.browser_worker"]
