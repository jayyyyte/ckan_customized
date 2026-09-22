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
# Percent-encode a password so it is safe inside a postgresql:// URL (gotcha 6e).
urlenc() { python3 -c 'import sys, urllib.parse; print(urllib.parse.quote(sys.argv[1], safe=""))' "$1"; }
# The password already stored in sqlalchemy.url, kept encoded as it is written there.
ini_password() { python3 -c 'import sys, urllib.parse; print(urllib.parse.urlsplit(sys.argv[1]).password or "")' "$1"; }
read_password() {  # read_password VARNAME PROMPT
  local __var=$1 __prompt=$2 p1 p2
  while :; do
    read -rs -p "$__prompt: " p1; echo
    read -rs -p "Repeat it: " p2; echo
    if [ -z "$p1" ]; then echo "Empty, try again."; continue; fi
    if [ "$p1" != "$p2" ]; then echo "The two entries differ, try again."; continue; fi
    break
  done
  printf -v "$__var" '%s' "$p1"
}

export PATH="$VENV/bin:$PATH"
cd "$HOME"

say "0. Checks"
[ -f "$INI" ] || { echo "$INI not found: run setup_step2_switch_to_2.11.sh first."; exit 1; }
if pgrep -f 'ckan -c .*\.ini run' >/dev/null; then echo "Stop 'ckan run' first."; exit 1; fi
mkdir -p "$BACKUP_DIR" && chmod 700 "$BACKUP_DIR"
cp -p "$INI" "$BACKUP_DIR/ckan.ini.before-datastore.$STAMP"
echo "Backup: $BACKUP_DIR/ckan.ini.before-datastore.$STAMP"

say "1. Postgres: DataStore database and read-only role (sudo)"
# The password is (re)set on every run: a re-run must not depend on remembering
# the password picked by an earlier run. psql's :'var' quotes it safely, but only
# for SQL read from stdin: with -c the string goes to the server unsubstituted.
read_password DS_PASSWORD "Choose a password for the read-only role datastore_default"
if role_exists datastore_default; then
  printf '%s\n' "alter role datastore_default password :'pw';" | psql_admin -v pw="$DS_PASSWORD" >/dev/null
  echo "Role datastore_default already existed: password reset."
else
  printf '%s\n' "create role datastore_default login nosuperuser nocreatedb nocreaterole password :'pw';" \
    | psql_admin -v pw="$DS_PASSWORD" >/dev/null
fi
db_exists datastore_default || sudo -u postgres createdb -O ckan_default datastore_default -E utf-8

say "2. Postgres: test databases for the extension's app tests (sudo)"
db_exists ckan_test || sudo -u postgres createdb -O ckan_default ckan_test -E utf-8
db_exists datastore_test || sudo -u postgres createdb -O ckan_default datastore_test -E utf-8

say "3. ckan.ini: DataStore URLs"
# write_url uses ckan_default, the same role (and password) as sqlalchemy.url.
CKAN_DB_PASSWORD=$(ini_password "$(ini_value sqlalchemy.url)")
[ -n "$CKAN_DB_PASSWORD" ] || { echo "No password found in sqlalchemy.url of $INI."; exit 1; }
ckan config-tool "$INI" \
  "ckan.datastore.write_url = postgresql://ckan_default:$CKAN_DB_PASSWORD@localhost/datastore_default" \
  "ckan.datastore.read_url = postgresql://datastore_default:$(urlenc "$DS_PASSWORD")@localhost/datastore_default"
unset CKAN_DB_PASSWORD DS_PASSWORD
psql "$(ini_value ckan.datastore.write_url)" -tAc 'select 1' >/dev/null \
  || { echo "Cannot log in with ckan.datastore.write_url (check sqlalchemy.url in $INI)."; exit 1; }
psql "$(ini_value ckan.datastore.read_url)" -tAc 'select 1' >/dev/null \
  || { echo "Cannot log in with ckan.datastore.read_url."; exit 1; }

say "4. XLoader $XLOADER_VERSION"
# From source with -e, like CKAN's docs and ckan-docker: a wheel installs into
# site-packages/ckanext/, which this venv never looks at, so `import ckanext.xloader`
# fails (gotcha 6ak). The requirements of the same tag are pinned by the XLoader README.
XLOADER_SRC=$VENV/src/ckanext-xloader
if [ ! -e "$XLOADER_SRC/setup.py" ]; then
  rm -rf "$XLOADER_SRC"
  git clone --depth 1 --branch "$XLOADER_VERSION" https://github.com/ckan/ckanext-xloader.git "$XLOADER_SRC"
fi
pip uninstall -y ckanext-xloader >/dev/null 2>&1 || true   # drop a wheel left by an older run
pip install -e "$XLOADER_SRC" -r "$XLOADER_SRC/requirements.txt"
python -c 'import ckanext.xloader' \
  || { echo "ckanext.xloader still not importable: see gotcha 6ak."; exit 1; }
pip check || echo "WARNING: pip check reported the problems above"

say "5. Plugins and permissions"
ckan config-tool "$INI" "ckan.plugins = $PLUGINS"
ckan -c "$INI" datastore set-permissions | sudo -u postgres psql --set ON_ERROR_STOP=1 >/dev/null
# Only plugins that ship an alembic tree can be upgraded: for the others CKAN builds
# an alembic config without script_location and dies (xloader keeps no CKAN-side
# tables of its own, it writes into the DataStore database).
has_migrations() {
  python - "$1" <<'PY'
import importlib.util, os, sys
name = sys.argv[1]
spec = importlib.util.find_spec("ckanext." + name)
# origin is None for a package without __init__.py, so read the search locations too.
roots = list(spec.submodule_search_locations or []) if spec else []
if spec and spec.origin:
    roots.append(os.path.dirname(spec.origin))
sys.exit(0 if any(os.path.isdir(os.path.join(r, "migration", name)) for r in roots) else 1)
PY
}
for plugin in activity tracking evntheme xloader; do
  if has_migrations "$plugin"; then
    ckan -c "$INI" db upgrade -p "$plugin"
  else
    echo "$plugin: no alembic migrations, nothing to upgrade"
  fi
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
