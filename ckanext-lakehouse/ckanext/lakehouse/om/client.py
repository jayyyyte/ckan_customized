"""Read-only client for the OpenMetadata REST API (/api/v1).

Only GET requests, and never `sampleData`: CKAN publishes metadata, not table contents.

OpenMetadata renamed two table fields across 1.x releases (`owner` -> `owners`,
`domain` -> `domains`) and answers 400 "Invalid field name" for the name it does not
know. The client tries the newest spelling first and remembers the first one the
server accepts; `ckanext.lakehouse.om.mapping` reads both shapes.
"""
from __future__ import annotations

import logging
from collections.abc import Iterator, Sequence
from typing import Any
from urllib.parse import quote

import requests

log = logging.getLogger(__name__)

# Table fields the portal uses, without the renamed ones.
TABLE_FIELDS = "columns,tags,tableConstraints,usageSummary,followers"
# Renamed fields, newest spelling first.
TABLE_FIELD_VARIANTS = ("owners,domains", "owners,domain", "owner,domain", "owner")
TEST_CASE_FIELD_VARIANTS = ("testCaseResult,testDefinition", "testDefinition", "")
PAGE_SIZE = 100


class OMError(Exception):
    """OpenMetadata could not be reached or refused the request."""

    def __init__(self, message: str, status: int | None = None) -> None:
        super().__init__(message)
        self.status = status


def quote_fqn(fqn: str) -> str:
    return quote(fqn, safe="")


def entity_link(fqn: str) -> str:
    """Entity link of a table, the filter of the test case API."""
    return f"<#E::table::{fqn}>"


class OMClient:
    def __init__(self, base_url: str, token: str = "", timeout: float = 10, verify: bool = True,
                 session: Any = None) -> None:
        if not base_url:
            raise OMError("OpenMetadata is not configured (ckanext.lakehouse.om.url)")
        self.api = base_url.rstrip("/") + "/api/v1"
        self.timeout = timeout
        self.verify = verify
        self.session = session or requests.Session()
        self.headers = {"Accept": "application/json"}
        if token:
            self.headers["Authorization"] = f"Bearer {token}"
        self._fields: dict[str, str] = {}

    # --- transport ---------------------------------------------------------------------

    def get(self, path: str, params: dict[str, Any] | None = None) -> Any:
        url = self.api + path
        try:
            response = self.session.get(url, params=params or {}, headers=self.headers,
                                        timeout=self.timeout, verify=self.verify)
        except requests.RequestException as err:
            raise OMError(f"cannot reach OpenMetadata: {err.__class__.__name__}") from err
        if response.status_code >= 400:
            raise OMError(f"GET {path}: HTTP {response.status_code} {_message(response)}",
                          response.status_code)
        try:
            return response.json()
        except ValueError as err:
            raise OMError(f"GET {path}: not JSON") from err

    def _get_fields(self, kind: str, path: str, params: dict[str, Any], base: str,
                    variants: Sequence[str]) -> Any:
        """GET with the first `fields` spelling the server accepts (remembered per kind)."""
        known = self._fields.get(kind)
        candidates = [known] if known is not None else list(variants)
        last: OMError | None = None
        for variant in candidates:
            fields = ",".join(part for part in (base, variant) if part)
            try:
                result = self.get(path, {**params, "fields": fields} if fields else params)
            except OMError as err:
                if err.status == 400 and "field" in str(err).lower():
                    last = err
                    continue
                raise
            self._fields[kind] = variant
            return result
        raise last or OMError(f"GET {path}: no accepted fields")

    # --- endpoints --------------------------------------------------------------------

    def version(self) -> str:
        return str(self.get("/system/version").get("version", "?"))

    def iter_tables(self, schema_fqn: str | None = None) -> Iterator[dict[str, Any]]:
        params: dict[str, Any] = {"limit": PAGE_SIZE, "include": "non-deleted"}
        if schema_fqn:
            params["databaseSchema"] = schema_fqn
        while True:
            page = self._get_fields("table", "/tables", params, TABLE_FIELDS, TABLE_FIELD_VARIANTS)
            yield from page.get("data") or []
            after = (page.get("paging") or {}).get("after")
            if not after:
                return
            params = {**params, "after": after}

    def table(self, fqn: str) -> dict[str, Any]:
        return self._get_fields("table", f"/tables/name/{quote_fqn(fqn)}", {}, TABLE_FIELDS,
                                TABLE_FIELD_VARIANTS)

    def profile(self, fqn: str) -> dict[str, Any] | None:
        """Latest table-level profile (rowCount, columnCount, timestamp); None if never profiled.

        Column profiles (min/max/... i.e. real values) are dropped on purpose.
        """
        try:
            table = self.get(f"/tables/{quote_fqn(fqn)}/tableProfile/latest")
        except OMError as err:
            if err.status == 404:
                return None
            raise
        return table.get("profile") or None

    def lineage(self, fqn: str, depth: int = 1) -> dict[str, Any]:
        return self.get(f"/lineage/table/name/{quote_fqn(fqn)}",
                        {"upstreamDepth": depth, "downstreamDepth": depth})

    def test_cases(self, fqn: str, limit: int = 50) -> list[dict[str, Any]]:
        params = {"entityLink": entity_link(fqn), "includeAllTests": "true", "limit": limit}
        page = self._get_fields("testcase", "/dataQuality/testCases", params, "", TEST_CASE_FIELD_VARIANTS)
        return page.get("data") or []


def _message(response: Any) -> str:
    try:
        body = response.json()
    except ValueError:
        return (response.text or "")[:200]
    return str(body.get("message") or body)[:200] if isinstance(body, dict) else str(body)[:200]
