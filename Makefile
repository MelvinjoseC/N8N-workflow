.PHONY: help lint lint-code format security test test-cov export deploy-dry audit-env healthcheck validate-compose up up-queue down backup clean

help:
	@echo "Available commands:"
	@echo "  make lint             - Run custom python workflow linter"
	@echo "  make lint-code        - Run Ruff static analysis on scripts and tests"
	@echo "  make format           - Auto-fix Ruff lint/import issues"
	@echo "  make security         - Run Bandit AST security scan on scripts/"
	@echo "  make test             - Run Python unit test suite via pytest"
	@echo "  make test-cov         - Run pytest with branch coverage enforcement"
	@echo "  make audit-env        - Audit .env file against .env.example security rules"
	@echo "  make healthcheck      - Probe n8n and Gotenberg health endpoints"
	@echo "  make validate-compose - Validate Docker Compose syntax"
	@echo "  make export           - Export workflows from running n8n instance"
	@echo "  make deploy-dry       - Simulate workflow deployment (dry-run + lint)"
	@echo "  make up               - Spin up Docker Compose stack"
	@echo "  make up-queue         - Spin up stack with Redis queue worker profile"
	@echo "  make down             - Spin down Docker Compose stack"
	@echo "  make backup           - Manually trigger postgres database backup"
	@echo "  make clean            - Remove python temporary cache files"

lint:
	python scripts/lint_workflows.py workflows/ --fail-on-warnings

lint-code:
	ruff check scripts/ tests/

format:
	ruff check --fix scripts/ tests/

security:
	bandit -r scripts/ -ll -c pyproject.toml

test:
	pytest

test-cov:
	pytest --cov=scripts --cov-report=term-missing --cov-fail-under=60

audit-env:
	python scripts/validate_env.py --env-file .env --example-file .env.example --strict

healthcheck:
	python scripts/healthcheck.py

validate-compose:
	docker compose config --quiet

export:
	python scripts/export_workflows.py --output-dir workflows/

deploy-dry:
	python scripts/deploy_workflows.py workflows/ --lint --dry-run

up:
	docker compose up -d

up-queue:
	docker compose --profile queue up -d

down:
	docker compose down

backup:
	docker compose exec -t postgres pg_dump -U n8n_user -d n8n_db > manual_backup.sql
	gzip -9 manual_backup.sql

clean:
	python -c "import pathlib; [p.unlink() for p in pathlib.Path('.').rglob('*.pyc')]"
	python -c "import pathlib, shutil; [shutil.rmtree(p) for p in pathlib.Path('.').rglob('__pycache__')]"
	python -c "import pathlib, shutil; [shutil.rmtree(p) for p in pathlib.Path('.').rglob('.pytest_cache')]"
