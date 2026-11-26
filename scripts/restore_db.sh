#!/bin/sh
# ==============================================================================
# n8n Database Restore Script
# Restores PostgreSQL database from a compressed backup file (.sql.gz)
# ==============================================================================

set -eu

DRY_RUN=0
BACKUP_FILE=""

for arg in "$@"; do
    case "$arg" in
        --dry-run)
            DRY_RUN=1
            ;;
        -h|--help)
            echo "Usage: $0 [--dry-run] <path_to_backup.sql.gz>"
            exit 0
            ;;
        *)
            BACKUP_FILE="$arg"
            ;;
    esac
done

DB_USER="${DB_POSTGRESDB_USER:-n8n_user}"
DB_NAME="${DB_POSTGRESDB_DATABASE:-n8n_db}"
PG_HOST="${DB_POSTGRESDB_HOST:-postgres}"
PG_PORT="${DB_POSTGRESDB_PORT:-5432}"
export PGPASSWORD="${DB_POSTGRESDB_PASSWORD:-${PGPASSWORD:-}}"

if [ -z "$BACKUP_FILE" ]; then
    echo "Usage: $0 [--dry-run] <path_to_backup.sql.gz>"
    echo "Example: $0 /backups/n8n_db_backup_20260821_120000.sql.gz"
    exit 1
fi

if [ ! -f "$BACKUP_FILE" ]; then
    echo "Error: Backup file '$BACKUP_FILE' does not exist."
    exit 1
fi

echo "Verifying backup file integrity..."
gzip -t "$BACKUP_FILE"
echo "Backup archive integrity verified."

echo "Checking PostgreSQL connection to $PG_HOST:$PG_PORT as $DB_USER..."
pg_isready -h "$PG_HOST" -p "$PG_PORT" -U "$DB_USER" -d "$DB_NAME" || {
    echo "Error: PostgreSQL is not reachable."
    exit 1
}

if [ "$DRY_RUN" -eq 1 ]; then
    echo "[DRY-RUN] Archive verified and PostgreSQL reachable. Skipping destructive restore."
    exit 0
fi

echo "Starting restore of database '$DB_NAME' from '$BACKUP_FILE'..."

# Terminate existing connections to allow clean restore
psql -h "$PG_HOST" -p "$PG_PORT" -U "$DB_USER" -d "$DB_NAME" -c "
SELECT pg_terminate_backend(pid) FROM pg_stat_activity
WHERE datname = '$DB_NAME' AND pid <> pg_backend_pid();" > /dev/null 2>&1 || true

# Stream gunzip to psql with ON_ERROR_STOP
gunzip -c "$BACKUP_FILE" | psql -h "$PG_HOST" -p "$PG_PORT" -U "$DB_USER" -d "$DB_NAME" -v ON_ERROR_STOP=1 --quiet

echo "PostgreSQL restore completed successfully."

# Verification check: count tables
TABLE_COUNT=$(psql -h "$PG_HOST" -p "$PG_PORT" -U "$DB_USER" -d "$DB_NAME" -t -A -c "SELECT count(*) FROM information_schema.tables WHERE table_schema='public';")
echo "Verification: $TABLE_COUNT public tables verified in '$DB_NAME'."
echo "Database restore finished successfully."
