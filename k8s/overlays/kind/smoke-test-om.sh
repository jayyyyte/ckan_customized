#!/usr/bin/env bash
# Acceptance test of phase 4 on kind (docs/phase-4-content-openmetadata.md):
# bootstrap of organizations/users/roles, OpenMetadata sync from the CronJob, the
# "Technical catalog" tab and its permissions, and the fallback when OpenMetadata is down.
#   bash k8s/overlays/kind/om-mock.sh               # once, before `apply -k`
#   bash k8s/overlays/kind/smoke-test-om.sh [context]
#
# kind only: it creates demo users, runs jobs and scales the OpenMetadata stand-in to 0.
set -uo pipefail
CTX="${1:-kind-ckan-rehearsal}"
case "$CTX" in kind-*) ;; *) echo "Refusing to run against $CTX: kind clusters only." >&2; exit 1 ;; esac
REPO="$(cd "$(dirname "$0")/../../.." && pwd)"
K="kubectl --context $CTX -n lakehouse"
URL=http://localhost:30500
DEMO="$REPO/ckanext-lakehouse/ckanext/lakehouse/demo/portal.yaml"
OUTAGE=om-trino_lakehouse-iceberg_curated-van_hanh-curated_outage_summary
WORK=$(mktemp -d)   # holds the demo passwords printed by bootstrap: removed on exit
trap 'rm -rf "$WORK"' EXIT
pass=0 fail=0
ok() { echo "PASS  $*"; pass=$((pass+1)); }
ko() { echo "FAIL  $*"; fail=$((fail+1)); }
expect() { local desc=$1; shift; if "$@" >/dev/null 2>&1; then ok "$desc"; else ko "$desc"; fi; }
ckan() { $K exec deploy/ckan -c ckan -- ckan -c /srv/app/ckan.ini "$@" 2>/dev/null; }
ckan_in() { $K exec -i deploy/ckan -c ckan -- ckan -c /srv/app/ckan.ini "$@" 2>/dev/null; }
code() { curl -s -o /dev/null -w '%{http_code}' "$@"; }
token() { ckan user token add "$1" smoke-om | tail -1 | tr -d '[:space:]'; }
run_sync_job() {   # name -> log in $WORK/<name>.log
    $K delete job "$1" --ignore-not-found >/dev/null
    $K create job --from=cronjob/ckan-om-sync "$1" >/dev/null
    # Until it succeeds or fails: `wait --for=condition=complete` would sit out its whole
    # timeout on a job that is meant to fail (OpenMetadata down).
    for _ in $(seq 1 150); do
        [ -n "$($K get job "$1" -o jsonpath='{.status.succeeded}{.status.failed}' 2>/dev/null)" ] && break
        sleep 2
    done
    $K logs "job/$1" >"$WORK/$1.log" 2>/dev/null
}

echo "== 1. image and services"
img=$($K get deploy ckan -o jsonpath='{.spec.template.spec.containers[0].image}')
expect "ckan runs ckan-lakehouse:0.2.0 (got $img)" test "$img" = ckan-lakehouse:0.2.0
expect "OpenMetadata stand-in ready" $K rollout status deploy/ckan-om-mock --timeout=60s
expect "plugin lakehouse loaded" bash -c "curl -sf $URL/api/3/action/status_show | grep -q '\"lakehouse\"'"
expect "CronJob ckan-om-sync exists (minute 40)" bash -c "$K get cronjob ckan-om-sync -o jsonpath='{.spec.schedule}' | grep -qx '40 \* \* \* \*'"

echo "== 2. bootstrap (file on stdin, passwords to stdout)"
ckan_in lakehouse bootstrap - --credentials - <"$DEMO" >"$WORK/boot1.out"
if grep -q "^om-sync," "$WORK/boot1.out"; then
    ok "bootstrap created the 9 demo users ($(grep -c '@evn.example' "$WORK/boot1.out") passwords printed)"
else
    expect "bootstrap ran (users existed already)" grep -q "Nothing to change\|Roles set\|Updated" "$WORK/boot1.out"
fi
ckan_in lakehouse bootstrap - <"$DEMO" >"$WORK/boot2.out"
expect "second bootstrap: Nothing to change" grep -q "Nothing to change" "$WORK/boot2.out"

echo "== 3. OpenMetadata check and sync (job from the CronJob)"
ckan lakehouse om check >"$WORK/check.out"
expect "om check reaches the stand-in (1.6.2)" grep -q "OpenMetadata 1.6.2" "$WORK/check.out"
expect "om check: 6 tables in scope" grep -q "6 table(s) in scope" "$WORK/check.out"
run_sync_job smoke-om-sync-1
expect "first sync: 6 in scope, nothing failed" bash -c "grep -q '6 in scope' $WORK/smoke-om-sync-1.log && ! grep -q '^Errors' $WORK/smoke-om-sync-1.log"
grep -E "Created|unchanged|Skipped" "$WORK/smoke-om-sync-1.log" | sed 's/^/      /'
run_sync_job smoke-om-sync-2
expect "second sync: 5 unchanged, nothing written" bash -c "grep -q '5 unchanged' $WORK/smoke-om-sync-2.log && ! grep -q '^Updated\|^Created' $WORK/smoke-om-sync-2.log"

