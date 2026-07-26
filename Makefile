PYTHON ?= python3
VENV   ?= .venv
BIN    := $(VENV)/bin

.DEFAULT_GOAL := help

help: ## Show this help
	@grep -hE '^[a-zA-Z_-]+:.*?## ' $(MAKEFILE_LIST) \
	  | awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-14s\033[0m %s\n", $$1, $$2}'

$(BIN)/python:
	$(PYTHON) -m venv $(VENV)

install: $(BIN)/python ## Create the venv and install runtime + dev dependencies
	$(BIN)/pip install --upgrade pip
	$(BIN)/pip install -e ".[dev]"

run: ## Start the server
	$(BIN)/python -m wwps

test: ## Run the test suite
	$(BIN)/pytest -q

lint: ## Check style and common mistakes
	$(BIN)/ruff check .

fmt: ## Apply the safe lint fixes
	$(BIN)/ruff check --fix .

schema: ## Apply schema.sql and the migrations to $$DATABASE_URL
	@test -n "$(DATABASE_URL)" || { echo "set DATABASE_URL"; exit 1; }
	psql "$(DATABASE_URL)" -v ON_ERROR_STOP=1 -f Database/schema.sql
	@for f in Database/migrations/*.sql; do \
	  [ -e "$$f" ] || continue; psql "$(DATABASE_URL)" -v ON_ERROR_STOP=1 -f "$$f"; \
	done

docker-build: ## Build the container image
	docker compose build

docker-up: ## Start the server and PostgreSQL
	docker compose up -d

docker-down: ## Stop the stack
	docker compose down

docker-logs: ## Follow the server logs
	docker compose logs -f server

clean: ## Remove caches and the venv
	rm -rf $(VENV) .pytest_cache .ruff_cache
	find . -name __pycache__ -type d -prune -exec rm -rf {} +

.PHONY: help install run test lint fmt schema docker-build docker-up docker-down docker-logs clean
