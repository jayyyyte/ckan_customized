#!/usr/bin/env bash
# Deploy the OpenMetadata stand-in of the kind rehearsal (om-mock.yaml):
#   bash k8s/overlays/kind/om-mock.sh [context]        # default kind-ckan-rehearsal
#   bash k8s/overlays/kind/om-mock.sh [context] --delete
#
# Run it BEFORE `kubectl apply -k k8s/overlays/kind`: it adds the bot token
# CKANEXT__LAKEHOUSE__OM__API_TOKEN to secrets.env (generated once, kept afterwards), and
# the ckan-secrets Secret is built from that file. kind only.
set -euo pipefail
CTX="${1:-kind-ckan-rehearsal}"
case "$CTX" in kind-*) ;; *) echo "Refusing to run against $CTX: kind clusters only." >&2; exit 1 ;; esac
HERE="$(cd "$(dirname "$0")" && pwd)"
REPO="$(cd "$HERE/../../.." && pwd)"
K="kubectl --context $CTX -n lakehouse"

if [ "${2:-}" = "--delete" ]; then
    $K delete -f "$HERE/om-mock.yaml" --ignore-not-found
    $K delete configmap ckan-om-mock-files --ignore-not-found
    $K delete secret ckan-om-mock --ignore-not-found
    exit 0
fi

secrets="$HERE/secrets.env"
[ -f "$secrets" ] || { echo "No $secrets: run k8s/scripts/make-secrets.sh kind first." >&2; exit 1; }
key=CKANEXT__LAKEHOUSE__OM__API_TOKEN
if ! grep -q "^$key=" "$secrets"; then
    printf '\n# Bot token of the OpenMetadata stand-in (om-mock.sh)\n%s=%s\n' "$key" \
        "$(python3 -c 'import secrets; print(secrets.token_urlsafe(32))')" >>"$secrets"
    echo "Added $key to $secrets"
fi
token="$(grep "^$key=" "$secrets" | cut -d= -f2-)"

# The token goes through a file descriptor, not argv.
$K create secret generic ckan-om-mock --from-env-file=<(printf 'OM_TOKEN=%s\n' "$token") \
    --dry-run=client -o yaml | $K apply -f - >/dev/null
$K create configmap ckan-om-mock-files \
    --from-file=om_mock.py="$REPO/tools/openmetadata/om_mock.py" \
    --from-file=snapshot.json="$REPO/tools/openmetadata/sample-snapshot.json" \
    --dry-run=client -o yaml | $K apply -f - >/dev/null
$K label secret/ckan-om-mock configmap/ckan-om-mock-files app.kubernetes.io/part-of=ckan --overwrite >/dev/null
$K apply -f "$HERE/om-mock.yaml"
# A changed snapshot does not change the pod spec: restart so the new file is read.
$K rollout restart deploy/ckan-om-mock >/dev/null
$K rollout status deploy/ckan-om-mock --timeout=120s
