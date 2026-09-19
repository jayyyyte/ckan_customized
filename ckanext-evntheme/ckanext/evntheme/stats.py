"""Portal-wide statistics, computed from one scan of the public search index.

A single paged ``package_search`` with a narrow field list (``fl``) feeds every
counter the theme shows: dataset and API counts, on-time publication rate and
per-organisation freshness. The result is cached (``stats_cache_seconds``) because
it runs on every page (header badges).

Only public datasets are counted, so the cache can be shared between users.
"""
from __future__ import annotations

import datetime as dt
import logging
from collections.abc import Iterable, Iterator
from dataclasses import dataclass, field
from typing import Any

from ckan.plugins import plugin_loaded

from ckanext.evntheme import config, formatting, public
from ckanext.evntheme.cache import ttl_cache
from ckanext.evntheme.vocab import API_FORMATS, FREQUENCIES, Extra

log = logging.getLogger(__name__)

# Solr fields requested with `fl`. Notes from the CKAN 2.11 schema:
# * `name`, not `id`: the tracking plugin runs a DB lookup for every result that has an id;
# * `organization` (the org *name*): `owner_org` is indexed but not stored;
# * extras are requested as `extras_<key>` but come back without the prefix.
_FIELDS = [
    "name",
    "organization",
    "metadata_modified",
    "extras_" + Extra.FREQUENCY,
    "res_format",
    "res_extras_datastore_active",
]


@dataclass
class OnTime:
    """Datasets with a publishing schedule, and how many were updated within it."""

    scheduled: int = 0
    on_time: int = 0

    def add(self, frequency: str | None, modified: Any, now: dt.datetime) -> None:
        term = FREQUENCIES.get(frequency or "")
        max_age = getattr(term, "max_age_days", None)
        age = formatting.age(modified, now)
        if max_age is None or age is None:
            return
        self.scheduled += 1
        if age <= dt.timedelta(days=max_age):
            self.on_time += 1

    @property
    def rate(self) -> float | None:
        """Percentage 0-100, or None when no dataset declares a schedule."""
        return 100.0 * self.on_time / self.scheduled if self.scheduled else None


@dataclass
class OrgStats:
    datasets: int = 0
    api_datasets: int = 0
    last_modified: dt.datetime | None = None
    on_time: OnTime = field(default_factory=OnTime)


@dataclass
class PortalStats:
    datasets: int = 0
    api_datasets: int = 0
    on_time: OnTime = field(default_factory=OnTime)
    by_org: dict[str, OrgStats] = field(default_factory=dict)  # keyed by organisation name

    def org(self, org_name: str) -> OrgStats:
        return self.by_org.get(org_name) or OrgStats()


def is_api_dataset(formats: Iterable[str], datastore_flags: Iterable[Any]) -> bool:
    if any((f or "").upper() in API_FORMATS for f in formats):
        return True
    return any(str(flag).lower() == "true" for flag in datastore_flags)


def _as_list(value: Any) -> list[Any]:
    if value is None:
        return []
    return value if isinstance(value, list) else [value]


def _scan(page_size: int = 1000) -> Iterator[dict[str, Any]]:
    start = 0
    while True:
        result = public.action(
            "package_search",
            {"q": "*:*", "fl": _FIELDS, "rows": page_size, "start": start, "sort": "metadata_modified desc"},
        )
        yield from result["results"]
        start += page_size
        if start >= result["count"] or not result["results"]:
            return


def compute(rows: Iterable[dict[str, Any]], now: dt.datetime | None = None) -> PortalStats:
    """Aggregate search rows (see `_FIELDS`). Pure function, unit-tested."""
    now = now or dt.datetime.now(dt.timezone.utc)
    stats = PortalStats()
    for row in rows:
        api = is_api_dataset(_as_list(row.get("res_format")), _as_list(row.get("res_extras_datastore_active")))
        frequency = row.get(Extra.FREQUENCY) or row.get("extras_" + Extra.FREQUENCY)
        modified = row.get("metadata_modified")

        stats.datasets += 1
        stats.api_datasets += int(api)
        stats.on_time.add(frequency, modified, now)

        org_name = row.get("organization")
        if not org_name:
            continue
        org = stats.by_org.setdefault(org_name, OrgStats())
        org.datasets += 1
        org.api_datasets += int(api)
        org.on_time.add(frequency, modified, now)
        parsed = formatting.parse_datetime(modified)
        if parsed and (org.last_modified is None or parsed > org.last_modified):
            org.last_modified = parsed
    return stats


@ttl_cache(lambda: config.get("stats_cache_seconds"))
def portal_stats() -> PortalStats:
    try:
        return compute(_scan())
    except Exception:  # search down: degrade to empty counters rather than break every page
        log.exception("evntheme: could not compute portal statistics")
        return PortalStats()


@ttl_cache(lambda: config.get("stats_cache_seconds"))
def organization_count() -> int:
    return len(public.action("organization_list", {}))


def tracking_enabled() -> bool:
    return plugin_loaded("tracking")


def resource_downloads(resources: Iterable[dict[str, Any]]) -> int | None:
    """Sum of tracked clicks on the resources' download links (tracking plugin), or None if not tracked."""
    if not tracking_enabled():
        return None
    return sum((r.get("tracking_summary") or {}).get("total", 0) for r in resources)


@ttl_cache(lambda: config.get("stats_cache_seconds"))
def organization_downloads(org_id: str) -> int | None:
    """Total downloads of an organisation's public datasets (tracking plugin), or None if not tracked."""
    if not tracking_enabled():
        return None
    total, start = 0, 0
    while True:
        result = public.action("package_search", {"fq": f'owner_org:"{org_id}"', "rows": 1000, "start": start})
        for pkg in result["results"]:
            total += resource_downloads(pkg.get("resources", [])) or 0
        start += 1000
        if start >= result["count"]:
            return total
