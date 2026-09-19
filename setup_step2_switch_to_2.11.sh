#!/usr/bin/env bash
# Switch the local WSL install from CKAN 2.12.0 to CKAN 2.11.6 (decision 2026-09-18,
# see docs/roadmap.md). Run it INSIDE your WSL Ubuntu terminal. No sudo needed.
# Interactive on purpose: it asks once before deleting anything, opens nano so you can
# put the DB password into ckan.ini, and asks for the new admin password.
# Safe to re-run: finished steps are detected and skipped.
#
# Before running: start Docker Desktop (WSL Integration on for Ubuntu) and stop `ckan run`.
# Usage (from a WSL Ubuntu shell):
#   bash /mnt/c/Users/Tlinh/ckan_customized/setup_step2_switch_to_2.11.sh
set -euo pipefail

CKAN_VERSION=2.11.6
CKAN_TAG=ckan-$CKAN_VERSION
SOLR_IMAGE=ckan/ckan-solr:2.11-solr9
VENV=$HOME/ckan/default
INI=$HOME/ckan/etc/ckan.ini
BACKUP_DIR=$HOME/ckan/backup
THEME=/mnt/c/Users/Tlinh/ckan_customized/ckanext-evntheme   # theme since 2026-09-19 (was ckanext-lakehouse_theme)
SAMPLE_DB_URL=postgresql://ckan_default:pass@localhost/ckan_default   # what `ckan generate config` writes
STAMP=$(date +%Y%m%d-%H%M%S)

say() { printf '\n== %s\n' "$*"; }
installed_version() { "$VENV/bin/pip" show ckan 2>/dev/null | awk '/^Version:/ {print $2}'; }
db_url() { grep -E '^sqlalchemy\.url' "$INI" | cut -d= -f2- | tr -d ' '; }
solr_ok() { curl -fs 'http://localhost:8983/solr/ckan/admin/ping?wt=json' | grep -q '"OK"'; }

unset CKAN_INI   # `ckan config-tool` / `generate` must not load an app (no DB password yet)
cd "$HOME"

say "0. Checks"
command -v docker >/dev/null || { echo "docker not found: start Docker Desktop (WSL Integration on) and re-run."; exit 1; }
if pgrep -f 'ckan -c .*\.ini run' >/dev/null; then echo "Stop 'ckan run' first."; exit 1; fi

cat <<EOF
This switches the local install to CKAN $CKAN_VERSION. It will:
  - delete and rebuild the venv $VENV (now: CKAN $(installed_version || true))
  - save $INI to $BACKUP_DIR, then regenerate it with CKAN $CKAN_VERSION
    (only while it still has the sample DB password, so nothing you typed is lost)
  - replace the Solr container ckan-solr and its volume ckan_solr_data with $SOLR_IMAGE
  - back up DB ckan_default with pg_dump to $BACKUP_DIR, then drop all its tables and
    create the $CKAN_VERSION schema (demo org/dataset and user admin are recreated later)
Uploaded files in ~/ckan/storage are kept.
EOF
read -r -p "Continue? [y/N] " answer
[[ $answer == [yY] ]] || exit 1
mkdir -p "$BACKUP_DIR" && chmod 700 "$BACKUP_DIR"

say "1. CKAN $CKAN_VERSION from source in $VENV"
if [ "$(installed_version || true)" != "$CKAN_VERSION" ]; then
  rm -rf "$VENV"
  python3 -m venv "$VENV"
  "$VENV/bin/pip" install --upgrade pip setuptools wheel
  git clone --depth 1 --branch "$CKAN_TAG" https://github.com/ckan/ckan.git "$VENV/src/ckan"
else
  echo "Already on $CKAN_VERSION: only re-checking requirements"
fi
export PATH="$VENV/bin:$PATH"
pip install -e "$VENV/src/ckan[requirements]"
pip install -r "$VENV/src/ckan/dev-requirements.txt"   # debug = true needs flask-debugtoolbar
pip install -e "$THEME"
pip check || echo "WARNING: pip check reported the problems above"
pybabel compile -d "$THEME/ckanext/evntheme/i18n" -D ckanext-evntheme

say "2. $INI"
if [ ! -f "$INI" ] || [ "$(db_url)" = "$SAMPLE_DB_URL" ]; then
  [ -f "$INI" ] && cp -p "$INI" "$BACKUP_DIR/ckan.ini.before-$CKAN_VERSION.$STAMP"
  ckan generate config "$INI"   # overwrites without asking
else
  echo "Keeping the existing file (sqlalchemy.url already has your password); re-applying the keys below"
