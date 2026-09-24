#!/usr/bin/env bash
# Write docker/.env from .env.example, generating every password and secret.
# Run it once before the first `docker compose up`:
#   bash docker/make-env.sh
# It never overwrites an existing .env (that would invalidate the database password,
# every session and every API token at once).
set -euo pipefail
cd "$(dirname "$0")"

if [ -e .env ]; then
    echo ".env already exists. Delete it yourself if you really want new secrets:"
    echo "  rm docker/.env   # the db volume keeps the OLD password: docker compose down -v"
    exit 1
fi

python3 - <<'PY'
import pathlib
import re
import secrets

# token_urlsafe only produces letters, digits, - and _, all of which are safe inside
# the userinfo part of a postgresql:// URL, so no percent-encoding is needed (gotchas 6e).
jwt = "string:" + secrets.token_urlsafe(32)
values = {
    "POSTGRES_PASSWORD": secrets.token_urlsafe(24),
    "CKAN_DB_PASSWORD": secrets.token_urlsafe(24),
    "DATASTORE_RO_PASSWORD": secrets.token_urlsafe(24),
    "CKAN_SYSADMIN_PASSWORD": secrets.token_urlsafe(12),
    "CKAN___SECRET_KEY": secrets.token_urlsafe(32),
    "CKAN___WTF_CSRF_SECRET_KEY": secrets.token_urlsafe(32),
    "CKAN___API_TOKEN__JWT__ENCODE__SECRET": jwt,
    "CKAN___API_TOKEN__JWT__DECODE__SECRET": jwt,
}

lines = pathlib.Path(".env.example").read_text(encoding="utf-8").splitlines()
out, filled = [], set()
for line in lines:
    match = re.match(r"^([A-Z0-9_]+)=(.*)$", line)
    if match and match.group(1) in values and match.group(2) in ("change-me", "generate-me",
                                                                "string:generate-me"):
        out.append(f"{match.group(1)}={values[match.group(1)]}")
        filled.add(match.group(1))
    else:
        out.append(line)

missing = set(values) - filled
if missing:
    raise SystemExit(f".env.example no longer has a placeholder for: {', '.join(sorted(missing))}")

pathlib.Path(".env").write_text("\n".join(out) + "\n", encoding="utf-8")
print(f"docker/.env written, {len(filled)} generated values")
PY

chmod 600 .env
echo "Sysadmin password (keep it, it is only in docker/.env):"
grep '^CKAN_SYSADMIN_PASSWORD=' .env
