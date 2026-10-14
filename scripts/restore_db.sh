#!/bin/sh
# ==============================================================================
# n8n Database Restore Script
# Restores PostgreSQL database from a compressed backup file (.sql.gz)
# ==============================================================================

set -e

BACKUP_FILE="$1"
DB_USER="${DB_POSTGRESDB_USER:-n8n_user}"
DB_NAME="${DB_POSTGRESDB_DATABASE:-n8n_db}"
PG_HOST="${DB_POSTGRESDB_HOST:-postgres}"

if [ -z "$BACKUP_FILE" ]; then
    echo "Usage: $0 <path_to_backup.sql.gz>"
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

echo "Checking PostgreSQL connection to $PG_HOST as $DB_USER..."
pg_isready -h "$PG_HOST" -U "$DB_USER" -d "$DB_NAME" || {
    echo "Error: PostgreSQL is not reachable."
    exit 1
}

echo "Starting restore of database '$DB_NAME' from '$BACKUP_FILE'..."

# Terminate existing connections to allow drop/recreate or clean restore
psql -h "$PG_HOST" -U "$DB_USER" -d "$DB_NAME" -c "
SELECT pg_terminate_backend(pid) FROM pg_stat_activity 
WHERE datname = '$DB_NAME' AND pid <> pg_backend_pid();" > /dev/null 2>&1 || true

# Stream gunzip to psql
gunzip -c "$BACKUP_FILE" | psql -h "$PG_HOST" -U "$DB_USER" -d "$DB_NAME" --quiet

echo "PostgreSQL restore completed successfully."

# Verification check: count tables
TABLE_COUNT=$(psql -h "$PG_HOST" -U "$DB_USER" -d "$DB_NAME" -t -c "SELECT count(*) FROM information_schema.tables WHERE table_schema='public';")
echo "Verification: $TABLE_COUNT public tables verified in '$DB_NAME'."
echo "Database restore finished successfully."