echo "== 4. datasets and permissions"
ADMIN=$(token admin); KTSX=$(token ktsx-bientap); A0=$(token a0-thanhvien); VIEWER=$(token nguoidung-xem)
show() { curl -s -H "Authorization: $1" "$URL/api/3/action/package_show?id=$OUTAGE"; }
pkg=$(show "$ADMIN")
py() { python3 -c "import json,sys; d=json.load(sys.stdin)['result']; print($1)"; }
expect "outage dataset is private" test "$(echo "$pkg" | py 'd["private"]')" = True
expect "owned by trung-tam-dieu-do-htd-qg" test "$(echo "$pkg" | py 'd["organization"]["name"]')" = trung-tam-dieu-do-htd-qg
expect "in group ky-thuat-an-toan (sync user is not a sysadmin)" test "$(echo "$pkg" | py '",".join(g["name"] for g in d["groups"])')" = ky-thuat-an-toan
expect "Trino JDBC resource" test "$(echo "$pkg" | py 'd["resources"][0]["url"]')" = "jdbc:trino://10.1.117.91:30800/iceberg_curated/van_hanh"
expect "record_count from the profile" bash -c "echo '$pkg' | grep -q '\"key\": \"record_count\", \"value\": \"1284530\"'"
sync_id=$(curl -s -H "Authorization: $ADMIN" "$URL/api/3/action/user_show?id=om-sync" | py 'd["id"]')
acts=$(curl -s -H "Authorization: $ADMIN" "$URL/api/3/action/package_activity_list?id=$OUTAGE" | py '" ".join(a["user_id"] for a in d)')
expect "activity stream names om-sync" grep -qw "$sync_id" <<<"$acts"
expect "anonymous: package_show 403" test "$(code "$URL/api/3/action/package_show?id=$OUTAGE")" = 403
expect "registered user outside the org: 403" test "$(code -H "Authorization: $VIEWER" "$URL/api/3/action/package_show?id=$OUTAGE")" = 403
expect "member of the org (a0-thanhvien) can read" test "$(code -H "Authorization: $A0" "$URL/api/3/action/package_show?id=$OUTAGE")" = 200

echo "== 5. Technical catalog tab"
curl -s -H "Authorization: $KTSX" "$URL/dataset/$OUTAGE?tab=openmetadata" >"$WORK/tab.html"
expect "tab rendered inline (editor)" grep -q 'id="tab-openmetadata"' "$WORK/tab.html"
expect "failed quality check listed" grep -q "province_in_code_list" "$WORK/tab.html"
expect "lineage reaches the Airflow pipeline" grep -q "airflow_lakehouse.curated_outage_summary" "$WORK/tab.html"
expect "lineage links the synced table to its CKAN page" grep -q "/dataset/om-trino_lakehouse-iceberg_curated-van_hanh-grid_loss_monthly" "$WORK/tab.html"
expect "sidebar shows Bảng nguồn, hides om_* extras" bash -c "grep -q '<dt>Bảng nguồn</dt>' $WORK/tab.html && ! grep -q '<dt>om_columns</dt>' $WORK/tab.html"
F="$URL/dataset/$OUTAGE/openmetadata"
expect "fragment: anonymous 403" test "$(code "$F")" = 403
expect "fragment: outside the org 403" test "$(code -H "Authorization: $VIEWER" "$F")" = 403
expect "fragment: org member 200" test "$(code -H "Authorization: $A0" "$F")" = 200

echo "== 6. OpenMetadata down"
$K scale deploy/ckan-om-mock --replicas=0 >/dev/null
$K wait --for=delete pod -l app.kubernetes.io/name=ckan-om-mock --timeout=60s >/dev/null 2>&1
$K exec deploy/ckan-redis -- sh -c 'redis-cli --scan --pattern "ckanext-lakehouse:om:*" | xargs -r redis-cli del' >/dev/null
start=$(date +%s)
curl -s -H "Authorization: $A0" "$F" >"$WORK/down.html"
took=$(( $(date +%s) - start ))
expect "notice shown" grep -q "Hiện không kết nối được OpenMetadata" "$WORK/down.html"
expect "columns from the last sync still listed" grep -q "saidi_minutes" "$WORK/down.html"
expect "answered within om.timeout (${took}s)" test "$took" -le 7
run_sync_job smoke-om-sync-down
expect "sync with OpenMetadata down fails and changes nothing" bash -c "grep -q 'nothing was changed' $WORK/smoke-om-sync-down.log"
$K scale deploy/ckan-om-mock --replicas=1 >/dev/null
$K rollout status deploy/ckan-om-mock --timeout=60s >/dev/null

echo "== cleanup"
for u in admin ktsx-bientap a0-thanhvien nguoidung-xem; do
    for jti in $(ckan user token list "$u" | sed -n 's/^[[:space:]]*\[\([^]]*\)\] smoke-om .*/\1/p'); do
        ckan user token revoke "$jti" >/dev/null && echo "  token of $u revoked"
    done
done
$K delete job smoke-om-sync-1 smoke-om-sync-2 smoke-om-sync-down --ignore-not-found >/dev/null

echo
echo "RESULT: $pass passed, $fail failed"
[ "$fail" -eq 0 ]
