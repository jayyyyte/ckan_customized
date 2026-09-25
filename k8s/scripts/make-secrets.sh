#!/usr/bin/env bash
# Write k8s/overlays/<overlay>/secrets.env (the ckan-secrets Secret) from
# k8s/secrets.env.example, generating every password and secret:
#   bash k8s/scripts/make-secrets.sh lab
#   PG_HOST=postgres-service:5432 bash k8s/scripts/make-secrets.sh lab   # the default
# For the kind overlay it also writes postgres-secrets.env (superuser of the stand-in).
#
# It never overwrites: a new secrets.env means new database passwords (the roles on
# postgres-service keep the old ones), and every session and API token becomes void.
set -euo pipefail

overlay="${1:?usage: make-secrets.sh <overlay>   (lab | kind)}"
k8s_dir="$(cd "$(dirname "$0")/.." && pwd)"
dir="$k8s_dir/overlays/$overlay"
out="$dir/secrets.env"

[ -d "$dir" ] || { echo "No overlay $dir" >&2; exit 1; }
if [ -e "$out" ]; then
    echo "$out already exists. Delete it yourself if you really want new secrets —" >&2
    echo "then the roles on postgres-service need the new passwords too." >&2
    exit 1
fi

PG_HOST="${PG_HOST:-postgres-service:5432}" python3 - "$k8s_dir/secrets.env.example" "$out" <<'PY'
import os
import pathlib
import re
import secrets
import sys

example, out = map(pathlib.Path, sys.argv[1:3])
host = os.environ["PG_HOST"]

# token_urlsafe: letters, digits, - and _ only, so the passwords need no percent-encoding
# inside the postgresql:// URLs (gotchas 6e).
ckan_pw = secrets.token_urlsafe(24)
ro_pw = secrets.token_urlsafe(24)
jwt = "string:" + secrets.token_urlsafe(32)
values = {
    "CKAN_SQLALCHEMY_URL": f"postgresql://ckan_default:{ckan_pw}@{host}/ckan_default",
    "CKAN_DATASTORE_WRITE_URL": f"postgresql://ckan_default:{ckan_pw}@{host}/datastore_default",
    "CKAN_DATASTORE_READ_URL": f"postgresql://datastore_default:{ro_pw}@{host}/datastore_default",
    "CKANEXT__XLOADER__JOBS_DB__URI": f"postgresql://ckan_default:{ckan_pw}@{host}/ckan_default",
    "CKAN_SYSADMIN_PASSWORD": secrets.token_urlsafe(12),
    "CKAN___SECRET_KEY": secrets.token_urlsafe(32),
    "CKAN___WTF_CSRF_SECRET_KEY": secrets.token_urlsafe(32),
    "CKAN___API_TOKEN__JWT__ENCODE__SECRET": jwt,
    "CKAN___API_TOKEN__JWT__DECODE__SECRET": jwt,
}

lines, filled = [], set()
for line in example.read_text(encoding="utf-8").splitlines():
    match = re.match(r"^([A-Z0-9_]+)=", line)
    if match and match.group(1) in values:
        lines.append(f"{match.group(1)}={values[match.group(1)]}")
        filled.add(match.group(1))
    else:
        lines.append(line)

missing = set(values) - filled
if missing:
    raise SystemExit(f"secrets.env.example has no line for: {', '.join(sorted(missing))}")

out.write_text("\n".join(lines) + "\n", encoding="utf-8")
print(f"{out} written, {len(filled)} generated values")
PY
chmod 600 "$out"

if [ "$overlay" = kind ] && [ ! -e "$dir/postgres-secrets.env" ]; then
    python3 -c 'import secrets; print("POSTGRES_PASSWORD=" + secrets.token_urlsafe(24))' \
        > "$dir/postgres-secrets.env"
    chmod 600 "$dir/postgres-secrets.env"
    echo "$dir/postgres-secrets.env written"
fi

echo "Sysadmin password: grep CKAN_SYSADMIN_PASSWORD $out"
