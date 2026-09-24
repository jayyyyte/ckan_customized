#!/bin/bash
# Sourced (`. "$f"`) by /srv/app/start_ckan.sh after prerun.py, so: no `set -e` — it would
# leak into the parent shell — and an `exit` here stops the whole startup, which is what
# we want for a failed migration: CKAN must not serve on an out-of-date schema.
#
# prerun.py runs `ckan db init` only, which upgrades core but no plugin (gotchas 6h).
# Upgrade just the plugins that ship ckanext/<name>/migration/<name>/: xloader has none
# and dies with "No 'script_location' key found in configuration" (gotchas 6al).
for _plugin in activity tracking evntheme; do
    echo "[entrypoint] ckan db upgrade -p ${_plugin}"
    if ! ckan -c "$CKAN_INI" db upgrade -p "$_plugin"; then
        echo "[entrypoint] db upgrade -p ${_plugin} failed — not starting CKAN" >&2
        exit 1
    fi
done
unset _plugin
