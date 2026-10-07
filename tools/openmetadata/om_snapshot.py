#!/usr/bin/env python3
"""Record an offline snapshot of OpenMetadata metadata (Python 3.8+, stdlib only).

Run it on a machine that reaches OpenMetadata (the company PC over Remote Desktop),
copy the JSON back, and serve it with om_mock.py to develop CKAN against real
metadata without the company network.

    set OM_TOKEN=<JWT>                       (Windows)   |   export OM_TOKEN=<JWT>   (Linux)
    python om_snapshot.py --url http://openmetadata.local:8585 ^
        --include "trino_lakehouse.iceberg_curated.*" --out lakehouse.om-snapshot.json

The token: OpenMetadata > Settings > Bots (a bot with read access), or your profile >
Access Tokens. It is read from OM_TOKEN (or asked for) and never written to the file.

What is recorded: tables (description, columns, owners, domains, tags, usage count),
the latest table-level profile (row and column counts), direct lineage, and the
status of data quality tests. What is NOT: sample data, column profiles (min/max/...
are real values), test result messages, followers' names, custom properties.
The file still names tables and people who own them: keep it off git and delete it
when done (the repo ignores *.om-snapshot.json).
"""
from __future__ import annotations

import argparse
import fnmatch
import getpass
import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

TABLE_FIELDS = "columns,tags,tableConstraints,usageSummary,followers"
TABLE_FIELD_VARIANTS = ("owners,domains", "owners,domain", "owner,domain", "owner")
TEST_CASE_FIELD_VARIANTS = ("testCaseResult,testDefinition", "testDefinition", "")

KEEP_TABLE = ("id", "name", "displayName", "fullyQualifiedName", "description", "tableType", "serviceType",
              "updatedAt", "version", "deleted", "tableConstraints")
KEEP_COLUMN = ("name", "displayName", "dataType", "dataTypeDisplay", "description", "constraint",
               "ordinalPosition")
KEEP_REF = ("id", "type", "name", "displayName", "fullyQualifiedName")


class HTTPError(Exception):
    def __init__(self, status: int, message: str) -> None:
        super().__init__(f"HTTP {status}: {message}")
        self.status = status


class Client:
    def __init__(self, url: str, token: str, timeout: float) -> None:
        self.api = url.rstrip("/") + "/api/v1"
        self.token = token
        self.timeout = timeout
        self.fields: dict = {}

    def get(self, path: str, params: dict | None = None) -> dict:
        url = self.api + path + ("?" + urllib.parse.urlencode(params) if params else "")
        request = urllib.request.Request(url, headers={"Authorization": f"Bearer {self.token}",
                                                       "Accept": "application/json"})
        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as response:  # noqa: S310
                return json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as err:
            body = err.read().decode("utf-8", "replace")[:300]
            raise HTTPError(err.code, body) from None

    def get_fields(self, kind: str, path: str, params: dict, base: str, variants: tuple) -> dict:
        candidates = [self.fields[kind]] if kind in self.fields else list(variants)
        last = None
        for variant in candidates:
            fields = ",".join(p for p in (base, variant) if p)
            try:
                result = self.get(path, {**params, "fields": fields} if fields else params)
            except HTTPError as err:
                if err.status == 400 and "field" in str(err).lower():
                    last = err
                    continue
                raise
            self.fields[kind] = variant
            return result
        raise last or HTTPError(400, "no accepted fields")


def q(fqn: str) -> str:
    return urllib.parse.quote(fqn, safe="")


def ref(value: dict | None) -> dict | None:
    return {k: value[k] for k in KEEP_REF if value and k in value} if value else None


def clean_table(table: dict) -> dict:
    result = {k: table[k] for k in KEEP_TABLE if k in table}
    result["service"] = ref(table.get("service"))
    result["columns"] = [
        {**{k: c[k] for k in KEEP_COLUMN if k in c},
         "tags": [{"tagFQN": t.get("tagFQN")} for t in c.get("tags") or []]}
        for c in table.get("columns") or []
    ]
    result["tags"] = [{"tagFQN": t.get("tagFQN"), "source": t.get("source")} for t in table.get("tags") or []]
    owners = table.get("owners") or ([table["owner"]] if table.get("owner") else [])
    result["owners"] = [{k: o[k] for k in ("type", "name", "displayName") if k in o} for o in owners]
    domains = table.get("domains") or ([table["domain"]] if table.get("domain") else [])
    result["domains"] = [ref(d) for d in domains]
    result["followers"] = [{} for _ in table.get("followers") or []]  # the count only
    weekly = ((table.get("usageSummary") or {}).get("weeklyStats") or {}).get("count")
    if weekly is not None:
        result["usageSummary"] = {"weeklyStats": {"count": weekly}}
    return result


