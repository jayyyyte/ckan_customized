#!/usr/bin/env bash
# CKAN's roles and databases on the shared postgres-service (phase-3 §3.3), with the
# names and passwords of k8s/overlays/<overlay>/secrets.env:
#   ckan_default       LOGIN; owns both databases
#   datastore_default  LOGIN; gets SELECT-only rights on the DataStore later, when prerun.py
#                      runs `datastore set-permissions` as ckan_default. That works without
#                      a superuser only because ckan_default owns the database (gotchas 15e).
#
#   bash k8s/scripts/prepare-postgres.sh --context <ctx> <overlay>           # look only
#   bash k8s/scripts/prepare-postgres.sh --context <ctx> <overlay> --apply   # create
#   bash k8s/scripts/prepare-postgres.sh --print <overlay> > ckan-db.sql     # no cluster
# --print writes the same SQL for the database owner to run with psql, when this
# kubeconfig may not `exec`: it holds SCRAM verifiers only, never a password.
# Env: NAMESPACE (default lakehouse), PG_TARGET (default svc/postgres-service).
#
# The server is shared, so:
# - it only CREATEs what is missing. An existing role or database is reported and left
#   alone: never ALTERed, never dropped.
# - no password travels in clear. It sends SCRAM-SHA-256 verifiers computed here, over
#   stdin: nothing in the kubectl command line (which the API server may audit-log) and
#   nothing a statement log on the Postgres side could reveal.
set -euo pipefail

usage() { sed -n '2,/^set -euo/p' "$0" | sed '$d; s/^# \{0,1\}//'; exit 1; }

ctx="" overlay="" apply=no print=no
while [ $# -gt 0 ]; do
    case "$1" in
        --context) ctx="${2:-}"; shift 2 ;;
        --apply) apply=yes; shift ;;
        --print) print=yes; shift ;;
        -h|--help) usage ;;
        *) overlay="$1"; shift ;;
    esac
done
[ -n "$overlay" ] && { [ -n "$ctx" ] || [ "$print" = yes ]; } || usage

secrets_env="$(cd "$(dirname "$0")/.." && pwd)/overlays/$overlay/secrets.env"
[ -r "$secrets_env" ] || { echo "No $secrets_env — run make-secrets.sh $overlay first" >&2; exit 1; }

namespace="${NAMESPACE:-lakehouse}"
target="${PG_TARGET:-svc/postgres-service}"
if [ "$print" = no ]; then
    server=$(kubectl config view --minify --context "$ctx" -o jsonpath='{.clusters[0].cluster.server}')
    echo "context $ctx ($server), $namespace/$target, mode: $([ $apply = yes ] && echo APPLY || echo check only)"
fi

# psql as the container's own superuser over the local socket (trust in the official
# image), so no superuser password is needed either.
psql_in_pod() {
    kubectl --context "$ctx" -n "$namespace" exec -i "$target" -- \
        sh -c 'exec psql -X -q -v ON_ERROR_STOP=1 -U "${POSTGRES_USER:-postgres}" -d postgres'
}

