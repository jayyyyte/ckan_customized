#!/bin/bash
# Sourced by start_ckan.sh — same rules as 10-plugin-migrations.sh.
#
# XLoader writes to the DataStore through the CKAN API and authenticates with an API
# token. There is no fallback: ckanext.xloader.api_token defaults to the literal
# "NOT_SET" and xloader_submit raises ValidationError while it stays that way.
#
# Pin a token with CKANEXT__XLOADER__API_TOKEN (a Secret in phase 3) — otherwise one is
# minted here for the sysadmin prerun.py just created. Only this container needs it: the
# token is copied into the job, so the worker gets it with the job it picks up.
if [ -n "${CKANEXT__XLOADER__API_TOKEN:-}" ]; then
    echo "[entrypoint] xloader: using the API token from the environment"
elif [ -z "${CKAN_SYSADMIN_NAME:-}" ]; then
    echo "[entrypoint] xloader: CKAN_SYSADMIN_NAME is empty, no token created —" \
         "set CKANEXT__XLOADER__API_TOKEN or DataStore uploads will fail" >&2
else
    # ckan.ini lives in the container filesystem, so a restart needs a fresh token.
    # Revoke the ones earlier starts left behind instead of piling them up in the database.
    ckan -c "$CKAN_INI" user token list "$CKAN_SYSADMIN_NAME" 2>/dev/null \
        | sed -n 's/^[[:space:]]*\[\([^]]*\)\] xloader-container .*/\1/p' \
        | while read -r _jti; do ckan -c "$CKAN_INI" user token revoke "$_jti" >/dev/null 2>&1; done
    _token=$(ckan -c "$CKAN_INI" user token add "$CKAN_SYSADMIN_NAME" xloader-container -q 2>/dev/null \
        | tail -1 | tr -d '[:space:]')
    if [ -n "$_token" ]; then
        # config-tool, not echo: the token must not end up in the container log.
        ckan config-tool "$CKAN_INI" "ckanext.xloader.api_token = ${_token}"
        echo "[entrypoint] xloader: API token created for ${CKAN_SYSADMIN_NAME}"
    else
        echo "[entrypoint] xloader: could not create an API token" >&2
    fi
    unset _token
fi
