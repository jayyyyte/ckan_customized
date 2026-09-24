#!/bin/bash
# Entrypoint of the ckan-worker service: `ckan jobs worker` (the RQ queue XLoader submits
# to) instead of uWSGI. It deliberately skips prerun.py: the web container already runs
# `ckan db init` and the migrations, and two containers racing on them invites deadlocks.
set -euo pipefail

CKAN_INI="${CKAN_INI:-/srv/app/ckan.ini}"

# ckan.plugins is read before plugins are loaded, so the envvars plugin cannot turn
# plugins on — that is why prerun.py writes CKAN__PLUGINS into the ini for the web
# container. Do the same here, otherwise the worker would run stock CKAN and fail to
# import the xloader job.
if [ -n "${CKAN__PLUGINS:-}" ]; then
    ckan config-tool "$CKAN_INI" "ckan.plugins = ${CKAN__PLUGINS}"
fi

# The ini shipped in the image has an empty SECRET_KEY: only start_ckan.sh (web container)
# fills it in, and it fills it with a *random* value. The worker must use the same secret
# as the web container, so it has to come from the environment (gotchas 11).
if [ -z "${CKAN___SECRET_KEY:-}" ]; then
    echo "[worker] CKAN___SECRET_KEY is empty — generate the secrets with docker/make-env.sh" >&2
    exit 1
fi

exec ckan -c "$CKAN_INI" jobs worker "$@"
