.PHONY: install check test test-integration secret-scan infra-up infra-down migrate api worker scheduler browser-worker frontend

install:
	uv --directory backend sync --all-groups --locked
	pnpm --dir frontend install --frozen-lockfile

check:
	uv --directory backend run ruff check .
	uv --directory backend run ruff format --check .
	uv --directory backend run mypy app tests scripts migrations/env.py
	uv --directory backend run pytest tests/unit
	pnpm --dir frontend lint
	pnpm --dir frontend typecheck
	pnpm --dir frontend test
	pnpm --dir frontend build
	python scripts/check_secrets.py

test:
	uv --directory backend run pytest tests/unit
	pnpm --dir frontend test

test-integration:
	RUN_INTEGRATION=1 uv --directory backend run pytest tests/integration

secret-scan:
	python scripts/check_secrets.py

infra-up:
	docker compose up -d postgres minio minio-init

infra-down:
	docker compose down

migrate:
	uv --directory backend run alembic upgrade head

api:
	uv --directory backend run uvicorn app.main:app --reload

worker:
	uv --directory backend run python -m app.worker

scheduler:
	uv --directory backend run python -m app.scheduler

browser-worker:
	uv --directory backend run python -m app.browser_worker

frontend:
	pnpm --dir frontend dev
