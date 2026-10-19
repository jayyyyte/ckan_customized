#!/usr/bin/env python3
"""Stand-in for the OpenMetadata REST API, serving a snapshot file (Python 3.8+, stdlib only).

The real OpenMetadata is only reachable from the company network. Record a snapshot
there with om_snapshot.py, copy it here, and point CKAN at this server:

    python3 tools/openmetadata/om_mock.py SNAPSHOT.json --port 8585 [--token T] [--legacy]
    ckanext.lakehouse.om.url = http://localhost:8585

It answers the endpoints ckanext-lakehouse calls (tables, profiles, lineage, test cases,
and teams/domains/users for `om scaffold` and user owners), with OpenMetadata's paging and its
400 "Invalid field name" for unknown `fields`. `--legacy` mimics releases before 1.5
(`owner`/`domain` instead of `owners`/`domains`, also on teams and domains). Read-only; anything else is 404.
"""
from __future__ import annotations

import argparse
import json
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, unquote, urlsplit

TABLE_FIELDS = {"columns", "tags", "tableConstraints", "usageSummary", "followers", "extension",
                "tablePartition", "customMetrics", "joins", "schemaDefinition", "dataModel", "testSuite",
                "dataProducts", "lifeCycle", "sourceHash", "votes"}
TEST_CASE_FIELDS = {"testCaseResult", "testDefinition", "testSuite", "owners", "tags", "incidentId"}
TEAM_FIELDS = {"users", "defaultRoles", "parents", "children", "policies", "userCount", "childrenCount",
               "owns", "profile", "domains"}
DOMAIN_FIELDS = {"experts", "parent", "children", "tags", "followers"}
USER_FIELDS = {"teams", "roles", "profile", "owns", "follows", "personas", "defaultPersona", "domains"}


class Snapshot:
    def __init__(self, data: dict, legacy: bool) -> None:
        self.version = data.get("version") or {"version": "mock"}
        self.legacy = legacy
        self.tables = [self._shape(t) for t in data.get("tables", [])]
        self.by_fqn = {t["fullyQualifiedName"]: t for t in self.tables}
        self.profiles = data.get("profiles", {})
        self.lineage = data.get("lineage", {})
        self.test_cases = data.get("testCases", {})
        self.teams = [self._owned(t) for t in data.get("teams", [])]
        self.domains = [self._owned(d) for d in data.get("domains", [])]
        self.users = data.get("users", [])
        self.users_by_name = {u["name"]: u for u in self.users}

    def _owned(self, entity: dict) -> dict:
        """Teams and domains: `owners`, or `owner` with --legacy."""
        entity = dict(entity)
        owners = entity.pop("owners", None) or ([entity.pop("owner")] if entity.get("owner") else [])
        if self.legacy:
            if owners:
                entity["owner"] = owners[0]
        else:
            entity["owners"] = owners
        return entity

    def owner_fields(self) -> set:
        return {"owner"} if self.legacy else {"owners"}

    def _shape(self, table: dict) -> dict:
        table = dict(table)
        owners = table.pop("owners", None) or ([table.pop("owner")] if table.get("owner") else [])
        domains = table.pop("domains", None) or ([table.pop("domain")] if table.get("domain") else [])
        if self.legacy:
            if owners:
                table["owner"] = owners[0]
            if domains:
                table["domain"] = domains[0]
        else:
            table["owners"] = owners
            if domains:
                table["domains"] = domains
        return table

    def table_fields(self) -> set:
        return TABLE_FIELDS | ({"owner", "domain"} if self.legacy else {"owners", "domains"})


