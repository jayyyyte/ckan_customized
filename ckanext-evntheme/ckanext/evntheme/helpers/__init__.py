"""Template helpers, exposed to Jinja as ``h.evn_<name>``.

To add a helper: write the function in the module that fits, then list it in
``_HELPERS``. Keep logic here and markup in templates.
"""
from __future__ import annotations

import datetime as dt
from collections.abc import Callable
from typing import Any

import ckan.plugins.toolkit as tk

from ckanext.evntheme import config, formatting
from ckanext.evntheme.helpers import dataset, datastore, organization, search, site, trino


def _config(name: str) -> Any:
    return config.get(name)


def _time_ago(timestamp: Any) -> str:
    return tk.h.time_ago_from_timestamp(timestamp) if timestamp else ""


def _year() -> int:
    return dt.date.today().year


_HELPERS: dict[str, Callable[..., Any]] = {
    # formatting
    "number": formatting.number,
    "percent": formatting.percent,
    "date": formatting.date,
    "time_ago": _time_ago,
    "year": _year,
    "config": _config,
    "logo": config.logo,
    # site / home
    "counts": site.counts,
    "nav_items": site.nav_items,
    "links": site.links,
    "hot_searches": site.hot_searches,
    "api_metrics": site.api_metrics,
    "domains": site.domains,
    "top_organizations": site.top_organizations,
    "home_sort_options": site.home_sort_options,
    "recent_datasets": site.recent_datasets,
    "mds_summary": site.mds_summary,
    "mds_status": site.mds_status,
    # datasets
    "data_type": dataset.data_type,
    "frequency": dataset.frequency,
    "format_badge": dataset.format_badge,
    "format_badges": dataset.format_badges,
    "downloads": dataset.downloads,
    "rating": dataset.rating,
    "hero_badges": dataset.hero_badges,
    "kpis": dataset.kpis,
    "quality": dataset.quality,
    "info_rows": dataset.info_rows,
    "related": dataset.related,
    "download_all": dataset.download_all,
    "am_following": dataset.am_following,
    "tabs": dataset.tabs,
    "active_tab": dataset.active_tab,
    "activities": dataset.activities,
    "resource_meta": dataset.resource_meta,
    # data preview / API
    "datastore_resources": datastore.datastore_resources,
    "map_resources": datastore.map_resources,
    "preview": datastore.preview,
    "api_console": datastore.api_console,
    # search
    "sidebar_facets": search.sidebar_facets,
    "facet_items": search.facet_items,
    "filter_chips": search.filter_chips,
    "sort_options": search.sort_options,
    "hidden_params": search.hidden_params,
    "result_range": search.result_range,
    # organizations (names from the design brief)
    "org_type": organization.org_type,
    "org_avatar": organization.org_avatar,
    "org_freshness": organization.org_freshness,
    "org_stats": organization.org_stats,
    "org_domain": organization.org_domain,
    "org_directory": organization.org_directory,
    "featured_org": organization.featured_org,
    "portal_on_time": site.portal_on_time,
    # lakehouse
    "trino_connection": trino.trino_connection,
}


def get_helpers() -> dict[str, Callable[..., Any]]:
    return {f"evn_{name}": fn for name, fn in _HELPERS.items()}
