"""Live OpenMetadata data for the dataset page's "Technical catalog" tab.

The OpenMetadata part (table, profile, lineage, tests) does not depend on the viewer
and is cached in Redis, shared by every uWSGI worker; failures are cached briefly so a
down OpenMetadata is not hammered. Links to other CKAN datasets are added per viewer,
after the cache, so private datasets stay invisible to those who cannot read them.

When OpenMetadata cannot be reached the tab falls back to what the last sync stored on
the dataset (the `om_columns` extra).
"""
from __future__ import annotations

import datetime as dt
import hashlib
import json
import logging
import re
from typing import Any
from urllib.parse import quote

import ckan.model as model
import ckan.plugins.toolkit as tk
from ckan.lib.redis import connect_to_redis

from ckanext.lakehouse import config
from ckanext.lakehouse.om import mapping
from ckanext.lakehouse.om.client import OMClient, OMError

log = logging.getLogger(__name__)

CACHE_PREFIX = "ckanext-lakehouse:om:"
ERROR_TTL = 60
MAX_TESTS = 20
STATUSES = ("Success", "Failed", "Aborted", "Queued")
_COLUMN_LINK = re.compile(r"::columns::(?P<column>[^>]+)>$")


def extra(pkg: dict[str, Any], key: str) -> str:
    for item in pkg.get("extras") or []:
        if item.get("key") == key:
            return item.get("value") or ""
    return str(pkg.get(key) or "")


def has_panel(pkg: dict[str, Any]) -> bool:
    return bool(extra(pkg, mapping.Ext.FQN))


# --- fetching (cached) ------------------------------------------------------------------


def _client() -> OMClient:
    return OMClient(config.get("om.url"), config.get("om.api_token") or "",
                    timeout=config.get("om.timeout"), verify=config.get("om.verify_ssl"))


def _cache_key(fqn: str) -> str:
    return CACHE_PREFIX + hashlib.sha1(fqn.encode("utf-8")).hexdigest()


def _cached(fqn: str) -> dict[str, Any]:
    ttl = config.get("om.cache_ttl")
    redis = None
    if ttl > 0:
        try:
            redis = connect_to_redis()
            hit = redis.get(_cache_key(fqn))
            if hit:
                return json.loads(hit)
        except Exception as err:  # noqa: BLE001 - a cache outage must not break the page
            log.warning("om panel: Redis unavailable (%s)", err)
            redis = None
    data = fetch(fqn)
    if redis is not None:
        try:
            redis.setex(_cache_key(fqn), ERROR_TTL if data.get("error") else ttl, json.dumps(data))
        except Exception as err:  # noqa: BLE001
            log.warning("om panel: cannot cache (%s)", err)
    return data


def clear_cache(fqn: str) -> None:
    try:
        connect_to_redis().delete(_cache_key(fqn))
    except Exception:  # noqa: BLE001
        pass


def fetch(fqn: str, client: OMClient | None = None) -> dict[str, Any]:
    """Everything the tab shows about one table, JSON-serialisable. `error` set when the table itself failed."""
    if not config.om_enabled() and client is None:
        return {"error": "not-configured"}
    client = client or _client()
    try:
        table = client.table(fqn)
    except OMError as err:
        log.warning("om panel %s: %s", fqn, err)
        return {"error": "not-found" if err.status == 404 else "unreachable"}
    data: dict[str, Any] = {"table": summarize_table(table), "columns": mapping.columns(table),
                            "fetched_at": _naive_utc(dt.datetime.now(dt.timezone.utc))}
    for name, call in (("profile", lambda: client.profile(fqn)),
                       ("lineage", lambda: summarize_lineage(client.lineage(fqn))),
                       ("tests", lambda: summarize_tests(client.test_cases(fqn)))):
        try:
            data[name] = call()
        except OMError as err:
            log.info("om panel %s: %s unavailable (%s)", fqn, name, err)
            data[name] = None
    return data


# --- shaping OpenMetadata answers -------------------------------------------------------


def summarize_table(table: dict[str, Any]) -> dict[str, Any]:
    usage = ((table.get("usageSummary") or {}).get("weeklyStats") or {}).get("count")
    return {
        "id": table.get("id"),
        "fqn": table.get("fullyQualifiedName"),
        "name": table.get("displayName") or table.get("name"),
        "table_type": table.get("tableType") or "",
        "service_type": table.get("serviceType") or "",
        "service": mapping.service_name(table),
        "owners": [{"name": mapping.ref_name(o), "type": o.get("type", "")} for o in mapping.owners(table)],
        "domains": [mapping.ref_name(d) for d in mapping.domains(table)],
        "tier": mapping.tier(table),
        "tags": [t for t in mapping.tag_fqns(table) if not t.lower().startswith(mapping.TIER_PREFIX)],
        "followers": len(table.get("followers") or []),
        "weekly_queries": usage,
        "updated_at": mapping.updated_at(table).rstrip("Z"),
    }


def _node_id(ref: Any) -> str:
    return ref.get("id", "") if isinstance(ref, dict) else str(ref or "")


