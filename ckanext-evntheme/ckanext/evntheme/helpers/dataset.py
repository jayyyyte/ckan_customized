"""Dataset helpers: badges, metadata rows, KPIs, quality, related datasets, activity."""
from __future__ import annotations

from typing import Any

from markupsafe import Markup, escape

import ckan.plugins.toolkit as tk
from ckan.plugins import plugin_loaded

from ckanext.evntheme import downloads as zip_downloads
from ckanext.evntheme import formatting, public, stats
from ckanext.evntheme.helpers.common import as_float, field, truthy
from ckanext.evntheme.vocab import (
    ACTIVITY_KINDS,
    DATA_TYPES,
    DATASET_TABS,
    DEFAULT_ACTIVITY,
    FORMAT_LABELS,
    FORMAT_STYLES,
    FREQUENCIES,
    QUALITY_METRICS,
    Extra,
    Term,
)


def data_type(pkg: dict[str, Any]) -> Term | None:
    return DATA_TYPES.get(field(pkg, Extra.DATA_TYPE) or "")


def frequency(pkg: dict[str, Any]) -> Term | None:
    return FREQUENCIES.get(field(pkg, Extra.FREQUENCY) or "")


def format_badge(fmt: str | None) -> dict[str, str]:
    key = (fmt or "").strip().upper()
    return {"label": FORMAT_LABELS.get(key, key or "?"), "style": FORMAT_STYLES.get(key, "other")}


def format_badges(pkg: dict[str, Any]) -> list[dict[str, str]]:
    """One badge per distinct resource format, in resource order."""
    seen: dict[str, dict[str, str]] = {}
    for res in pkg.get("resources") or []:
        badge = format_badge(res.get("format"))
        if res.get("format") and badge["label"] not in seen:
            seen[badge["label"]] = badge
    return list(seen.values())


def downloads(pkg: dict[str, Any]) -> int | None:
    return stats.resource_downloads(pkg.get("resources") or [])


def rating(pkg: dict[str, Any]) -> dict[str, Any] | None:
    """Average rating if a rating extension fills `rating_average`/`rating_count`."""
    average = as_float(field(pkg, Extra.RATING_AVERAGE))
    count = as_float(field(pkg, Extra.RATING_COUNT))
    if average is None or not count:
        return None
    return {"average": formatting.number(average, 1), "count": formatting.number(count)}


def hero_badges(pkg: dict[str, Any]) -> list[dict[str, str]]:
    badges = []
    kind = data_type(pkg)
    if kind:
        badges.append({"label": tk._(kind.label), "style": f"kind-{kind.code}"})
    if truthy(field(pkg, Extra.GOLDEN_RECORD)):
        badges.append({"label": tk._("Golden record"), "style": "outline"})
    standard = field(pkg, Extra.METADATA_STANDARD)
    if standard:
        badges.append({"label": tk._("Follows {standard}").format(standard=standard), "style": "good"})
    return badges


def record_count(pkg: dict[str, Any]) -> float | None:
    return as_float(field(pkg, Extra.RECORD_COUNT))


def kpis(pkg: dict[str, Any]) -> list[dict[str, str]]:
    """KPI tiles under the description; tiles without data are left out."""
    tiles = []
    records = record_count(pkg)
    if records is not None:
        tiles.append({"label": tk._("Records"), "value": formatting.number(records)})
    freq = frequency(pkg)
    if freq:
        tiles.append({"label": tk._("Update frequency"), "value": tk._(freq.label).capitalize()})
    completeness = as_float(field(pkg, "quality_completeness"))
    if completeness is not None:
        tiles.append({"label": tk._("Completeness"), "value": formatting.percent(completeness)})
    source = field(pkg, Extra.SOURCE_SYSTEM)
    if source:
        tiles.append({"label": tk._("Source system"), "value": source})
    return tiles


def quality(pkg: dict[str, Any]) -> list[dict[str, Any]]:
    bars = []
    for metric in QUALITY_METRICS:
        value = as_float(field(pkg, metric.code))
        if value is not None:
            value = max(0.0, min(100.0, value))
            bars.append({"label": tk._(metric.label), "value": value, "text": formatting.percent(value),
                         "tone": metric.tone})
    return bars


def open_level(pkg: dict[str, Any]) -> int | None:
    value = as_float(field(pkg, Extra.OPEN_LEVEL))
    return int(value) if value is not None and 0 <= value <= 5 else None


def _contact(pkg: dict[str, Any]) -> str:
    name = pkg.get("maintainer") or pkg.get("author") or ""
    email = pkg.get("maintainer_email") or pkg.get("author_email") or ""
    return " · ".join(part for part in (name, email) if part)


# Extras rendered by name in `info_rows`; any other extra is listed after them.
_KNOWN_EXTRAS = {
    Extra.DATA_TYPE, Extra.FREQUENCY, Extra.SOURCE_SYSTEM, Extra.RECORD_COUNT, Extra.GOLDEN_RECORD,
    Extra.METADATA_STANDARD, Extra.SPATIAL, Extra.TEMPORAL, Extra.OPEN_LEVEL, Extra.RATING_AVERAGE,
    Extra.RATING_COUNT, *(m.code for m in QUALITY_METRICS),
}


