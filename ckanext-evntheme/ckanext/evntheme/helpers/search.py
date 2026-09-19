"""Search page helpers: facet configuration, facet items, filter chips, sort options."""
from __future__ import annotations

from collections import OrderedDict
from collections.abc import Callable
from typing import Any

import ckan.plugins.toolkit as tk

from ckanext.evntheme import config, stats
from ckanext.evntheme.helpers.dataset import format_badge
from ckanext.evntheme.vocab import CHIP_PREFIXES, DATA_TYPES, FACETS, N_

SORT_OPTIONS = (
    ("score desc, metadata_modified desc", N_("Relevance")),
    ("metadata_modified desc", N_("Last modified")),
    ("title_string asc", N_("Name A-Z")),
    ("title_string desc", N_("Name Z-A")),
)
POPULAR_SORT = ("views_recent desc", N_("Most viewed"))


def dataset_facets(facets: OrderedDict[str, str]) -> OrderedDict[str, str]:
    """IFacets: the theme's facets first, in order, then anything other plugins added."""
    ordered: OrderedDict[str, str] = OrderedDict((f.code, tk._(f.label)) for f in FACETS)
    for name, title in facets.items():
        ordered.setdefault(name, title)
    return ordered


def sidebar_facets(facet_titles: dict[str, str], skip: tuple[str, ...] = ()) -> list[tuple[str, str]]:
    """(name, title) of the facets shown in the sidebar, per `ckanext.evntheme.sidebar_facets`."""
    wanted = [n for n in config.get_list("sidebar_facets") if n in facet_titles and n not in skip]
    return [(name, facet_titles[name]) for name in wanted]


def facet_value_label(field: str, value: str, display_name: str | None = None) -> str:
    if field == "data_type" and value in DATA_TYPES:
        return tk._(DATA_TYPES[value].label)
    if field == "res_format":
        return format_badge(value)["label"]
    return display_name or value


def facet_items(name: str, search_facets: dict[str, Any], extras: dict[str, Any] | None = None,
                alternative_url: str | None = None) -> dict[str, Any]:
    """Visible items of one facet (selected ones first), plus the show more/less link."""
    all_items = tk.h.get_facet_items_dict(name, search_facets, limit=0)
    limit_param = f"_{name}_limit"
    expanded = tk.request.args.get(limit_param) == "0"
    visible_limit = config.get("facet_items")

    active = [i for i in all_items if i["active"]]
    others = [i for i in all_items if not i["active"]]
    visible = active + (others if expanded else others[: max(0, visible_limit - len(active))])

    # "values", not "items": in Jinja `data.items` would resolve to dict.items().
    values = []
    for item in visible:
        if item["active"]:
            href = tk.h.remove_url_param(name, item["name"], extras=extras, alternative_url=alternative_url)
        else:
            href = tk.h.add_url_param(new_params={name: item["name"]}, extras=extras, alternative_url=alternative_url)
        values.append({
            "value": item["name"],
            "label": facet_value_label(name, item["name"], item.get("display_name")),
            "count": item["count"],
            "active": item["active"],
            "href": href,
        })

    hidden = len(all_items) - len(visible)
    toggle = None
    if hidden > 0:
        toggle = {"more": hidden, "href": tk.h.remove_url_param(
            limit_param, replace="0", extras=extras, alternative_url=alternative_url)}
    elif expanded and len(all_items) > visible_limit:
        toggle = {"more": 0, "href": tk.h.remove_url_param(limit_param, extras=extras, alternative_url=alternative_url)}
    return {"values": values, "toggle": toggle}


def filter_chips(fields_grouped: dict[str, list[str]], search_facets: dict[str, Any],
                 remove_field: Callable[..., str]) -> list[dict[str, str]]:
    """'Đang lọc:' chips, one per active filter, each with the URL that removes it."""
    chips = []
    for field, values in (fields_grouped or {}).items():
        names = {i["name"]: i.get("display_name") for i in (search_facets or {}).get(field, {}).get("items", [])}
        prefix = CHIP_PREFIXES.get(field)
        for value in values:
            label = facet_value_label(field, value, names.get(value))
            chips.append({
                "label": f"{tk._(prefix)}: {label}" if prefix else label,
                "remove_url": remove_field(field, value),
            })
    return chips


def sort_options(selected: str | None) -> list[dict[str, Any]]:
    """Sort choices; 'Most viewed' only when the tracking plugin indexes views (as its own template does)."""
    options = list(SORT_OPTIONS)
    if stats.tracking_enabled():
        options.append(POPULAR_SORT)
    return [{"value": value, "label": tk._(label), "selected": value == selected} for value, label in options]


def hidden_params(*exclude: str) -> list[tuple[str, str]]:
    """Current query parameters to carry as hidden inputs in a search form."""
    skip = set(exclude) | {"page"}
    return [(k, v) for k, v in tk.request.args.items(multi=True) if k not in skip and v]


def result_range(page: Any) -> dict[str, int]:
    """First/last item numbers of a CKAN Page (1-based) and the total."""
    if not page or not page.item_count:
        return {"first": 0, "last": 0, "total": 0}
    return {"first": page.first_item, "last": page.last_item, "total": page.item_count}
