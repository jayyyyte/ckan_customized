"""Sync CKAN datasets from tables catalogued in OpenMetadata (`ckan evntheme sync-openmetadata`).

Each OpenMetadata Table becomes one CKAN dataset with a single resource: the Trino JDBC
connection for its catalog/schema — no data is copied by default, matching the existing
pattern for curated/gold resources (docs/ckan-overview.md). Column names and descriptions
from OpenMetadata are written to the resource's Data Dictionary. If Trino credentials are
configured, up to `openmetadata_preview_rows` rows are also queried live and loaded into the
resource's DataStore, so the dataset page shows a real preview instead of just the JDBC link.

Also writes `om_fqn`, `om_id`, `om_columns` and related `om_*` extras so the dataset page
automatically displays the "Danh mục kỹ thuật" (Technical catalog) tab from `ckanext-lakehouse`
with live lineage, data quality test results, table profile and offline column fallback.

Safe to run repeatedly, e.g. from a CronJob: datasets are looked up and updated by a name
derived from the table's fully qualified name, never duplicated, and a table removed from
OpenMetadata simply stops being touched (its CKAN dataset is left in place).
"""
from __future__ import annotations

import datetime as dt
import decimal
import json
import logging
import re
from collections.abc import Callable, Iterator
from dataclasses import dataclass, field
from typing import Any
from urllib.parse import quote

import requests

import ckan.model as model
import ckan.plugins.toolkit as tk

log = logging.getLogger(__name__)

TABLE_FIELDS = "description,tags,database,databaseSchema,columns"
PAGE_SIZE = 100
MAX_COLUMNS = 500
TIER_PREFIX = "tier."


class OpenMetadataError(Exception):
    """The OpenMetadata API could not be reached or returned something unexpected."""


class TrinoError(Exception):
    """The Trino query for a data preview failed. Never fatal: the dataset/resource sync
    already succeeded, only the preview is skipped."""


@dataclass
class Column:
    name: str
    description: str
    data_type: str = ""
    constraint: str = ""


@dataclass
class Table:
    fqn: str
    name: str
    display_name: str
    description: str
    catalog: str
    schema: str
    tags: list[str]
    tag_fqns: list[str]
    columns: list[Column] = field(default_factory=list)
    id: str = ""
    service: str = ""
    service_type: str = ""
    table_type: str = ""
    updated_at: str = ""

    @property
    def dataset_name(self) -> str:
        """A valid, stable CKAN package name: the same table always slugs to the same name."""
        slug = re.sub(r"[^a-z0-9_-]+", "-", self.fqn.lower()).strip("-")
        return slug[:100] or "table"

    @property
    def tier(self) -> str:
        for fqn in self.tag_fqns:
            if fqn.lower().startswith(TIER_PREFIX):
                return fqn.split(".", 1)[1]
        return ""

    @property
    def source_system(self) -> str:
        return " · ".join(filter(None, (self.service_type, self.service)))

    def om_columns_json(self) -> str:
        """Compact column list stored in `om_columns` for the Technical catalog tab's offline fallback."""
        items = []
        for col in self.columns[:MAX_COLUMNS]:
            item: dict[str, str] = {"name": col.name, "type": col.data_type}
            if col.description:
                item["description"] = col.description
            if col.constraint:
                item["constraint"] = col.constraint
            items.append(item)
        return json.dumps(items, ensure_ascii=False, separators=(",", ":"))

    def om_extras(self, ui_url: str = "") -> dict[str, str]:
        """Extras written by the sync so both evntheme and ckanext-lakehouse's Technical catalog tab work."""
        om_url = f"{ui_url.rstrip('/')}/table/{quote(self.fqn, safe='')}" if ui_url else ""
        candidates = {
            "synced_from": "openmetadata",
            "openmetadata_fqn": self.fqn,
            "om_fqn": self.fqn,
            "om_id": self.id,
            "om_url": om_url,
            "om_service": self.service,
            "om_service_type": self.service_type,
            "om_table_type": self.table_type,
            "om_tier": self.tier,
            "om_updated_at": self.updated_at,
            "om_columns": self.om_columns_json(),
            "data_type": "Bảng dữ liệu (Trino/Iceberg)",
        }
        return {k: v for k, v in candidates.items() if v != ""}