fi
# Same values as the config mapping table in docs/phase-2-docker-packaging.md
ckan config-tool "$INI" \
  "ckan.site_url = http://localhost:5000" \
  "solr_url = http://127.0.0.1:8983/solr/ckan" \
  "ckan.redis.url = redis://localhost:6379/0" \
  "ckan.storage_path = $HOME/ckan/storage" \
  "ckan.plugins = evntheme activity tracking text_view image_view" \
  "ckan.base_templates_folder = templates" \
  "ckan.base_public_folder = public" \
  "ckan.locale_default = vi" \
  "ckan.locales_offered = vi en" \
  "ckan.site_title = Cổng dữ liệu EVN" \
  "ckan.site_description = Chia sẻ dữ liệu dùng chung toàn Tập đoàn" \
  "ckan.favicon = /evntheme/images/favicon.svg" \
  "ckanext.evntheme.domain_groups = kinh-doanh-dvkh ky-thuat-an-toan dau-tu-xay-dung tai-chinh-vat-tu to-chuc-nhan-su"
ckan config-tool "$INI" -s DEFAULT "debug = true"
chmod 600 "$INI"
if [ "$(db_url)" = "$SAMPLE_DB_URL" ]; then
  line=$(grep -n '^sqlalchemy\.url' "$INI" | cut -d: -f1)
  echo "Put the real ckan_default DB password into sqlalchemy.url (line $line)."
  echo "URL-encode @ : / # % ? in the password (for example @ -> %40). Save with Ctrl+O, quit with Ctrl+X."
  read -r -p "Press Enter to open nano... " _
  nano "+$line" "$INI"
fi
[ "$(db_url)" != "$SAMPLE_DB_URL" ] || { echo "sqlalchemy.url still has the sample password. Re-run when ready."; exit 1; }
psql "$(db_url)" -tAc 'select 1' >/dev/null || { echo "Cannot log in with sqlalchemy.url. Fix it in $INI and re-run."; exit 1; }

say "3. Solr ($SOLR_IMAGE)"
# First, before any `ckan -c`: 2.11 refuses a Solr core with the 2.12 schema (SearchError).
if [ "$(docker inspect -f '{{.Config.Image}}' ckan-solr 2>/dev/null || true)" != "$SOLR_IMAGE" ]; then
  docker rm -f ckan-solr >/dev/null 2>&1 || true
  docker volume rm ckan_solr_data >/dev/null 2>&1 || true   # holds the 2.12 core config and index
  docker run -d --name ckan-solr --restart unless-stopped \
    -p 8983:8983 -v ckan_solr_data:/var/solr "$SOLR_IMAGE"
else
  docker start ckan-solr >/dev/null
fi
for _ in $(seq 1 30); do solr_ok && break; sleep 2; done
solr_ok || { echo "Solr core 'ckan' does not answer on :8983. Check: docker logs ckan-solr"; exit 1; }
echo "Solr OK"

say "4. Database ckan_default"
URL=$(db_url)
if [ "$(psql "$URL" -tAc "select to_regclass('public.file_owner') is not null")" = t ]; then
  # file_owner only exists in the 2.12 schema (migration 109); 2.11 cannot migrate from there.
  dump="$BACKUP_DIR/ckan_default-2.12.0-$STAMP.dump"
  pg_dump "$URL" -Fc -f "$dump"
  echo "Backup: $dump"
  ckan -c "$INI" db clean --yes || true
  if [ "$(psql "$URL" -tAc "select count(*) from pg_tables where schemaname = 'public'")" != 0 ]; then
    echo "db clean left tables behind: dropping schema public (ckan_default owns this DB)"
    psql "$URL" -v ON_ERROR_STOP=1 -c 'DROP SCHEMA public CASCADE; CREATE SCHEMA public;'
  fi
fi
ckan -c "$INI" db init
for plugin in activity tracking evntheme; do   # db init does not migrate plugin tables
  ckan -c "$INI" db upgrade -p "$plugin"
done
ckan -c "$INI" db pending-migrations
ckan -c "$INI" search-index rebuild

say "5. Sysadmin admin"
if [ "$(psql "$URL" -tAc "select count(*) from \"user\" where name = 'admin' and sysadmin")" = 0 ]; then
  ckan -c "$INI" sysadmin add admin email=admin@localhost name=admin   # asks for a password
else
  echo "admin already exists"
fi

say "Done: CKAN $(installed_version) + $SOLR_IMAGE"
echo "Start the portal with:  ckan -c $INI run   (then open http://localhost:5000)"
echo "Demo content (optional):  ckan -c $INI evntheme seed-demo"
