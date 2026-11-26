# Production Operations Runbook

This runbook documents standard operating procedures for deploying, scaling, monitoring, and recovering the self-hosted n8n GitOps stack.

---

## 1. Pre-Deployment Checklist

1. **Audit Environment Variables:**
   ```bash
   python scripts/validate_env.py --env-file .env --example-file .env.example --strict
   ```
2. **Validate Docker Compose Configuration:**
   ```bash
   docker compose config --quiet
   ```
3. **Lint Workflows & Run Tests:**
   ```bash
   make lint
   make test-cov
   make security
   ```

---

## 2. Safe Workflow Deployment & Rollback

### Dry-Run with Remote Diff
Preview changes before mutating the production n8n instance:
```bash
python scripts/deploy_workflows.py workflows/ --lint --dry-run --diff
```

### Production Deployment with Pre-Deploy Backup
```bash
python scripts/deploy_workflows.py workflows/ --lint --backup-dir ./backups/pre-deploy
```
`global_error_handler.json` is automatically deployed first so dependent workflows always have a valid error target.

### Rollback
If a deployment introduces a regression, re-deploy the pre-deploy backup JSON:
```bash
python scripts/deploy_workflows.py ./backups/pre-deploy
```

---

## 3. Scaling to Redis Queue Mode

1. Update `.env`:
   ```env
   EXECUTIONS_MODE=queue
   ```
2. Start the stack with the `queue` profile:
   ```bash
   docker compose --profile queue up -d --scale n8n-worker=2
   ```

---

## 4. Health Monitoring

Run the stack healthcheck probe:
```bash
python scripts/healthcheck.py --pg-host localhost --redis-host localhost --json
```
n8n also exposes Prometheus metrics when `N8N_METRICS=true` is enabled in `.env`.

---

## 5. Backup & Disaster Recovery

The `db-backup` container runs `pg_dump`, compresses with `gzip -9`, verifies archive integrity with `gzip -t`, and retains 7 days of snapshots in the `n8n_db_backups` volume.

### Dry-Run Restore Verification
```bash
./scripts/restore_db.sh --dry-run /backups/n8n_db_backup_YYYYMMDD_HHMMSS.sql.gz
```

### Full Database Restore
```bash
./scripts/restore_db.sh /backups/n8n_db_backup_YYYYMMDD_HHMMSS.sql.gz
```
