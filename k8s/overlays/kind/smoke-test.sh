#!/usr/bin/env bash
# End-to-end acceptance test of the phase 3 rehearsal on kind: the phase 2 test plan
# re-run against Kubernetes (docs/phase-3-k8s-deploy.md, section 3.10).
#   bash k8s/overlays/kind/smoke-test.sh [context]        # default kind-ckan-rehearsal
#
# kind only: it loads demo content, cordons a node, restarts pods and uploads files.
# None of that is acceptable on the shared company cluster.
set -uo pipefail
CTX="${1:-kind-ckan-rehearsal}"
case "$CTX" in kind-*) ;; *) echo "Refusing to run against $CTX: kind clusters only." >&2; exit 1 ;; esac
REPO="$(cd "$(dirname "$0")/../../.." && pwd)"
K="kubectl --context $CTX -n lakehouse"
URL=http://localhost:30500
WORK=$(mktemp -d)
trap 'rm -rf "$WORK"' EXIT
pass=0 fail=0
ok() { echo "PASS  $*"; pass=$((pass+1)); }
ko() { echo "FAIL  $*"; fail=$((fail+1)); }
expect() { local desc=$1; shift; if "$@" >/dev/null 2>&1; then ok "$desc"; else ko "$desc"; fi; }
ckan() { $K exec deploy/ckan -c ckan -- ckan -c /srv/app/ckan.ini "$@"; }
api() { curl -sf "$URL/api/3/action/$1" "${@:2}"; }
jget() { python3 -c "import json,sys; d=json.load(sys.stdin); print($1)"; }
code() { curl -s -o /dev/null -w '%{http_code}' "$@"; }
secret() { grep "^$1=" "$REPO/k8s/overlays/kind/secrets.env" | cut -d= -f2-; }

echo "== 1. status and plugins"
st=$(api status_show)
v=$(echo "$st" | jget 'd["result"]["ckan_version"]')
expect "status_show reports 2.11.6 (got $v)" test "$v" = 2.11.6
exts=$(echo "$st" | jget '" ".join(d["result"]["extensions"])')
for e in evntheme activity tracking datastore xloader datatables_view envvars; do
    expect "plugin $e loaded" grep -qw "$e" <<<"$exts"
done

echo "== 2. demo content"
n=$(api 'package_search?rows=0' | jget 'd["result"]["count"]')
if [ "$n" = 0 ]; then
    if ckan evntheme seed-demo >"$WORK/seed.log" 2>&1; then ok "seed-demo"; else ko "seed-demo"; tail -20 "$WORK/seed.log"; fi
fi
n=$(api 'package_search?rows=0' | jget 'd["result"]["count"]')
orgs=$(api organization_list | jget 'len(d["result"])')
groups=$(api group_list | jget 'len(d["result"])')
expect "12 datasets (got $n)" test "$n" -ge 12
expect "9 organizations (got $orgs)" test "$orgs" = 9
expect "5 domain groups (got $groups)" test "$groups" = 5

echo "== 3. pages rendered by the theme"
first=$(api 'package_search?rows=1&sort=name%20asc' | jget 'd["result"]["results"][0]["name"]')
for p in / /dataset/ /organization/ /group/ /mds/ /about "/dataset/$first" \
         "/dataset/$first?tab=preview" "/dataset/$first?tab=api" "/dataset/$first?tab=activity"; do
    c=$(curl -s -o "$WORK/page" -w '%{http_code}' "$URL$p")
    expect "GET $p -> 200 with evn-header (got $c)" bash -c "[ $c = 200 ] && grep -q 'class=\"evn-header\"' '$WORK/page'"
done
curl -s "$URL/" -o "$WORK/home"
expect "home: Vietnamese site title" grep -q 'Cổng dữ liệu EVN' "$WORK/home"
expect "home: no Google Fonts request" bash -c "! grep -q fonts.googleapis '$WORK/home'"
expect "favicon 200" test "$(code "$URL/evntheme/images/favicon.svg")" = 200
woff=$(python3 - "$WORK/home" "$URL" <<'PY'
import re, sys, urllib.parse, urllib.request
html, base = open(sys.argv[1], encoding="utf-8").read(), sys.argv[2]
for href in re.findall(r'href="([^"]+\.css[^"]*)"', html):
    css_url = urllib.parse.urljoin(base + "/", href)
    css = urllib.request.urlopen(css_url).read().decode("utf-8", "replace")
    m = re.search(r'url\(["\']?([^)"\']+\.woff2)', css)
    if m:
        print(urllib.parse.urljoin(css_url, m.group(1))); break
PY
)
expect "self-hosted .woff2 200 ($woff)" test "$(code "$woff")" = 200