def info_rows(pkg: dict[str, Any]) -> list[dict[str, Any]]:
    """'Dataset information' sidebar: label/value rows, empty ones skipped.

    `value` is plain text; `stars` (0-5) renders the openness rating.
    """
    org = pkg.get("organization") or {}
    groups = ", ".join(g.get("display_name") or g.get("title") or g["name"] for g in pkg.get("groups") or [])
    rows = [
        (tk._("Identifier"), pkg.get("name")),
        (tk._("Data domain"), groups),
        (tk._("Publisher"), org.get("title") or org.get("name")),
        (tk._("Contact"), _contact(pkg)),
        (tk._("License"), pkg.get("license_title")),
        (tk._("Spatial coverage"), field(pkg, Extra.SPATIAL)),
        (tk._("Temporal coverage"), field(pkg, Extra.TEMPORAL)),
        (tk._("Metadata standard"), field(pkg, Extra.METADATA_STANDARD)),
        (tk._("Version"), pkg.get("version")),
    ]
    result = [{"label": label, "value": value} for label, value in rows if value]
    level = open_level(pkg)
    if level is not None:
        result.append({"label": tk._("Openness"), "value": tk._("{n} of 5 stars").format(n=level), "stars": level})
    for extra in pkg.get("extras") or []:
        if extra.get("key") not in _KNOWN_EXTRAS and extra.get("value"):
            result.append({"label": extra["key"], "value": extra["value"]})
    return result


def _solr_quote(value: str) -> str:
    return value.replace("\\", "\\\\").replace('"', '\\"')


def related(pkg: dict[str, Any], limit: int = 3) -> list[dict[str, Any]]:
    """Datasets sharing a tag or the publisher, best matches first."""
    clauses = [f'tags:"{_solr_quote(t["name"])}"' for t in pkg.get("tags") or []]
    if pkg.get("owner_org"):
        clauses.append(f'owner_org:"{pkg["owner_org"]}"')
    if not clauses:
        return []
    result = public.action("package_search", {"q": " OR ".join(clauses), "fq": f'-id:"{pkg["id"]}"', "rows": limit})
    return result["results"]


def download_all(pkg: dict[str, Any]) -> dict[str, Any] | None:
    """Target of the hero download button: a zip when several files are uploaded, the file itself when one."""
    files = zip_downloads.local_files(pkg)
    if not files:
        return None
    if len(files) == 1:
        return {"count": 1, "url": files[0][0]["url"]}
    return {"count": len(files), "url": tk.url_for("evntheme_dataset.download_all", id=pkg["name"])}


def am_following(pkg: dict[str, Any]) -> bool | None:
    """None for anonymous users (the button then leads to the login page)."""
    if not tk.current_user.is_authenticated:
        return None
    return tk.get_action("am_following_dataset")({}, {"id": pkg["id"]})


def tabs(pkg: dict[str, Any]) -> list[dict[str, Any]]:
    current = active_tab()
    items = [t for t in DATASET_TABS if t.code != "activity" or plugin_loaded("activity")]
    return [
        {"code": t.code, "label": tk._(t.label), "active": t.code == current,
         "url": tk.url_for(f"{pkg['type']}.read", id=pkg["name"], tab=None if t.code == "overview" else t.code)}
        for t in items
    ]


def active_tab() -> str:
    tab = tk.request.args.get("tab", "overview")
    return tab if tab in {t.code for t in DATASET_TABS} else "overview"


def activities(pkg: dict[str, Any], limit: int = 6) -> list[dict[str, Any]]:
    if not plugin_loaded("activity"):
        return []
    try:
        items = tk.get_action("package_activity_list")({}, {"id": pkg["id"], "limit": limit})
    except (tk.NotAuthorized, tk.ObjectNotFound):
        return []
    result = []
    for item in items:
        kind = ACTIVITY_KINDS.get(item.get("activity_type"), DEFAULT_ACTIVITY)
        actor = tk.h.linked_user(item["user_id"], maxlength=40, avatar=0)
        text = escape(tk._(kind.label)).replace(escape("{actor}"), Markup(actor))
        result.append({"tone": kind.tone, "text": text, "timestamp": item["timestamp"]})
    return result


def resource_meta(res: dict[str, Any]) -> list[str]:
    """Size · rows · last change, for a resource row."""
    parts = []
    if res.get("size"):
        parts.append(tk.h.localised_filesize(int(res["size"])))
    rows = as_float(res.get("rows") or res.get("record_count"))
    if rows is not None:
        parts.append(tk._("{n} rows").format(n=formatting.number(rows)))
    changed = res.get("last_modified") or res.get("metadata_modified") or res.get("created")
    if changed:
        parts.append(tk._("updated {ago}").format(ago=tk.h.time_ago_from_timestamp(changed)))
    return parts
