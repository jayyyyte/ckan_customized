#!/bin/bash
# Runs once, as the postgres superuser, the first time the data directory is created
# (/docker-entrypoint-initdb.d of the postgres image). Editing it later has no effect
# until the volume is recreated: docker compose down -v.
#
# Same layout as the local install (setup_step1_system.sh + setup_step3_datastore.sh) and
# as the two databases phase 3 will add to the shared postgres-service:
#   ckan_default       main CKAN database, owned by the ckan_default role
#   datastore_default  DataStore: written by ckan_default, read by datastore_default
#
# The read-only role gets its SELECT-only rights from `ckan datastore set-permissions`,
# which prerun.py runs in the CKAN container over CKAN_DATASTORE_WRITE_URL. That works
# without a superuser because ckan_default owns both databases, and since PostgreSQL 15
# the owner of a database also controls its public schema (pg_database_owner).
set -euo pipefail

: "${CKAN_DB_PASSWORD:?CKAN_DB_PASSWORD is not set}"
: "${DATASTORE_RO_PASSWORD:?DATASTORE_RO_PASSWORD is not set}"

# psql substitutes :'var' only for SQL read from stdin or -f, never for -c (gotchas 6aj).
# :'var' also quotes and escapes, so a password containing a quote survives.
psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname postgres \
     -v ckan_pw="$CKAN_DB_PASSWORD" -v ds_pw="$DATASTORE_RO_PASSWORD" <<'EOSQL'
CREATE ROLE ckan_default LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE PASSWORD :'ckan_pw';
CREATE ROLE datastore_default LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE PASSWORD :'ds_pw';
CREATE DATABASE ckan_default OWNER ckan_default;
CREATE DATABASE datastore_default OWNER ckan_default;
EOSQL

echo "[postgres-init] roles ckan_default / datastore_default and both databases created"