echo "== 4. Vietnamese search"
word=$(api "package_show?id=$first" | jget 'max((w for w in d["result"]["title"].split() if not w.isascii()), key=len, default=d["result"]["title"].split()[0])')
hits=$(curl -sfG "$URL/api/3/action/package_search" --data-urlencode "q=$word" --data-urlencode rows=0 | jget 'd["result"]["count"]')
expect "package_search q=$word -> $hits hit(s)" test "$hits" -ge 1

echo "== 5. API token; worker moved off the node that holds ckan-storage"
TOKEN=$(ckan user token add admin smoke-k8s -q 2>/dev/null | tail -1 | tr -d '[:space:]')
expect "API token created" test -n "$TOKEN"
ckan_node=$($K get pod -l app.kubernetes.io/name=ckan -o jsonpath='{.items[0].spec.nodeName}')
worker_node=$($K get pod -l app.kubernetes.io/name=ckan-worker -o jsonpath='{.items[0].spec.nodeName}')
if [ "$ckan_node" = "$worker_node" ]; then
    kubectl --context "$CTX" cordon "$ckan_node" >/dev/null
    $K delete pod -l app.kubernetes.io/name=ckan-worker --wait=true >/dev/null
    $K rollout status deploy/ckan-worker --timeout=180s >/dev/null
    kubectl --context "$CTX" uncordon "$ckan_node" >/dev/null
    worker_node=$($K get pod -l app.kubernetes.io/name=ckan-worker --field-selector=status.phase=Running -o jsonpath='{.items[0].spec.nodeName}')
fi
expect "worker on $worker_node, ckan-storage on $ckan_node" test "$worker_node" != "$ckan_node"

echo "== 6. upload -> PVC -> XLoader (worker has no volume)"
printf 'ma_don_vi,ten_don_vi,san_luong_mwh\nPC01,Điện lực Hà Nội,1234.5\nPC02,Điện lực Hải Phòng,987.6\nPC03,Điện lực Đà Nẵng,456.7\n' >"$WORK/smoke.csv"
res=$(curl -sf -H "Authorization: $TOKEN" -F package_id="$first" -F name=smoke-k8s.csv -F format=CSV \
      -F upload=@"$WORK/smoke.csv" "$URL/api/3/action/resource_create")
rid=$(echo "$res" | jget 'd["result"]["id"]')
rurl=$(echo "$res" | jget 'd["result"]["url"]')
expect "resource_create with upload ($rid)" test -n "$rid"
curl -sf -H "Authorization: $TOKEN" -o "$WORK/down.csv" "$rurl"
expect "downloaded file identical to the upload" cmp -s "$WORK/smoke.csv" "$WORK/down.csv"
ckan xloader submit all >/dev/null 2>&1
rows=0
for _ in $(seq 1 60); do
    rows=$(api "datastore_search?resource_id=$rid&limit=0" 2>/dev/null | jget 'd["result"]["total"]' 2>/dev/null || echo 0)
    [ "$rows" = 3 ] && break; sleep 5
done
expect "XLoader loaded the upload into the DataStore (rows=$rows)" test "$rows" = 3
prev=-1; active=0
for _ in $(seq 1 30); do
    active=$(api 'package_search?rows=100' | jget 'sum(1 for p in d["result"]["results"] for r in p["resources"] if r.get("datastore_active"))')
    [ "$active" = "$prev" ] && break; prev=$active; sleep 10
done
expect "datastore_active resources: $active (10 seeded CSV + 1 upload)" test "$active" -ge 11
expect "preview tab of $first renders" test "$(code "$URL/dataset/$first?tab=preview&resource_id=$rid")" = 200

echo "== 7. login session"
curl -s -c "$WORK/jar" -b "$WORK/jar" -o "$WORK/login.html" "$URL/user/login"
csrf=$(python3 -c 'import re,sys; m=re.search(r"name=\"_csrf_token\" value=\"([^\"]+)\"", open(sys.argv[1]).read()); print(m.group(1) if m else "")' "$WORK/login.html")
printf '%s' "$(secret CKAN_SYSADMIN_PASSWORD)" >"$WORK/pw"   # no trailing newline
curl -s -c "$WORK/jar" -b "$WORK/jar" -o /dev/null --data-urlencode login=admin \
     --data-urlencode "password@$WORK/pw" --data-urlencode "_csrf_token=$csrf" "$URL/user/login"
rm -f "$WORK/pw"
expect "logged in: /dashboard/datasets 200" test "$(code -b "$WORK/jar" "$URL/dashboard/datasets")" = 200

echo "== 8. DataStore roles"
ro_pw=$(secret CKAN_DATASTORE_READ_URL | python3 -c 'import sys,urllib.parse; print(urllib.parse.urlsplit(sys.stdin.read().strip()).password)')
ro_sql() { printf '%s\n' "$ro_pw" | $K exec -i svc/postgres-service -- sh -c \
    'read -r PGPASSWORD; export PGPASSWORD; psql -X -h 127.0.0.1 -U datastore_default -d datastore_default -v ON_ERROR_STOP=1 -tAc "$1"' sh "$1"; }
