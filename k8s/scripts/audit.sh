#!/usr/bin/env bash
# Read-only audit before phase 3 touches the shared cluster (phase-3 §3.1). Only get,
# auth can-i, logs and `helm list`: nothing is created, changed or deleted, and no
# Secret or environment value is printed.
#   bash k8s/scripts/audit.sh --context <ctx> [namespace] | tee ~/ckan-audit-$(date +%F).txt
# Keep the output out of the repo (it lists colleagues' workloads); copy the findings
# into docs/cluster-context.md.
set -uo pipefail   # no -e: one forbidden command must not end the audit

[ "${1:-}" = --context ] && [ -n "${2:-}" ] || {
    echo "usage: audit.sh --context <ctx> [namespace]" >&2; exit 1; }
ctx="$2"
ns="${3:-lakehouse}"

k() { kubectl --context "$ctx" --request-timeout=20s "$@"; }
section() { printf '\n===== %s\n' "$*"; }
run() { printf '$ kubectl %s\n' "$*"; k "$@" 2>&1; }

section "Context"
echo "$ctx -> $(kubectl config view --minify --context "$ctx" -o jsonpath='{.clusters[0].cluster.server}')"
run version

section "Nodes: CPU architecture (image is amd64), runtime, taints"
run get nodes -o wide
run get nodes -o 'custom-columns=NAME:.metadata.name,ARCH:.status.nodeInfo.architecture,RUNTIME:.status.nodeInfo.containerRuntimeVersion,TAINTS:.spec.taints[*].key'

section "Free capacity per node (CKAN requests ~0.65 CPU / ~1.7 GiB, limits 4.5 CPU / ~4.8 GiB)"
k describe nodes 2>&1 | grep -E '^Name:|Allocated resources' -A7 | grep -E 'Name:|cpu|memory'

section "Namespace $ns (labels: Pod Security admission?) and storage"
run get ns "$ns" --show-labels
run get storageclass

section "What this kubeconfig may do in $ns"
for check in "create deployments.apps" "create services" "create secrets" "create configmaps" \
             "create persistentvolumeclaims" "create cronjobs.batch" "create pods/exec" \
             "delete deployments.apps" "delete services"; do
    # shellcheck disable=SC2086 # word splitting of $check is intended
    printf '  %-32s %s\n' "$check" "$(k auth can-i $check -n "$ns" 2>&1)"
done

section "Quotas, default limits, network policies in $ns (each can break a deploy)"
run -n "$ns" get resourcequota,limitrange,networkpolicy

section "Workloads in $ns"
run -n "$ns" get deploy,sts,ds,cronjob,svc,pvc -o wide

section "The ckan stub (phase-3 §3.2: replaced only after its owner agrees)"
k -n "$ns" get deploy,svc,pvc,cm -o wide 2>&1 | grep -iE '^NAME|ckan'
printf 'deploy/ckan: image=%s selector=%s\n' \
    "$(k -n "$ns" get deploy ckan -o jsonpath='{.spec.template.spec.containers[*].image}' 2>&1)" \
    "$(k -n "$ns" get deploy ckan -o jsonpath='{.spec.selector.matchLabels}' 2>&1)"
printf 'svc/ckan-service: %s\n' \
    "$(k -n "$ns" get svc ckan-service -o jsonpath='{.spec.type} selector={.spec.selector} ports={.spec.ports}' 2>&1)"
echo '$ kubectl logs deploy/ckan --tail=20'
k -n "$ns" logs deploy/ckan --tail=20 2>&1

section "Name and port clashes (NodePort 30500, names ckan-*, solr, redis)"
k get svc -A -o wide 2>&1 | grep -E '^NAMESPACE|30500|ckan|solr|redis'

section "postgres-service: workload name, image (need >= 15), ports"
k -n "$ns" get deploy,sts,svc -o wide 2>&1 | grep -iE '^NAME|postgres'

section "Images in use: pulled from Docker Hub directly, or from a registry of our own?"
k get pods -A -o jsonpath='{range .items[*]}{range .spec.containers[*]}{.image}{"\n"}{end}{end}' 2>&1 \
    | sort | uniq -c | sort -rn

section "Helm releases"
if command -v helm >/dev/null; then helm --kube-context "$ctx" list -A 2>&1; else echo "helm not installed"; fi
