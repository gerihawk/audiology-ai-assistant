.PHONY: up down build logs migrate seed retention-purge test test-frontend lint format

up:
	docker compose up --build

down:
	docker compose down

build:
	docker compose build

logs:
	docker compose logs -f

migrate:
	docker compose run --rm backend alembic upgrade head

seed:
	docker compose run --rm backend python -m app.seed

retention-purge:
	docker compose run --rm backend python -m app.retention.cli

test:
	docker compose run --rm backend pytest

test-frontend:
	docker compose run --rm frontend npm test

lint:
	docker compose run --rm backend ruff check .
	docker compose run --rm backend black --check .
	docker compose run --rm frontend npm run lint
	docker compose run --rm frontend npm run format:check

format:
	docker compose run --rm backend ruff check --fix .
	docker compose run --rm backend black .
	docker compose run --rm frontend npm run format
