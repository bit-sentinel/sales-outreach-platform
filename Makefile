# OutreachAI – Developer Helper Commands
# Usage: make <target>

.PHONY: help dev stop logs migrate test lint build deploy

help: ## Show available commands
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | awk 'BEGIN {FS = ":.*?## "}; {printf "\033[36m%-20s\033[0m %s\n", $$1, $$2}'

# ── Development ──────────────────────────────────────────────────────────────

dev: ## Start all services in development mode
	docker compose up -d
	@echo "\n✓ API:      http://localhost:8000"
	@echo "✓ Frontend: http://localhost:3000"
	@echo "✓ Flower:   http://localhost:5555"
	@echo "✓ Docs:     http://localhost:8000/docs"

stop: ## Stop all services
	docker compose down

logs: ## Tail all container logs
	docker compose logs -f

logs-api: ## Tail API logs
	docker compose logs -f api

logs-worker: ## Tail Celery worker logs
	docker compose logs -f celery-worker celery-email-worker

# ── Database ─────────────────────────────────────────────────────────────────

migrate: ## Run Alembic migrations
	docker compose exec api alembic upgrade head

migrate-create: ## Create a new migration (usage: make migrate-create MSG="add users table")
	docker compose exec api alembic revision --autogenerate -m "$(MSG)"

migrate-down: ## Rollback last migration
	docker compose exec api alembic downgrade -1

db-shell: ## Open psql shell
	docker compose exec postgres psql -U outreach outreachai

# ── Testing ──────────────────────────────────────────────────────────────────

test: ## Run all backend tests
	docker compose exec api python -m pytest tests/ -v

test-cov: ## Run tests with coverage report
	docker compose exec api python -m pytest tests/ --cov=app --cov-report=term-missing

test-frontend: ## Run frontend tests
	docker compose exec frontend npm test

# ── Code Quality ─────────────────────────────────────────────────────────────

lint: ## Lint backend code
	cd backend && ruff check . && ruff format --check .

lint-fix: ## Auto-fix lint issues
	cd backend && ruff check --fix . && ruff format .

# ── Build & Deploy ───────────────────────────────────────────────────────────

build: ## Build production Docker images
	docker build -t outreachai/api:latest ./backend
	docker build -t outreachai/frontend:latest ./frontend

deploy-staging: ## Deploy to staging (requires kubectl configured)
	kubectl apply -f infra/k8s/ -n outreachai