def _normalize_api_url(base_url: str) -> str:
    base = base_url.rstrip("/")
    if base.endswith("/api/v1"):
        return base[:-3]
    if not base.endswith("/api"):
        return f"{base}/api"
    return base


class OpenMetadataClient:
    def __init__(self, base_url: str, token: str = "") -> None:
        self.base_url = _normalize_api_url(base_url)
        self._headers = {"Authorization": f"Bearer {token}"} if token else {}

    def _get(self, path: str, **params: Any) -> dict[str, Any]:
        url = f"{self.base_url}{path}"
        try:
            response = requests.get(url, params=params, headers=self._headers, timeout=10)
            response.raise_for_status()
        except requests.RequestException as err:
            raise OpenMetadataError(f"OpenMetadata API {url} failed: {err}") from err
        return response.json()

    def tables(self, service: str = "", tag: str = "") -> Iterator[Table]:
        """Every Table entity, paged with OpenMetadata's cursor (`paging.after`).

        `tag` selects which data gets published: only tables carrying that OpenMetadata tag
        (e.g. a classification `CKAN.Publish`, or a tier like `Tier.Gold`) are returned.
        A data steward publishes or unpublishes a table by tagging it in OpenMetadata, without
        touching CKAN config. Filtered here rather than via the API's own query params, since
        not every OpenMetadata version accepts the same tag filter syntax.
        """
        after = None
        while True:
            params: dict[str, Any] = {"fields": TABLE_FIELDS, "limit": PAGE_SIZE}
            if service:
                params["service"] = service
            if after:
                params["after"] = after
            page = self._get("/v1/tables", **params)
            for entity in page.get("data", []):
                table = _to_table(entity)
                if tag and tag not in table.tag_fqns:
                    continue
                yield table
            after = page.get("paging", {}).get("after")
            if not after:
                return


