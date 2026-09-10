SHELL := /bin/bash
POETRY := poetry

.PHONY: help install shell run test pytest integration-test keycloak-up keycloak-token token docs docs-build tox docker-build docker-up docker-down logs migrate seed reset-seed docker-seed docker-reset-seed alembic-revision

help:
	@echo "Available targets:"
	@echo "  install        : Install dependencies with poetry"
	@echo "  shell          : Enter poetry shell"
	@echo "  run            : Run dev server (uvicorn)"
	@echo "  test           : Start services, generate Keycloak token, and run pytest with coverage"
	@echo "  pytest         : Run pytest with optional TEST variable: make pytest TEST=src/unidades/test_unidades.py"
	@echo "  integration-test : Start Keycloak, generate token, and run integration tests"
	@echo "  keycloak-up    : Start Keycloak with imported test realm"
	@echo "  keycloak-token : Print an access token for the integration test user"
	@echo "  token          : Alias for keycloak-token; copy the output into Swagger Authorize"
	@echo "  tox            : Run tox"
	@echo "  docker-build   : Build docker image"
	@echo "  docker-up      : Start services with docker-compose"
	@echo "  docker-down    : Stop services"
	@echo "  logs           : Tail docker-compose logs"
	@echo "  migrate        : Run alembic upgrade head"
	@echo "  seed           : Run migrations and seed local database"
	@echo "  reset-seed     : Reset local database data and seed it"
	@echo "  docker-seed    : Run seeds inside the API container"
	@echo "  docker-reset-seed : Reset database data and seed it inside the API container"
	@echo "  lint           : Run linter (pylint)"
	@echo "  format         : Run code formatter (black)"
	@echo "  typecheck      : Run static type checks (mypy)"

install:
	$(POETRY) install

shell:
	$(POETRY) shell

run:
	$(POETRY) run uvicorn src.main:app --reload --host 0.0.0.0 --port 8000

test:
	scripts/run-tests.sh -v

pytest:
	$(POETRY) run pytest $(TEST)

integration-test:
	scripts/run-integration-tests.sh

keycloak-up:
	docker compose up -d keycloak

keycloak-token:
	scripts/keycloak-token.sh

token: keycloak-token

lint:
	$(POETRY) run pylint src


tox:
	tox

docker-build:
	docker build -t paraiba-hotdog-back .

docker-up:
	docker-compose up -d --build

docker-down:
	docker-compose down

logs:
	docker-compose logs -f

migrate:
	$(POETRY) run alembic upgrade head

seed: migrate
	PYTHONPATH=. $(POETRY) run python scripts/seed.py

reset-seed: migrate
	PYTHONPATH=. $(POETRY) run python scripts/reset_seed.py

docker-seed:
	docker compose exec paraiba-hotdog-back env PYTHONPATH=/app python scripts/seed.py

docker-reset-seed:
	docker compose exec paraiba-hotdog-back env PYTHONPATH=/app python scripts/reset_seed.py

alembic-revision:
	$(POETRY) run alembic revision --autogenerate -m "$(MSG)"
