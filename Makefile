.PHONY: help lint test test-cov export audit-env up down backup restore clean

help:
	@echo "Available commands:"
	@echo "  make lint       - Run custom python workflow linter with color output"
	@echo "  make test       - Run Python unit test suite via pytest"
	@echo "  make audit-env  - Audit .env file against .env.example security rules"
	@echo "  make export     - Export workflows from running n8n instance"
	@echo "  make up         - Spin up Docker Compose stack"
	@echo "  make down       - Spin down Docker Compose stack"
	@echo "  make backup     - Manually trigger postgres database backup"
	@echo "  make clean      - Remove python temporary cache files"

lint:
	python scripts/lint_workflows.py workflows/

test:
	pytest

audit-env:
	python scripts/validate_env.py --env-file .env --example-file .env.example

export:
	python scripts/export_workflows.py --output-dir workflows/

up:
	docker compose up -d

down:
	docker compose down

backup:
	docker compose exec -t postgres pg_dump -U n8n_user -d n8n_db > manual_backup.sql
	gzip -9 manual_backup.sql

clean:
	python -c "import pathlib; [p.unlink() for p in pathlib.Path('.').rglob('*.pyc')]"
	python -c "import pathlib, shutil; [shutil.rmtree(p) for p in pathlib.Path('.').rglob('__pycache__')]"
	python -c "import pathlib, shutil; [shutil.rmtree(p) for p in pathlib.Path('.').rglob('.pytest_cache')]"
