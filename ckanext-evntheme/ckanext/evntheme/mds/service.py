"""Queries, import and export for the shared code lists (MDS).

Views and helpers only talk to this module, never to the ORM directly, so the
storage can change (e.g. move to a dedicated MDS service) without touching templates.
"""
from __future__ import annotations

import csv
import datetime as dt
import io
import json
import logging
from collections.abc import Iterable
from dataclasses import dataclass, field
from typing import Any

import sqlalchemy as sa

import ckan.model as model

from ckanext.evntheme import config
from ckanext.evntheme.cache import ttl_cache
from ckanext.evntheme.mds.model import MdsCatalog, MdsCode, MdsConsumer, MdsVersion
from ckanext.evntheme.vocab import MDS_CATALOG_STATUSES, MDS_CODE_STATUSES, MDS_CONSUMER_STATUSES

log = logging.getLogger(__name__)

_tables_ready = False


def tables_ready() -> bool:
    """True once `ckan db upgrade -p evntheme` has created the tables (checked until it is)."""
    global _tables_ready
    if not _tables_ready:
        _tables_ready = sa.inspect(model.meta.engine).has_table(MdsCatalog.__tablename__)
        if not _tables_ready:
            log.warning("evntheme: MDS tables missing, run `ckan db upgrade -p evntheme`")
    return _tables_ready


# --- Read ----------------------------------------------------------------------


@dataclass
class TreeItem:
    code: str
    name: str
    code_count: int


@dataclass
class TreeGroup:
    name: str
    items: list[TreeItem] = field(default_factory=list)


@dataclass
class CodeRow:
    code: MdsCode
    level: int


@dataclass
class CatalogPage:
    catalog: MdsCatalog
    rows: list[CodeRow]

    @property
    def levels(self) -> int:
        return max((r.level for r in self.rows), default=0)

    @property
    def has_counts(self) -> bool:
        return any(r.code.item_count is not None for r in self.rows)


@dataclass(frozen=True)
class Summary:
    catalogs: int = 0
    active_codes: int = 0
    consumer_systems: int = 0


def _published():
    return model.Session.query(MdsCatalog).filter(MdsCatalog.status != "draft")


def catalog_tree() -> list[TreeGroup]:
    if not tables_ready():
        return []
    counts = dict(
        model.Session.query(MdsCode.catalog_id, sa.func.count(MdsCode.id)).group_by(MdsCode.catalog_id).all()
    )
    groups: dict[str, TreeGroup] = {}
    for catalog in _published().order_by(MdsCatalog.position, MdsCatalog.name):
        group = groups.setdefault(catalog.group, TreeGroup(catalog.group))
        group.items.append(TreeItem(catalog.code, catalog.name, counts.get(catalog.id, 0)))
    return list(groups.values())


def _levels(codes: Iterable[MdsCode]) -> dict[str, int]:
    parents = {c.code: c.parent_code for c in codes}
    levels: dict[str, int] = {}

    def level(code: str, seen: frozenset[str] = frozenset()) -> int:
        if code not in levels:
            parent = parents.get(code)
            levels[code] = 1 if not parent or parent not in parents or parent in seen else (
                level(parent, seen | {code}) + 1
            )
        return levels[code]

    for code in parents:
        level(code)
    return levels


def get_catalog(code: str) -> CatalogPage | None:
    if not tables_ready():
        return None
    catalog = _published().filter(MdsCatalog.code == code).one_or_none()
    if catalog is None:
        return None
    levels = _levels(catalog.codes)
    return CatalogPage(catalog, [CodeRow(c, levels[c.code]) for c in catalog.codes])


def first_catalog_code() -> str | None:
    tree = catalog_tree()
    return tree[0].items[0].code if tree and tree[0].items else None


@ttl_cache(lambda: config.get("stats_cache_seconds"))
def summary() -> Summary:
    if not tables_ready():
        return Summary()
    published = _published().subquery()
    active_codes = (
        model.Session.query(sa.func.count(MdsCode.id))
        .join(published, published.c.id == MdsCode.catalog_id)
        .filter(MdsCode.status.in_(["active", "new"]))
        .scalar()
    )
    systems = model.Session.query(sa.func.count(sa.distinct(MdsConsumer.system_name))).scalar()
    return Summary(_published().count(), active_codes or 0, systems or 0)


