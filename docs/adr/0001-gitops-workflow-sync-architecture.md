# ADR 0001: GitOps Workflow Synchronization Architecture

## Status
Accepted

## Context
Self-hosted n8n instances persist workflows directly inside a PostgreSQL database. Managing workflows exclusively via the UI poses severe operational hazards:
- Lack of code review and pull request gates.
- No automated linting for hardcoded plaintext credentials or broken node connections.
- Risk of accidental overwrites and lack of instant rollback mechanisms.

## Decision
We adopt a declarative GitOps synchronization workflow:
1. **Source of Truth:** Git repository (`workflows/*.json`) is the canonical source of truth for production workflows.
2. **Automated Verification:** Pull requests trigger linting (`scripts/lint_workflows.py`), checking for secret leakage, unauthenticated webhooks, and missing timeouts.
3. **Continuous Deployment:** On merge to production branches, `scripts/deploy_workflows.py` compares local workflows with target n8n API endpoints:
   - Remote workflows are backed up prior to overwriting (`--backup-dir`).
   - Git commit SHAs and deployment timestamps are stamped into workflow metadata.
   - Idempotent `POST` / `PUT` operations ensure seamless updates.
4. **Bidirectional Sync:** Developers who iterate in staging UI can export back to Git via `scripts/export_workflows.py`.

## Consequences
- **Positive:** Full auditability, automated rollback capability, and elimination of credential leaks in version control.
- **Negative:** Direct manual changes made on production n8n instances without exporting back to Git will be overwritten on subsequent pipeline deployments.