class Handler(BaseHTTPRequestHandler):
    snapshot: Snapshot
    token: str = ""

    def log_message(self, fmt: str, *args: object) -> None:
        sys.stderr.write("om-mock %s\n" % (fmt % args))

    def _send(self, status: int, body: object) -> None:
        payload = json.dumps(body, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def _error(self, status: int, message: str) -> None:
        self._send(status, {"code": status, "message": message})

    def _check_fields(self, query: dict, allowed: set) -> bool:
        for name in ",".join(query.get("fields", [""])).split(","):
            if name and name not in allowed:
                self._error(400, f"Invalid field name {name}")
                return False
        return True

    def _page(self, query: dict, items: list) -> None:
        limit = int(query.get("limit", ["10"])[0])
        start = int(query.get("after", ["0"])[0])
        paging = {"total": len(items)}
        if start + limit < len(items):
            paging["after"] = str(start + limit)
        self._send(200, {"data": items[start:start + limit], "paging": paging})

    def do_GET(self) -> None:  # http.server API
        if self.token and self.headers.get("Authorization") != f"Bearer {self.token}":
            return self._error(401, "Not authorized; missing or wrong bearer token")
        url = urlsplit(self.path)
        query = parse_qs(url.query)
        path = url.path
        snap = self.snapshot
        prefix = "/api/v1"
        if not path.startswith(prefix):
            return self._error(404, "not found")
        path = path[len(prefix):]

        if path == "/system/version":
            return self._send(200, snap.version)

        if path == "/tables":
            if not self._check_fields(query, snap.table_fields()):
                return None
            tables = snap.tables
            for param in ("service", "database", "databaseSchema"):
                if param in query:
                    head = query[param][0] + "."
                    tables = [t for t in tables if t["fullyQualifiedName"].startswith(head)]
            return self._page(query, tables)

        if path.startswith("/tables/name/"):
            if not self._check_fields(query, snap.table_fields()):
                return None
            table = snap.by_fqn.get(unquote(path[len("/tables/name/"):]))
            return self._send(200, table) if table else self._error(404, "table instance not found")

        if path.startswith("/tables/") and path.endswith("/tableProfile/latest"):
            fqn = unquote(path[len("/tables/"):-len("/tableProfile/latest")])
            if fqn not in snap.by_fqn:
                return self._error(404, "table instance not found")
            profile = snap.profiles.get(fqn)
            body = {"fullyQualifiedName": fqn}
            if profile:
                body["profile"] = profile
            return self._send(200, body)

        if path.startswith("/lineage/table/name/"):
            fqn = unquote(path[len("/lineage/table/name/"):])
            table = snap.by_fqn.get(fqn)
            if not table:
                return self._error(404, "table instance not found")
            lineage = snap.lineage.get(fqn) or {}
            entity = {"id": table["id"], "type": "table", "name": table["name"], "fullyQualifiedName": fqn}
            return self._send(200, {"entity": entity, "nodes": lineage.get("nodes", []),
                                    "upstreamEdges": lineage.get("upstreamEdges", []),
                                    "downstreamEdges": lineage.get("downstreamEdges", [])})

        if path == "/dataQuality/testCases":
            if not self._check_fields(query, TEST_CASE_FIELDS):
                return None
            link = query.get("entityLink", [""])[0]
            fqn = link[len("<#E::table::"):].rstrip(">").split("::")[0] if link.startswith("<#E::table::") else ""
            cases = snap.test_cases.get(fqn, [])
            limit = int(query.get("limit", ["10"])[0])
            return self._send(200, {"data": cases[:limit], "paging": {"total": len(cases)}})

        if path == "/teams":
            if not self._check_fields(query, TEAM_FIELDS | snap.owner_fields()):
                return None
            return self._page(query, snap.teams)

        if path == "/domains":
            if not self._check_fields(query, DOMAIN_FIELDS | snap.owner_fields()):
                return None
            return self._page(query, snap.domains)

        if path == "/users":
            if not self._check_fields(query, USER_FIELDS):
                return None
            return self._page(query, snap.users)  # the snapshot holds no bots

        if path.startswith("/users/name/"):
            if not self._check_fields(query, USER_FIELDS):
                return None
            user = snap.users_by_name.get(unquote(path[len("/users/name/"):]))
            return self._send(200, user) if user else self._error(404, "user instance not found")

        return self._error(404, f"no mock for {path}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("snapshot", help="snapshot JSON (om_snapshot.py output, or sample-snapshot.json)")
    parser.add_argument("--host", default="127.0.0.1", help="0.0.0.0 to serve containers/kind (default %(default)s)")
    parser.add_argument("--port", type=int, default=8585)
    parser.add_argument("--token", default="", help="require this bearer token")
    parser.add_argument("--legacy", action="store_true", help="answer like OpenMetadata < 1.5 (owner/domain)")
    args = parser.parse_args()
    with open(args.snapshot, encoding="utf-8") as fh:
        Handler.snapshot = Snapshot(json.load(fh), args.legacy)
    Handler.token = args.token
    server = ThreadingHTTPServer((args.host, args.port), Handler)
    print(f"om-mock: {len(Handler.snapshot.tables)} tables on http://{args.host}:{args.port} "
          f"({'legacy' if args.legacy else 'current'} fields)", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
