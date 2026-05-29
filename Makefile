.PHONY: help install dev run test lint format typecheck check clean docker-build docker-up docker-down indexes

help: ## Show this help
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-20s\033[0m %s\n", $$1, $$2}'

install: ## Install all dependencies via Poetry
	poetry install --with dev

dev: ## Run the API locally with hot reload
	poetry run uvicorn src.main:app --reload --host 0.0.0.0 --port 8000

run: ## Run the API in production mode (gunicorn + uvicorn workers)
	poetry run gunicorn src.main:app -k uvicorn.workers.UvicornWorker -w 4 -b 0.0.0.0:8000

test: ## Run the test suite
	poetry run pytest

lint: ## Lint the codebase with ruff
	poetry run ruff check src

format: ## Format the codebase with ruff
	poetry run ruff format src

typecheck: ## Run static type checking with pyright
	poetry run pyright

check: lint typecheck test ## Run all quality gates

clean: ## Remove caches and build artifacts
	find . -type d \( -name __pycache__ -o -name .pytest_cache -o -name .ruff_cache -o -name .pyright \) -exec rm -rf {} + 2>/dev/null || true
	rm -rf .coverage coverage.xml htmlcov build dist *.egg-info

docker-build: ## Build the production Docker image
	docker compose build

docker-up: ## Start the full stack (api + mongo + redis)
	docker compose up -d

docker-down: ## Stop the stack
	docker compose down

docker-logs: ## Tail logs
	docker compose logs -f api

indexes: ## Create MongoDB indexes (idempotent)
	poetry run python -m src.scripts.create_indexes

seed: ## Seed development data
	poetry run python -m src.scripts.seed_dev
