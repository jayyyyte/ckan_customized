"""Site-wide helpers: header navigation, counters, links and the home page sections."""
from __future__ import annotations

import logging
from typing import Any

import requests

import ckan.plugins.toolkit as tk

from ckanext.evntheme import config, formatting, public, stats
from ckanext.evntheme.cache import ttl_cache
from ckanext.evntheme.helpers.common import field
from ckanext.evntheme.mds import service as mds
from ckanext.evntheme.vocab import (
    MDS_CATALOG_STATUSES,
    MDS_CODE_STATUSES,
    MDS_CONSUMER_STATUSES,
    TONES,
    GroupExtra,
    Term,
)

log = logging.getLogger(__name__)


def counts() -> dict[str, int]:
    """Public counters shown in the header badges and the home hero."""
    portal = stats.portal_stats()
    return {
        "datasets": portal.datasets,
        "organizations": stats.organization_count(),
        "apis": portal.api_datasets,
        "catalogs": mds.summary().catalogs,
    }


def portal_on_time() -> float | None:
    """Share (0-100) of scheduled public datasets updated on time, None if none has a schedule."""
    return stats.portal_stats().on_time.rate


def _is_dataset_blueprint(blueprint: str, dataset_type: str) -> bool:
    return blueprint == dataset_type or blueprint.startswith(dataset_type + "_") or blueprint == "evntheme_dataset"


def nav_items() -> list[dict[str, Any]]:
    """Main navigation pills. `count` is None for items without a badge."""
    blueprint, view = tk.get_endpoint()
    blueprint = blueprint or ""
    dataset_type = tk.h.default_package_type()
    org_type = tk.h.default_group_type("organization")
    total = counts()
    return [
        {
            "label": tk._("Home"),
            "url": tk.url_for("home.index"),
            "count": None,
            "active": blueprint == "home" and view == "index",
        },
        {
            "label": tk._("Datasets"),
            "url": tk.url_for(f"{dataset_type}.search"),
            "count": total["datasets"],
            "active": _is_dataset_blueprint(blueprint, dataset_type),
        },
        {
            "label": tk._("Organizations"),
            "url": tk.url_for(f"{org_type}.index"),
            "count": total["organizations"],
            "active": blueprint == org_type,
        },
        {
            "label": tk._("Code lists"),
            "url": tk.url_for("evntheme_mds.index"),
            "count": total["catalogs"],
            "active": blueprint == "evntheme_mds",
        },
    ]


def links() -> dict[str, str]:
    """Identity texts and outbound links, all from config."""
    names = (
        "owner_name", "platform_name", "operator", "contact_email", "contact_address",
        "guide_url", "api_docs_url", "terms_url",
    )
    values = {name: config.get(name) for name in names}
    values["support_url"] = config.support_url()
    return values


def hot_searches() -> list[str]:
    return config.get_list("hot_searches", ";")


@ttl_cache(lambda: 60)
def _fetch_api_metrics(url: str) -> dict[str, Any]:
    try:
        response = requests.get(url, timeout=2)
        response.raise_for_status()
        return response.json()
    except (requests.RequestException, ValueError):
        log.warning("evntheme: cannot read API metrics from %s", url, exc_info=True)
        return {}


def api_metrics() -> list[dict[str, str]]:
    """Rows of the developer card. Only metrics the monitoring endpoint provides are shown."""
    url = config.get("api_metrics_url")
    data = _fetch_api_metrics(url) if url else {}
    rows = []
    if data.get("uptime_30d") is not None:
        rows.append({"label": tk._("Uptime (30 days)"), "value": formatting.percent(data["uptime_30d"], 2),
                     "tone": "good"})
    if data.get("calls_today") is not None:
        rows.append({"label": tk._("Calls today"), "value": formatting.number(data["calls_today"])})
    if data.get("latency_ms") is not None:
        rows.append({"label": tk._("Response time"), "value": f"{formatting.number(data['latency_ms'])} ms"})
    return rows


@ttl_cache(lambda: config.get("stats_cache_seconds"))
def _groups(names: tuple[str, ...]) -> list[dict[str, Any]]:
    data_dict: dict[str, Any] = {"all_fields": True, "include_extras": True, "sort": "title asc"}
    if names:
        data_dict["groups"] = list(names)
    groups = public.action("group_list", data_dict)
    if names:
        order = {name: i for i, name in enumerate(names)}
        groups.sort(key=lambda g: order.get(g["name"], len(order)))
    return groups


def all_groups() -> list[dict[str, Any]]:
    return _groups(())


def domains() -> list[dict[str, Any]]:
    """Data domains (CKAN groups) with their public dataset count and colour."""
    dataset_type = tk.h.default_package_type()
    result = []
    for i, group in enumerate(_groups(tuple(config.get_list("domain_groups")))):
        tone = field(group, GroupExtra.TONE)
        result.append({
            "name": group["name"],
            "title": group.get("display_name") or group["name"],
            "description": tk.h.markdown_extract(group.get("description") or "", extract_length=80),
            "count": group.get("package_count", 0),
            "tone": tone if tone in TONES else TONES[i % len(TONES)],
            "url": tk.url_for(f"{dataset_type}.search", groups=group["name"]),
        })
    return result


def top_organizations(limit: int = 5) -> list[dict[str, Any]]:
    return public.action(
        "organization_list",
        {"all_fields": True, "include_extras": True, "sort": "package_count desc", "limit": limit},
    )


HOME_SORTS = {"recent": "metadata_modified desc", "popular": "views_recent desc"}


def home_sort_options() -> list[dict[str, Any]]:
    """'Sort by' choices of the home list. 'Most viewed' needs the tracking plugin."""
    options = [{"value": "recent", "label": tk._("Newest")}]
    if stats.tracking_enabled():
        options.append({"value": "popular", "label": tk._("Most viewed")})
    selected = tk.request.args.get("sort")
    for option in options:
        option["selected"] = option["value"] == selected
    return options


def recent_datasets(sort: str | None = None) -> list[dict[str, Any]]:
    key = sort if sort in HOME_SORTS and (sort != "popular" or stats.tracking_enabled()) else "recent"
    result = public.action("package_search", {"rows": config.get("home_datasets"), "sort": HOME_SORTS[key]})
    return result["results"]


def mds_summary() -> mds.Summary:
    return mds.summary()


_MDS_STATUSES = {"catalog": MDS_CATALOG_STATUSES, "code": MDS_CODE_STATUSES, "consumer": MDS_CONSUMER_STATUSES}


def mds_status(code: str, kind: str = "code") -> Term:
    """Status term of a code list ('catalog'), a code ('code') or a consuming system ('consumer')."""
    return _MDS_STATUSES[kind].get(code) or Term(code, code)