def clean_lineage(lineage: dict) -> dict:
    def edge(e: dict) -> dict:
        return {"fromEntity": e.get("fromEntity"), "toEntity": e.get("toEntity")}

    return {"nodes": [ref(n) for n in lineage.get("nodes") or []],
            "upstreamEdges": [edge(e) for e in lineage.get("upstreamEdges") or []],
            "downstreamEdges": [edge(e) for e in lineage.get("downstreamEdges") or []]}


def clean_test(case: dict) -> dict:
    result = case.get("testCaseResult") or {}
    return {"name": case.get("name"), "displayName": case.get("displayName"),
            "entityLink": case.get("entityLink"),
            "testDefinition": ref(case.get("testDefinition")),
            "testCaseResult": {k: result[k] for k in ("testCaseStatus", "timestamp") if k in result}}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--url", required=True, help="OpenMetadata address, e.g. http://openmetadata.local:8585")
    parser.add_argument("--include", nargs="+", default=["*"],
                        help="table FQN patterns (fnmatch), e.g. 'trino_lakehouse.iceberg_curated.*'")
    parser.add_argument("--max-tables", type=int, default=300, help="stop after this many tables (default %(default)s)")
    parser.add_argument("--out", default="lakehouse.om-snapshot.json")
    parser.add_argument("--timeout", type=float, default=30)
    args = parser.parse_args()

    token = os.environ.get("OM_TOKEN") or getpass.getpass("OpenMetadata token (JWT): ")
    client = Client(args.url, token.strip(), args.timeout)
    version = client.get("/system/version")
    print(f"OpenMetadata {version.get('version')} at {client.api}")

    tables, after, listed = [], None, 0
    while len(tables) < args.max_tables:
        params = {"limit": 100, "include": "non-deleted", **({"after": after} if after else {})}
        page = client.get_fields("table", "/tables", params, TABLE_FIELDS, TABLE_FIELD_VARIANTS)
        for table in page.get("data") or []:
            listed += 1
            if any(fnmatch.fnmatchcase(table.get("fullyQualifiedName", ""), p) for p in args.include):
                tables.append(table)
        after = (page.get("paging") or {}).get("after")
        if not after:
            break
    tables = tables[: args.max_tables]
    print(f"{listed} tables listed, {len(tables)} match {args.include} (fields: {client.fields.get('table')})")

    snapshot = {"format": "lakehouse-om-snapshot/1", "recorded_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                "source": args.url, "version": {"version": version.get("version")},
                "tables": [], "profiles": {}, "lineage": {}, "testCases": {}}
    for n, table in enumerate(tables, 1):
        fqn = table["fullyQualifiedName"]
        snapshot["tables"].append(clean_table(table))
        try:
            profile = client.get(f"/tables/{q(fqn)}/tableProfile/latest").get("profile")
            if profile:
                snapshot["profiles"][fqn] = {k: profile[k] for k in ("timestamp", "rowCount", "columnCount",
                                                                     "sizeInByte") if k in profile}
        except HTTPError as err:
            print(f"  {fqn}: no profile ({err.status})")
        try:
            snapshot["lineage"][fqn] = clean_lineage(
                client.get(f"/lineage/table/name/{q(fqn)}", {"upstreamDepth": 1, "downstreamDepth": 1}))
        except HTTPError as err:
            print(f"  {fqn}: no lineage ({err.status})")
        try:
            page = client.get_fields("testcase", "/dataQuality/testCases",
                                     {"entityLink": f"<#E::table::{fqn}>", "includeAllTests": "true", "limit": 50},
                                     "", TEST_CASE_FIELD_VARIANTS)
            cases = [clean_test(c) for c in page.get("data") or []]
            if cases:
                snapshot["testCases"][fqn] = cases
        except HTTPError as err:
            print(f"  {fqn}: no tests ({err.status})")
        if n % 20 == 0:
            print(f"  {n}/{len(tables)}")

    with open(args.out, "w", encoding="utf-8") as fh:
        json.dump(snapshot, fh, ensure_ascii=False, indent=1)
    print(f"Wrote {args.out}: {len(snapshot['tables'])} tables, {len(snapshot['profiles'])} profiles, "
          f"{sum(1 for v in snapshot['lineage'].values() if v['nodes'])} with lineage, "
          f"{len(snapshot['testCases'])} with tests")


if __name__ == "__main__":
    try:
        main()
    except HTTPError as err:
        sys.exit(f"OpenMetadata refused the request: {err}")
    except OSError as err:
        sys.exit(f"Cannot reach OpenMetadata: {err}")