def summarize_lineage(lineage: dict[str, Any]) -> dict[str, list[dict[str, Any]]]:
    """Direct upstream and downstream entities. Edges carry ids (dicts in some releases)."""
    entity_id = _node_id(lineage.get("entity"))
    nodes = {n.get("id"): n for n in lineage.get("nodes") or []}

    def side(edges: list[dict[str, Any]], mine: str, other: str) -> list[dict[str, Any]]:
        result, seen = [], set()
        for edge in edges or []:
            if _node_id(edge.get(mine)) != entity_id:
                continue
            node_id = _node_id(edge.get(other))
            node = nodes.get(node_id)
            if node is None or node_id in seen:
                continue
            seen.add(node_id)
            result.append({"id": node_id, "type": node.get("type") or "table",
                           "name": node.get("displayName") or node.get("name") or node_id,
                           "fqn": node.get("fullyQualifiedName") or ""})
        return result

    return {"upstream": side(lineage.get("upstreamEdges"), "toEntity", "fromEntity"),
            "downstream": side(lineage.get("downstreamEdges"), "fromEntity", "toEntity")}


def _naive_utc(moment: dt.datetime) -> str:
    """CKAN's date helpers (render_datetime, time_ago_from_timestamp) read naive ISO strings as UTC."""
    return moment.astimezone(dt.timezone.utc).replace(tzinfo=None).isoformat(timespec="seconds")


def _timestamp(value: Any) -> str:
    if not isinstance(value, int | float):
        return ""
    seconds = value / 1000 if value > 10**11 else value  # ms in recent releases, s in old ones
    return _naive_utc(dt.datetime.fromtimestamp(seconds, tz=dt.timezone.utc))


def summarize_tests(cases: list[dict[str, Any]]) -> dict[str, Any]:
    counts = dict.fromkeys(STATUSES, 0)
    items = []
    for case in cases:
        result = case.get("testCaseResult") or {}
        status = result.get("testCaseStatus") or "Queued"
        counts[status] = counts.get(status, 0) + 1
        match = _COLUMN_LINK.search(case.get("entityLink") or "")
        items.append({
            "name": case.get("displayName") or case.get("name") or "",
            "test": mapping.ref_name(case.get("testDefinition")),
            "column": match.group("column") if match else "",
            "status": status,
            "at": _timestamp(result.get("timestamp")),
        })
    # Failures first; sort() is stable, so OpenMetadata's order holds within a status.
    items.sort(key=lambda i: i["status"] != "Failed")
    return {"total": len(cases), "counts": counts, "items": items[:MAX_TESTS]}


# --- per viewer ---------------------------------------------------------------------------


def _readable_datasets(om_ids: list[str]) -> dict[str, dict[str, str]]:
    """om_id -> dataset name/title, limited to datasets the current user may read."""
    if not om_ids:
        return {}
    rows = (
        model.Session.query(model.Package.name, model.Package.title, model.PackageExtra.value)
        .join(model.PackageExtra, model.PackageExtra.package_id == model.Package.id)
        .filter(model.PackageExtra.key == mapping.Ext.ID, model.PackageExtra.value.in_(om_ids),
                model.PackageExtra.state == "active", model.Package.state == "active")
    )
    result = {}
    for name, title, om_id in rows:
        if tk.h.check_access("package_show", {"id": name}):
            result[om_id] = {"name": name, "title": title}
    return result


def ui_link(entity_type: str, fqn: str) -> str:
    base = config.om_ui_url()
    return f"{base}/{entity_type}/{quote(fqn, safe='')}" if base and fqn else ""


def panel(pkg: dict[str, Any]) -> dict[str, Any] | None:
    """Template data for the tab; None when the dataset does not come from OpenMetadata."""
    fqn = extra(pkg, mapping.Ext.FQN)
    if not fqn:
        return None
    live = _cached(fqn)
    data: dict[str, Any] = {
        "fqn": fqn,
        "om_url": extra(pkg, mapping.Ext.URL) or ui_link("table", fqn),
        "error": live.get("error"),
        "updated_at": extra(pkg, mapping.Ext.UPDATED).rstrip("Z"),
        **{k: live.get(k) for k in ("table", "profile", "lineage", "tests", "fetched_at")},
    }
    profile = data.get("profile")
    if profile:
        data["profile"] = {"rows": profile.get("rowCount"), "columns": profile.get("columnCount"),
                           "at": _timestamp(profile.get("timestamp"))}
    data["columns"] = live.get("columns")
    if data["columns"] is None:
        try:
            data["columns"] = json.loads(extra(pkg, mapping.Ext.COLUMNS) or "[]")
        except ValueError:
            data["columns"] = []
    lineage = data.get("lineage")
    if lineage:
        nodes = lineage["upstream"] + lineage["downstream"]
        datasets = _readable_datasets([n["id"] for n in nodes if n["type"] == "table"])
        for node in nodes:
            node["dataset"] = datasets.get(node["id"])
            node["om_url"] = ui_link(node["type"], node["fqn"])
    return data
