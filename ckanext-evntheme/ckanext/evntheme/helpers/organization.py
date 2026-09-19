"""Organisation helpers: type, avatar, freshness, directory and the featured publisher."""
from __future__ import annotations

import datetime as dt
from typing import Any

import ckan.plugins.toolkit as tk

from ckanext.evntheme import config, formatting, public, stats
from ckanext.evntheme.cache import ttl_cache
from ckanext.evntheme.helpers import site
from ckanext.evntheme.helpers.common import field, initials, tone_for
from ckanext.evntheme.vocab import ORG_FILTERS, ORG_TYPES, OrgExtra, Term

# Freshness thresholds: green up to FRESH, orange up to AGING, red after.
FRESH = dt.timedelta(hours=12)
AGING = dt.timedelta(days=2)


def org_type(org: dict[str, Any]) -> Term:
    return ORG_TYPES.get(field(org, OrgExtra.TYPE) or "", ORG_TYPES["other"])


def _with_extras(org: dict[str, Any]) -> dict[str, Any]:
    """The organisation embedded in a dataset dict has no extras: take the full one from the cached list."""
    if "extras" in org:
        return org
    return next((o for o in _all_orgs() if o["id"] == org.get("id")), org)


def org_avatar(org: dict[str, Any]) -> dict[str, str]:
    """Abbreviation tile: `abbreviation` extra or initials, colour stable per organisation."""
    title = org.get("display_name") or org.get("title") or org.get("name") or ""
    return {
        "abbr": field(_with_extras(org), OrgExtra.ABBREVIATION) or initials(title),
        "tone": tone_for(org.get("name") or title),
        "title": title,
    }


def freshness(last_modified: dt.datetime | None, now: dt.datetime | None = None) -> dict[str, str] | None:
    """{'label': 'tươi 5 phút', 'tone': 'fresh|aging|stale'} from the newest update."""
    if last_modified is None:
        return None
    delta = max((now or dt.datetime.now(dt.timezone.utc)) - last_modified, dt.timedelta(minutes=1))
    tone = "fresh" if delta <= FRESH else "aging" if delta <= AGING else "stale"
    return {"label": tk._("fresh {age}").format(age=formatting.duration(delta)), "tone": tone}


def org_freshness(org: dict[str, Any]) -> dict[str, str] | None:
    return freshness(stats.portal_stats().org(org["name"]).last_modified)


def org_stats(org: dict[str, Any]) -> dict[str, Any]:
    data = stats.portal_stats().org(org["name"])
    return {
        "datasets": data.datasets,
        "apis": data.api_datasets,
        "on_time": data.on_time.rate,
        "freshness": freshness(data.last_modified),
    }


def org_domain(org: dict[str, Any]) -> str:
    """Main data domain: `domain` extra, shown with the group title when it names a group."""
    domain = field(org, OrgExtra.DOMAIN)
    if not domain:
        return ""
    titles = {g["name"]: g.get("display_name") or g["name"] for g in site.all_groups()}
    return titles.get(domain, domain)


@ttl_cache(lambda: config.get("stats_cache_seconds"))
def _all_orgs() -> list[dict[str, Any]]:
    """Every organisation with extras; organization_list caps all_fields pages, so page through it."""
    page_size = 25
    orgs: list[dict[str, Any]] = []
    while True:
        batch = public.action(
            "organization_list",
            {"all_fields": True, "include_extras": True, "sort": "package_count desc",
             "limit": page_size, "offset": len(orgs)},
        )
        orgs.extend(batch)
        if len(batch) < page_size:
            return orgs


def _matches(org: dict[str, Any], query: str) -> bool:
    text = " ".join(str(org.get(k) or "") for k in ("name", "title", "description"))
    abbr = field(org, OrgExtra.ABBREVIATION) or ""
    return query in f"{text} {abbr}".casefold()


def _filter_code(org: dict[str, Any]) -> str:
    code = org_type(org).code
    return code if code in {f.code for f in ORG_FILTERS} else "other"


def org_directory() -> dict[str, Any]:
    """Organisations for /organization, filtered by ?type= and ?q=, with the filter tabs."""
    query = (tk.request.args.get("q") or "").strip()
    selected = tk.request.args.get("type") or "all"
    orgs = [o for o in _all_orgs() if not query or _matches(o, query.casefold())]
    tabs = []
    for tab in ORG_FILTERS:
        members = orgs if tab.code == "all" else [o for o in orgs if _filter_code(o) == tab.code]
        tabs.append({
            "code": tab.code,
            "label": tk._(tab.label),
            "count": len(members),
            "active": tab.code == selected,
            "url": tk.url_for(f"{tk.h.default_group_type('organization')}.index",
                              type=None if tab.code == "all" else tab.code, q=query or None),
        })
    if selected != "all":
        orgs = [o for o in orgs if _filter_code(o) == selected]
    return {"organizations": orgs, "tabs": tabs, "query": query, "type": selected}


@ttl_cache(lambda: config.get("stats_cache_seconds"))
def _featured_org_name() -> str | None:
    result = public.action(
        "package_search",
        {"fq": "metadata_modified:[NOW-30DAYS TO NOW]", "rows": 0, "facet.field": ["organization"], "facet.limit": 50},
    )
    items = result["search_facets"].get("organization", {}).get("items", [])
    return max(items, key=lambda i: i["count"])["name"] if items else None


def featured_org() -> dict[str, Any] | None:
    """'Đơn vị nổi bật tháng này': the publisher with the most datasets updated in the last 30 days."""
    name = _featured_org_name()
    if not name:
        return None
    org = next((o for o in _all_orgs() if o["name"] == name), None)
    if org is None:
        return None
    return {"org": org, "stats": org_stats(org), "downloads": stats.organization_downloads(org["id"])}