expect "read-only role: SELECT on _table_metadata" ro_sql 'SELECT count(*) FROM "_table_metadata"'
ro_refused() { ! ro_sql "$1"; }
expect "read-only role: CREATE TABLE refused" ro_refused 'CREATE TABLE smoke_forbidden (x int)'

echo "== 9. tracking CronJob"
$K delete job smoke-tracking --ignore-not-found >/dev/null
$K create job --from=cronjob/ckan-tracking-update smoke-tracking >/dev/null
expect "job from cronjob/ckan-tracking-update completed" $K wait --for=condition=complete job/smoke-tracking --timeout=300s
$K logs job/smoke-tracking 2>&1 | grep -iE "index|rebuilt" | tail -2
views=0
for name in $(api 'package_search?rows=100' | jget '" ".join(p["name"] for p in d["result"]["results"])'); do
    t=$(api "package_show?id=$name&include_tracking=true" | jget 'd["result"].get("tracking_summary",{}).get("total",0)')
    views=$((views + t))
done
expect "tracking_summary filled: $views views in total" test "$views" -gt 0

echo "== 10. restart the web pod"
curl -sf -o "$WORK/before.csv" "$rurl"
$K rollout restart deploy/ckan >/dev/null
$K rollout status deploy/ckan --timeout=420s >/dev/null
# The NodePort refuses connections for a few seconds after the rollout (gotchas 21e).
for _ in $(seq 1 15); do [ "$(code "$URL/api/3/action/status_show")" = 200 ] && break; sleep 2; done
new_node=$($K get pod -l app.kubernetes.io/name=ckan --field-selector=status.phase=Running -o jsonpath='{.items[0].spec.nodeName}')
expect "new pod on the same node as before ($new_node): the volume is pinned" test "$new_node" = "$ckan_node"
expect "API token still valid (api_token_list 200)" test "$(code -H "Authorization: $TOKEN" "$URL/api/3/action/api_token_list?user_id=admin")" = 200
expect "  ...and refused without it (403)" test "$(code "$URL/api/3/action/api_token_list?user_id=admin")" = 403
expect "session cookie still valid" test "$(code -b "$WORK/jar" "$URL/dashboard/datasets")" = 200
curl -sf -o "$WORK/after.csv" "$rurl"
expect "uploaded file still served from the PVC" cmp -s "$WORK/before.csv" "$WORK/after.csv"
n2=$(api 'package_search?rows=0' | jget 'd["result"]["count"]')
expect "datasets unchanged ($n2)" test "$n2" = "$n"
expect "DataStore rows still there" test "$(api "datastore_search?resource_id=$rid&limit=0" | jget 'd["result"]["total"]')" = 3

echo "== 11. XLoader after the restart (token re-minted by 20-xloader-token.sh)"
printf 'ky,gia_tri\n2026-01,1\n2026-02,2\n' >"$WORK/smoke2.csv"
rid2=$(curl -sf -H "Authorization: $TOKEN" -F package_id="$first" -F name=smoke-k8s-2.csv -F format=CSV \
       -F upload=@"$WORK/smoke2.csv" "$URL/api/3/action/resource_create" | jget 'd["result"]["id"]')
rows=0
for _ in $(seq 1 60); do
    rows=$(api "datastore_search?resource_id=$rid2&limit=0" 2>/dev/null | jget 'd["result"]["total"]' 2>/dev/null || echo 0)
    [ "$rows" = 2 ] && break; sleep 5
done
expect "auto-submitted upload loaded after restart (rows=$rows)" test "$rows" = 2

echo "== 12. memory in use (cgroup), for requests/limits"
for d in ckan ckan-worker ckan-solr ckan-redis; do
    printf '  %-12s current=%s MiB  peak=%s MiB\n' "$d" \
        "$($K exec deploy/$d -- sh -c 'echo $(( $(cat /sys/fs/cgroup/memory.current) / 1048576 ))' 2>/dev/null)" \
        "$($K exec deploy/$d -- sh -c 'echo $(( $(cat /sys/fs/cgroup/memory.peak) / 1048576 ))' 2>/dev/null)"
done

echo "== cleanup"
for rid_ in "$rid" "$rid2"; do curl -sf -H "Authorization: $TOKEN" -d "{\"id\":\"$rid_\"}" -H 'Content-Type: application/json' "$URL/api/3/action/resource_delete" >/dev/null && echo "  deleted resource $rid_"; done
jti=$(ckan user token list admin 2>/dev/null | sed -n 's/^[[:space:]]*\[\([^]]*\)\] smoke-k8s .*/\1/p' | head -1)
[ -n "$jti" ] && ckan user token revoke "$jti" >/dev/null 2>&1 && echo "  smoke token revoked"
$K delete job smoke-tracking --ignore-not-found >/dev/null

echo
echo "RESULT: $pass passed, $fail failed"
