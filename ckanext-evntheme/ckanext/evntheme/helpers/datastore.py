"""Data preview and 'Try the API' helpers.

Both read from the DataStore when a resource has been loaded into it
(`datastore_active`). Without the datastore plugin they degrade: the preview
shows an empty state and the API console demonstrates `package_show` instead.
"""
from __future__ import annotations

import json
import logging
import math
from typing import Any

import ckan.plugins.toolkit as tk
from ckan.plugins import plugin_loaded

from ckanext.evntheme import config
from ckanext.evntheme.helpers.common import truthy
from ckanext.evntheme.vocab import MAP_FORMATS

log = logging.getLogger(__name__)

API_SAMPLE_ROWS = 5


def datastore_enabled() -> bool:
    return plugin_loaded("datastore")


def datastore_resources(pkg: dict[str, Any]) -> list[dict[str, Any]]:
    if not datastore_enabled():
        return []
    return [r for r in pkg.get("resources") or [] if truthy(r.get("datastore_active"))]


def map_resources(pkg: dict[str, Any]) -> list[dict[str, Any]]:
    return [r for r in pkg.get("resources") or [] if (r.get("format") or "").upper() in MAP_FORMATS]


def _search(resource_id: str, limit: int, offset: int = 0) -> dict[str, Any] | None:
    try:
        return tk.get_action("datastore_search")(
            {}, {"resource_id": resource_id, "limit": limit, "offset": offset, "include_total": True}
        )
    except (tk.ObjectNotFound, tk.NotAuthorized, tk.ValidationError):
        return None
    except Exception:  # DataStore DB unreachable: show the empty state, keep the page up
        log.exception("evntheme: datastore_search failed for %s", resource_id)
        return None


def selected_resource(pkg: dict[str, Any]) -> dict[str, Any] | None:
    """Resource chosen with ?resource_id=, else the first DataStore resource."""
    resources = datastore_resources(pkg)
    wanted = tk.request.args.get("resource_id")
    return next((r for r in resources if r["id"] == wanted), resources[0] if resources else None)


def preview(pkg: dict[str, Any]) -> dict[str, Any] | None:
    """One page of the selected DataStore resource for the preview table."""
    resource = selected_resource(pkg)
    if resource is None:
        return None
    per_page = config.get("preview_rows")
    try:
        page = max(1, int(tk.request.args.get("page", 1)))
    except ValueError:
        page = 1
    result = _search(resource["id"], per_page, (page - 1) * per_page)
    if result is None:
        return {"resource": resource, "error": True}
    fields = [f for f in result.get("fields", []) if f["id"] != "_id"]
    total = result.get("total") or 0
    return {
        "resource": resource,
        "fields": fields,
        "records": result.get("records", []),
        "total": total,
        "page": page,
        "pages": max(1, math.ceil(total / per_page)),
        "numeric_fields": [f["id"] for f in fields if f.get("type") in {"int", "int4", "int8", "numeric", "float8"}],
        "error": False,
    }


def api_console(pkg: dict[str, Any]) -> dict[str, Any]:
    """Endpoint shown in the console and the server-side response it returns."""
    resource = selected_resource(pkg)
    if resource is not None:
        endpoint = tk.url_for("api.action", ver=3, logic_function="datastore_search",
                              resource_id=resource["id"], limit=API_SAMPLE_ROWS)
        result = _search(resource["id"], API_SAMPLE_ROWS)
        response = {"success": result is not None, "result": result}
    else:
        endpoint = tk.url_for("api.action", ver=3, logic_function="package_show", id=pkg["name"])
        response = {"success": True, "result": pkg}
    return {
        "endpoint": endpoint,
        "response": json.dumps(response, ensure_ascii=False, indent=2, default=str),
        "datastore": resource is not None,
        "csv_url": tk.url_for("datastore.dump", resource_id=resource["id"], format="csv") if resource else None,
    }
