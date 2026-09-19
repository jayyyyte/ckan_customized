#!/usr/bin/env bash
# Turn on DataStore + XLoader in the local WSL install, so the dataset page's
# "Xem trước dữ liệu" and "Thử API" tabs show real rows (roadmap Q4).
# Also creates the ckan_test / datastore_test databases the extension's app tests use.
#
# Run it INSIDE your WSL Ubuntu terminal: it needs sudo (postgres) and asks for passwords.
# Safe to re-run: existing roles, databases and settings are kept.
#
# Before running: stop `ckan run`. Postgres and Solr must be up.
# Usage:
#   bash /mnt/c/Users/Tlinh/ckan_customized/setup_step3_datastore.sh
set -euo pipefail

VENV=$HOME/ckan/default
INI=$HOME/ckan/etc/ckan.ini
BACKUP_DIR=$HOME/ckan/backup
XLOADER_VERSION=2.5.0          # README compatibility table: CKAN 2.10 and 2.11 (checked 2026-09-19)
PLUGINS="evntheme activity tracking datastore xloader text_view image_view datatables_view"
STAMP=$(date +%Y%m%d-%H%M%S)

say() { printf '\n== %s\n' "$*"; }
psql_admin() { sudo -u postgres psql -v ON_ERROR_STOP=1 -tA "$@"; }
role_exists() { [ "$(psql_admin -c "select 1 from pg_roles where rolname = '$1'")" = 1 ]; }
db_exists() { [ "$(psql_admin -c "select 1 from pg_database where datname = '$1'")" = 1 ]; }
ini_value() { grep -E "^$1 *=" "$INI" | head -1 | cut -d= -f2- | sed 's/^ *//'; }

export PATH="$VENV/bin:$PATH"
cd "$HOME"

say "0. Checks"
[ -f "$INI" ] || { echo "$INI not found: run setup_step2_switch_to_2.11.sh first."; exit 1; }
if pgrep -f 'ckan -c .*\.ini run' >/dev/null; then echo "Stop 'ckan run' first."; exit 1; fi
mkdir -p "$BACKUP_DIR" && chmod 700 "$BACKUP_DIR"
cp -p "$INI" "$BACKUP_DIR/ckan.ini.before-datastore.$STAMP"
echo "Backup: $BACKUP_DIR/ckan.ini.before-datastore.$STAMP"

say "1. Postgres: DataStore database and read-only role (sudo)"
if ! role_exists datastore_default; then
  echo "Choose a password for the read-only role datastore_default (you will type it again in nano)."
  sudo -u postgres createuser -S -D -R -P -l datastore_default
fi
db_exists datastore_default || sudo -u postgres createdb -O ckan_default datastore_default -E utf-8

say "2. Postgres: test databases for the extension's app tests (sudo)"
db_exists ckan_test || sudo -u postgres createdb -O ckan_default ckan_test -E utf-8
db_exists datastore_test || sudo -u postgres createdb -O ckan_default datastore_test -E utf-8

say "3. ckan.ini: DataStore URLs"
if [ -z "$(ini_value ckan.datastore.write_url)" ]; then
  ckan config-tool "$INI" \
    "ckan.datastore.write_url = postgresql://ckan_default:CKAN_DB_PASSWORD@localhost/datastore_default" \
    "ckan.datastore.read_url = postgresql://datastore_default:DATASTORE_PASSWORD@localhost/datastore_default"
fi
if grep -qE 'CKAN_DB_PASSWORD|DATASTORE_PASSWORD' "$INI"; then
  line=$(grep -n '^ckan.datastore.write_url' "$INI" | cut -d: -f1)
  echo "Replace CKAN_DB_PASSWORD (same as in sqlalchemy.url) and DATASTORE_PASSWORD (the one you just chose)."
  echo "URL-encode @ : / # % ? (for example @ -> %40). Save with Ctrl+O, quit with Ctrl+X."
  read -r -p "Press Enter to open nano... " _
  nano "+$line" "$INI"
fi
grep -qE 'CKAN_DB_PASSWORD|DATASTORE_PASSWORD' "$INI" && { echo "Placeholders still in $INI. Re-run when ready."; exit 1; }
psql "$(ini_value ckan.datastore.read_url)" -tAc 'select 1' >/dev/null \
  || { echo "Cannot log in with ckan.datastore.read_url. Fix it in $INI and re-run."; exit 1; }

say "4. XLoader $XLOADER_VERSION"
# The wheel does not declare its dependencies: install the pinned requirements of the same tag (XLoader README).
pip install "ckanext-xloader==$XLOADER_VERSION" \
  -r "https://raw.githubusercontent.com/ckan/ckanext-xloader/$XLOADER_VERSION/requirements.txt"
pip check || echo "WARNING: pip check reported the problems above"

say "5. Plugins and permissions"
ckan config-tool "$INI" "ckan.plugins = $PLUGINS"
ckan -c "$INI" datastore set-permissions | sudo -u postgres psql --set ON_ERROR_STOP=1 >/dev/null
for plugin in activity tracking evntheme xloader; do
  ckan -c "$INI" db upgrade -p "$plugin"
done

say "6. API token used by XLoader to write into the DataStore"
if [ -z "$(ini_value ckanext.xloader.api_token)" ]; then
  token=$(ckan -c "$INI" user token add admin xloader 2>/dev/null | tail -1 | tr -d '[:space:]')
  ckan config-tool "$INI" "ckanext.xloader.api_token = $token"
  unset token
fi
chmod 600 "$INI"

say "Done"
cat <<EOF
Next, in two WSL terminals:
  ckan -c $INI jobs worker          # runs the XLoader jobs
  ckan -c $INI run                  # the portal
Then load the existing CSV files into the DataStore:
  ckan -c $INI xloader submit all
Open a dataset, tab "Xem trước dữ liệu": the table, chart and "Thử API" now use datastore_search.
EOF