def _format_updated_at(millis: Any) -> str:
    if not isinstance(millis, int | float):
        return ""
    return dt.datetime.fromtimestamp(millis / 1000, tz=dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _to_table(entity: dict[str, Any]) -> Table:
    database = entity.get("database") or {}
    schema = entity.get("databaseSchema") or {}
    service = entity.get("service") or {}
    fqn = entity["fullyQualifiedName"]
    tag_fqns = [t["tagFQN"] for t in entity.get("tags", []) if t.get("tagFQN")]
    tags = [t_fqn.rsplit(".", 1)[-1] for t_fqn in tag_fqns]
    columns = [
        Column(
            name=c["name"],
            description=c.get("description") or "",
            data_type=c.get("dataTypeDisplay") or c.get("dataType") or "",
            constraint=c.get("constraint") or "",
        )
        for c in entity.get("columns", [])
    ]
    return Table(
        fqn=fqn,
        name=entity["name"],
        display_name=entity.get("displayName") or entity["name"],
        description=entity.get("description") or "",
        catalog=database.get("name", ""),
        schema=schema.get("name", ""),
        tags=tags,
        tag_fqns=tag_fqns,
        columns=columns,
        id=str(entity.get("id") or ""),
        service=service.get("name") or fqn.split(".", 1)[0],
        service_type=entity.get("serviceType") or "",
        table_type=entity.get("tableType") or "",
        updated_at=_format_updated_at(entity.get("updatedAt")),
    )


@dataclass
class TrinoConfig:
    host: str  # "host:port", same value used to build the JDBC resource URL
    user: str
    password: str

    @property
    def hostname(self) -> str:
        return self.host.split(":", 1)[0]

    @property
    def port(self) -> int:
        parts = self.host.split(":", 1)
        return int(parts[1]) if len(parts) > 1 else 8080


def _field_type(value: Any) -> str:
    """DataStore/Postgres type for one Python value returned by the Trino driver."""
    if isinstance(value, bool):
        return "bool"
    if isinstance(value, (int, float, decimal.Decimal)):
        return "numeric"
    if isinstance(value, (dt.date, dt.datetime)):
        return "timestamp"
    return "text"


def _json_safe(value: Any) -> Any:
    """DataStore records go through the API as JSON: give it types it accepts."""
    if isinstance(value, decimal.Decimal):
        return float(value)
    if isinstance(value, (dt.date, dt.datetime)):
        return value.isoformat()
    return value


def _connect(cfg: TrinoConfig, catalog: str, schema: str) -> Any:
    try:
        import trino  # heavy optional import: only needed when a query is actually made
    except ImportError as err:
        raise TrinoError("the 'trino' package is not installed") from err
    return trino.dbapi.connect(
        host=cfg.hostname,
        port=cfg.port,
        user=cfg.user,
        catalog=catalog,
        schema=schema,
        http_scheme="http",
        auth=trino.auth.BasicAuthentication(cfg.user, cfg.password) if cfg.password else None,
    )


def _query_trino(cfg: TrinoConfig, table: Table, limit: int) -> tuple[list[str], list[list[Any]]]:
    conn = None
    try:
        conn = _connect(cfg, table.catalog, table.schema)
        cur = conn.cursor()
        cur.execute(f'SELECT * FROM "{table.name}" LIMIT {int(limit)}')
        rows = cur.fetchall()
        columns = [d[0] for d in cur.description]
    except TrinoError:
        raise
    except Exception as err:  # noqa: BLE001 - the trino driver raises its own exception types
        raise TrinoError(f"query on {table.catalog}.{table.schema}.{table.name} failed: {err}") from err
    finally:
        if conn is not None:
            conn.close()
    return columns, rows


def open_cursor(cfg: TrinoConfig, catalog: str, schema: str, table_name: str) -> tuple[Any, list[str], Any]:
    """Unbounded `SELECT *`, for streaming a full export (`downloads.py`). Returns
    (connection, column names, cursor); the caller must close the connection when done."""
    conn = None
    try:
        conn = _connect(cfg, catalog, schema)
        cur = conn.cursor()
        cur.execute(f'SELECT * FROM "{table_name}"')
        columns = [d[0] for d in cur.description]
    except TrinoError:
        raise
    except Exception as err:  # noqa: BLE001
        if conn is not None:
            conn.close()
        raise TrinoError(f"query on {catalog}.{schema}.{table_name} failed: {err}") from err
    return conn, columns, cur


def refresh_datastore_preview(
    action: Callable[[str, dict[str, Any]], Any],
    trino: TrinoConfig,
    resource_id: str,
    table: Table,
    preview_rows: int,
) -> None:
    """Query up to `preview_rows` rows from Trino and (re)load them into `resource_id`'s
    DataStore, with column descriptions from OpenMetadata as the Data Dictionary."""
    columns, rows = _query_trino(trino, table, preview_rows)
    notes = {c.name.lower(): c.description for c in table.columns if c.description}
    types = ["text"] * len(columns)
    for row in rows:
        for i, value in enumerate(row):
            if value is not None and types[i] == "text":
                types[i] = _field_type(value)
    fields = [
        {"id": name, "type": ftype, "info": {"notes": notes.get(name.lower(), "")}}
        for name, ftype in zip(columns, types, strict=False)
    ]
    records = [dict(zip(columns, (_json_safe(v) for v in row), strict=False)) for row in rows]
    try:
        action("datastore_delete", {"resource_id": resource_id, "force": True})
    except tk.ObjectNotFound:
        pass
    action("datastore_create", {
        "resource_id": resource_id, "force": True, "fields": fields, "records": records,
    })
    existing = action("resource_view_list", {"id": resource_id})
    if not any(v["view_type"] == "datatables_view" for v in existing):
        action("resource_view_create", {
            "resource_id": resource_id, "view_type": "datatables_view", "title": tk._("Xem trước"),
        })


class Syncer:
    """Upserts one CKAN dataset per OpenMetadata table, run as a real sysadmin so the change
    shows in the activity stream (activity by the site user is hidden by CKAN)."""

    def __init__(
        self, username: str, owner_org: str, trino_host: str,
        trino: TrinoConfig | None = None, preview_rows: int = 1000, ui_url: str = "",
    ) -> None:
        if model.User.by_name(username) is None:
            raise ValueError(f"user {username!r} does not exist; pass --user <sysadmin>")
        if not trino_host:
            raise ValueError("ckanext.evntheme.openmetadata_trino_host is not set")
        if not owner_org:
            raise ValueError("ckanext.evntheme.openmetadata_owner_org is not set")
        self.username = username
        self.owner_org = owner_org
        self.trino_host = trino_host
        self.trino = trino
        self.preview_rows = preview_rows
        self.ui_url = ui_url
        try:
            self._action("organization_show", {"id": owner_org})
        except tk.ObjectNotFound as err:
            raise ValueError(f"organisation {owner_org!r} does not exist; create it first") from err

    def _context(self) -> dict[str, Any]:
        return {"user": self.username, "ignore_auth": True}

    def _action(self, name: str, data: dict[str, Any]) -> Any:
        return tk.get_action(name)(self._context(), data)

    def sync(self, table: Table, dry_run: bool = False) -> str:
        """Create or update the dataset for one table. Returns "create" or "update"."""
        name = table.dataset_name
        try:
            existing = self._action("package_show", {"id": name})
        except tk.ObjectNotFound:
            existing = None
        action = "update" if existing else "create"
        if dry_run:
            return action

        om_extras = table.om_extras(self.ui_url)
        kept_extras = {
            e["key"]: e.get("value", "")
            for e in (existing.get("extras") or [])
            if e.get("key") and e["key"] not in om_extras and not e["key"].startswith("om_")
        } if existing else {}
        if table.source_system and not kept_extras.get("source_system"):
            kept_extras["source_system"] = table.source_system
        merged_extras = {**kept_extras, **om_extras}

        data = {
            "name": name,
            "title": table.display_name,
            "notes": table.description or (existing.get("notes") or "" if existing else ""),
            "owner_org": self.owner_org,
            "tags": [{"name": t} for t in table.tags],
            "extras": [{"key": k, "value": v} for k, v in sorted(merged_extras.items())],
        }
        pkg = self._action("package_patch", {**data, "id": existing["id"]}) if existing else self._action(
            "package_create", data,
        )
        resource = self._sync_resource(pkg, table)
        if self.trino and self.preview_rows > 0:
            try:
                self._refresh_preview(resource, table)
            except TrinoError as err:
                log.warning("preview for %s skipped: %s", table.fqn, err)
        return action

    def _sync_resource(self, pkg: dict[str, Any], table: Table) -> dict[str, Any]:
        data = {
            "package_id": pkg["id"],
            "name": table.display_name,
            "format": "JDBC",
            "url": f"jdbc:trino://{self.trino_host}/{table.catalog}/{table.schema}",
            "description": (
                f'Kết nối Trino JDBC. Truy vấn bảng: SELECT * FROM "{table.catalog}"."{table.schema}"."{table.name}"'
            ),
        }
        existing = next((r for r in pkg.get("resources", []) if r["name"] == table.display_name), None)
        if existing:
            return self._action("resource_patch", {**data, "id": existing["id"]})
        return self._action("resource_create", data)

    def _refresh_preview(self, resource: dict[str, Any], table: Table) -> None:
        """Query up to `preview_rows` rows from Trino and (re)load them into the resource's
        DataStore, with column descriptions from OpenMetadata as the Data Dictionary."""
        assert self.trino is not None
        refresh_datastore_preview(self._action, self.trino, resource["id"], table, self.preview_rows)

    def _ensure_grid_view(self, resource_id: str) -> None:
        """CKAN only auto-creates a preview view by resource format (`ckan.views.default_views`),
        and "JDBC" is not in that list. Without this, a DataStore-backed resource has data but no
        tab to show it in."""
        existing = self._action("resource_view_list", {"id": resource_id})
        if any(v["view_type"] == "datatables_view" for v in existing):
            return
        self._action("resource_view_create", {
            "resource_id": resource_id, "view_type": "datatables_view", "title": tk._("Xem trước"),
        })