# $1 = check|apply. The SQL is printed on stdout, secrets never leave this process
# except as SCRAM verifiers.
make_sql() {
    python3 - "$secrets_env" "$1" <<'PY'
import base64
import hashlib
import hmac
import re
import secrets
import sys
from urllib.parse import unquote, urlsplit

path, mode = sys.argv[1:3]
env = {}
for line in open(path, encoding="utf-8"):
    match = re.match(r"^([A-Z0-9_]+)=(.*)$", line.rstrip("\r\n"))
    if match:
        env[match.group(1)] = match.group(2)

def parts(key):
    url = urlsplit(env[key])
    return unquote(url.username or ""), unquote(url.password or ""), url.path.lstrip("/")

ckan_user, ckan_pw, ckan_db = parts("CKAN_SQLALCHEMY_URL")
write_user, write_pw, ds_db = parts("CKAN_DATASTORE_WRITE_URL")
ro_user, ro_pw, ro_db = parts("CKAN_DATASTORE_READ_URL")
if (write_user, write_pw) != (ckan_user, ckan_pw) or ro_db != ds_db:
    sys.exit("secrets.env: the DataStore write URL must use the CKAN user and password, "
             "and both DataStore URLs the same database")
for name in (ckan_user, ro_user, ckan_db, ds_db):
    if not re.fullmatch(r"[a-z_][a-z0-9_]*", name):
        sys.exit(f"secrets.env: unexpected role/database name {name!r}")
for pw in (ckan_pw, ro_pw):
    # ASCII only: the verifier below skips SASLprep, which ASCII does not need.
    if not re.fullmatch(r"[A-Za-z0-9_-]{16,}", pw):
        sys.exit("secrets.env: passwords must be 16+ URL-safe characters (make-secrets.sh)")

def scram(password, iterations=4096):
    """The verifier PostgreSQL itself stores for password_encryption = scram-sha-256."""
    salt = secrets.token_bytes(16)
    salted = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, iterations)
    stored_key = hashlib.sha256(hmac.new(salted, b"Client Key", "sha256").digest()).digest()
    server_key = hmac.new(salted, b"Server Key", "sha256").digest()
    b64 = lambda raw: base64.b64encode(raw).decode()
    return f"SCRAM-SHA-256${iterations}:{b64(salt)}${b64(stored_key)}:{b64(server_key)}"

roles = f"('{ckan_user}'), ('{ro_user}')"
dbs = f"('{ckan_db}'), ('{ds_db}')"
print(r"\pset footer off")
if mode == "apply":
    for role, pw in ((ckan_user, ckan_pw), (ro_user, ro_pw)):
        print(f"SELECT format('CREATE ROLE %I LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE "
              f"PASSWORD %L', '{role}', '{scram(pw)}') "
              f"WHERE NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = '{role}') \\gexec")
    for db in (ckan_db, ds_db):
        print(f"SELECT format('CREATE DATABASE %I OWNER %I ENCODING %L TEMPLATE template0', "
              f"'{db}', '{ckan_user}', 'UTF8') "
              f"WHERE NOT EXISTS (SELECT 1 FROM pg_database WHERE datname = '{db}') \\gexec")
print(r"\echo '--- server'")
print("SELECT current_setting('server_version') AS server_version, current_user AS psql_user,"
      " (SELECT rolsuper FROM pg_roles WHERE rolname = current_user) AS superuser;")
print(r"\echo '--- roles'")
print(f"SELECT r.name AS role, p.rolname IS NOT NULL AS exists, p.rolcanlogin AS login, "
      f"p.rolsuper AS superuser FROM (VALUES {roles}) r(name) "
      f"LEFT JOIN pg_roles p ON p.rolname = r.name;")
print(r"\echo '--- databases (owner must be " + ckan_user + r", gotchas 15e)'")
print(f"SELECT d.name AS database, db.datname IS NOT NULL AS exists, "
      f"pg_get_userbyid(db.datdba) AS owner, pg_encoding_to_char(db.encoding) AS encoding "
      f"FROM (VALUES {dbs}) d(name) LEFT JOIN pg_database db ON db.datname = d.name;")
PY
}

if [ "$print" = yes ]; then
    echo "-- CKAN roles and databases, generated by k8s/scripts/prepare-postgres.sh --print"
    echo "-- Run as a superuser: psql -X -v ON_ERROR_STOP=1 -d postgres -f <this file>"
    echo "-- Creates only what is missing; the passwords are SCRAM-SHA-256 verifiers."
    make_sql apply
    exit 0
fi

if [ "$apply" = yes ]; then
    echo "Creating the missing roles/databases (existing ones are left untouched)…"
fi
make_sql "$([ $apply = yes ] && echo apply || echo check)" | psql_in_pod

cat <<'EOF'

Expected: both roles exist with login and without superuser; both databases exist, owned
by ckan_default, UTF8; server_version 15 or later (the owner trick of gotchas 15e).
A role that existed before this script keeps its old password: if it differs from
secrets.env, CKAN cannot log in — sort that out with the database owner, not here.
EOF