# --- Import / export -------------------------------------------------------------


def _date(value: Any) -> dt.date | None:
    if not value:
        return None
    return value if isinstance(value, dt.date) else dt.date.fromisoformat(str(value))


def _check(value: str, allowed: dict[str, Any], what: str) -> str:
    if value not in allowed:
        raise ValueError(f"{what}: unknown status {value!r}, expected one of {sorted(allowed)}")
    return value


def load(data: dict[str, Any]) -> MdsCatalog:
    """Create or replace one catalog (with codes, versions, consumers) from a dict.

    Format: see ckanext/evntheme/demo/mds.json. Does not commit.
    """
    try:
        code = data["code"]
        name = data["name"]
    except KeyError as err:
        raise ValueError(f"catalog is missing {err.args[0]!r}") from err

    catalog = model.Session.query(MdsCatalog).filter_by(code=code).one_or_none()
    if catalog is None:
        catalog = MdsCatalog(code=code)
    else:
        # Delete the old children first: the unit of work would otherwise insert the
        # new codes before deleting the old ones and hit UNIQUE(catalog_id, code).
        catalog.codes, catalog.versions, catalog.consumers = [], [], []
        model.Session.flush()
    catalog.name = name
    catalog.group = data.get("group", "")
    catalog.position = int(data.get("position", 0))
    catalog.description = data.get("description", "")
    catalog.version = str(data.get("version", ""))
    catalog.effective_from = _date(data.get("effective_from"))
    catalog.status = _check(data.get("status", "active"), MDS_CATALOG_STATUSES, code)
    catalog.issuer = data.get("issuer", "")
    catalog.sync_note = data.get("sync_note", "")
    catalog.name_label = data.get("name_label", "")
    catalog.count_label = data.get("count_label", "")
    catalog.codes = [
        MdsCode(
            code=row["code"],
            name=row["name"],
            parent_code=row.get("parent") or None,
            item_count=row.get("count"),
            status=_check(row.get("status", "active"), MDS_CODE_STATUSES, f"{code}/{row['code']}"),
            position=i,
        )
        for i, row in enumerate(data.get("codes", []))
    ]
    catalog.versions = [
        MdsVersion(version=str(v["version"]), note=v.get("note", ""), released_on=_date(v.get("date")))
        for v in data.get("versions", [])
    ]
    catalog.consumers = [
        MdsConsumer(
            system_name=c["name"],
            sync_note=c.get("sync", ""),
            status=_check(c.get("status", "ok"), MDS_CONSUMER_STATUSES, f"{code}/{c['name']}"),
            position=i,
        )
        for i, c in enumerate(data.get("consumers", []))
    ]
    model.Session.add(catalog)
    return catalog


def load_many(payload: Any) -> list[MdsCatalog]:
    """Load a list of catalogs, or {"catalogs": [...]}, then commit once."""
    items = payload.get("catalogs", []) if isinstance(payload, dict) else payload
    try:
        catalogs = [load(item) for item in items]
        model.Session.commit()
    except Exception:
        model.Session.rollback()
        raise
    return catalogs


EXPORT_COLUMNS = ("code", "name", "parent_code", "item_count", "status")


def export(page: CatalogPage, fmt: str) -> tuple[bytes, str]:
    """Return (body, mimetype) for a catalog download. `fmt` is 'csv' or 'json'."""
    rows = [{col: getattr(r.code, col) for col in EXPORT_COLUMNS} for r in page.rows]
    if fmt == "csv":
        buffer = io.StringIO()
        writer = csv.DictWriter(buffer, fieldnames=EXPORT_COLUMNS)
        writer.writeheader()
        writer.writerows(rows)
        # BOM so Excel opens Vietnamese text correctly.
        return ("﻿" + buffer.getvalue()).encode("utf-8"), "text/csv; charset=utf-8"
    if fmt == "json":
        catalog = page.catalog
        body = {
            "code": catalog.code,
            "name": catalog.name,
            "version": catalog.version,
            "effective_from": catalog.effective_from.isoformat() if catalog.effective_from else None,
            "issuer": catalog.issuer,
            "codes": rows,
        }
        return json.dumps(body, ensure_ascii=False, indent=2).encode("utf-8"), "application/json"
    raise ValueError(f"unsupported export format {fmt!r}")
