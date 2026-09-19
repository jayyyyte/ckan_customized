"""Config options of the theme (``ckanext.evntheme.*``) and typed accessors.

Everything a deployment may change without rebuilding the image lives here: owner
texts, outbound links, which groups are data domains, where API metrics come from...
Inspect them with ``ckan config declaration evntheme``.

On Kubernetes each key can be set as an env var, e.g.
``CKANEXT__EVNTHEME__CONTACT_EMAIL`` (ckanext-envvars convention).
"""
from __future__ import annotations

from typing import Any

import ckan.plugins.toolkit as tk
from ckan.common import config_declaration

PREFIX = "ckanext.evntheme."

# key -> (default, description). Types come from the default value.
OPTIONS: dict[str, tuple[Any, str]] = {
    # Identity
    "owner_name": ("Tập đoàn Điện lực Việt Nam", "Owner shown in the utility bar and footer."),
    "platform_name": ("Nền tảng dữ liệu dùng chung", "Second half of the utility bar text."),
    "operator": ("EVNICT", "Unit operating the portal (footer)."),
    "contact_email": ("data@evn.com.vn", "Contact e-mail (footer, default support link)."),
    "contact_address": ("11 Cửa Bắc, Ba Đình, Hà Nội", "Postal address in the footer. Empty hides it."),
    # Links
    "guide_url": ("/about", "'User guide' link in the utility bar."),
    "api_docs_url": ("https://docs.ckan.org/en/2.11/api/", "API documentation link."),
    "support_url": ("", "'Support' link. Empty: mailto: contact_email."),
    "terms_url": ("", "'Terms of use' link in the footer. Empty hides it."),
    # Home page
    "hot_searches": (
        "danh mục vật tư; tổn thất lưới điện; sản lượng thương phẩm; trạm biến áp 110kV",
        "Suggested searches under the hero search box, separated by ';'.",
    ),
    "domain_groups": ("", "Group names shown as data domains, in order. Empty: every group."),
    "home_datasets": (4, "Number of datasets in 'Recently updated'."),
    "api_metrics_url": (
        "",
        "JSON endpoint with API health for the developer card: "
        '{"uptime_30d": 99.97, "calls_today": 412880, "latency_ms": 86}. Empty hides the rows.',
    ),
    "api_rate_limit": ("", "Rate limit text shown on the 'Try the API' tab. Empty hides it."),
    # Search
    "sidebar_facets": (
        "organization res_format data_type tags license_id",
        "Facets shown in the search sidebar, in order (all facets are still queried).",
    ),
    "facet_items": (5, "Facet values shown before the 'Show N more' link."),
    # Dataset page
    "preview_rows": (10, "Rows per page in the data preview table."),
    "map_tile_url": (
        "",
        "Leaflet tile URL for the map preview, e.g. https://tile.openstreetmap.org/{z}/{x}/{y}.png. "
        "Empty draws the shapes without a basemap (works offline).",
    ),
    "zip_max_mb": (500, "Largest total size served by 'Download all' as one zip."),
    # Caching
    "stats_cache_seconds": (300, "How long portal-wide counters are cached. 0 disables the cache."),
}

# Core options CKAN reads but does not declare. CKAN 2.11 checks `ckan.upload.admin.*` when a
# sysadmin uploads the site logo on /ckan-admin/config, and without a value it refuses every
# file ("No uploads allowed for object type admin", docs/gotchas.md 6ai). Declared only while
# core leaves them out, so a CKAN upgrade that declares them wins.
CORE_GAPS: dict[str, tuple[list[str], str]] = {
    "ckan.upload.admin.types": (["image"], "File types a sysadmin may upload as the site logo."),
    "ckan.upload.admin.mimetypes": (
        ["image/png", "image/jpeg", "image/gif", "image/webp"],
        "MIME types a sysadmin may upload as the site logo. SVG is left out because an SVG opened "
        "directly runs its scripts on the portal's origin; serve an SVG logo from the theme instead.",
    ),
}

# The logo is CKAN's own `ckan.site_logo`: set in ckan.ini / env var, or uploaded on
# /ckan-admin/config (stored in the database, overrides ckan.ini). Any image format works.
SITE_LOGO = "ckan.site_logo"
THEME_LOGO = "/evntheme/public/evntheme/images/evn-logo.jpg"


def declare(declaration: Any, key: Any) -> None:
    """IConfigDeclaration: register every option with its type and description."""
    group = key.ckanext.evntheme
    for name, (default, description) in OPTIONS.items():
        option_key = getattr(group, name)
        if isinstance(default, bool):
            option = declaration.declare_bool(option_key, default)
        elif isinstance(default, int):
            option = declaration.declare_int(option_key, default)
        else:
            option = declaration.declare(option_key, default)
        option.set_description(description)
    for name, (default, description) in CORE_GAPS.items():
        if name not in declaration:
            declaration.declare_list(name, default).set_description(description)


def get(name: str) -> Any:
    if name not in OPTIONS:
        raise KeyError(f"Unknown evntheme option: {name}")
    return tk.config.get(PREFIX + name)


def get_list(name: str, sep: str | None = None) -> list[str]:
    """Split a string option on `sep` (whitespace by default), dropping empty items."""
    value = get(name) or ""
    return [item.strip() for item in value.split(sep) if item.strip()]


def support_url() -> str:
    return get("support_url") or (f"mailto:{get('contact_email')}" if get("contact_email") else "")


def pick_logo(site_logo: str | None, ckan_default: str | None) -> str:
    """The configured logo, or the theme's while `ckan.site_logo` still holds CKAN's default.

    An empty value means "no logo", as in core: the header then shows the title only.
    """
    if site_logo is None or site_logo == ckan_default:
        return THEME_LOGO
    return site_logo


def logo() -> str:
    option = config_declaration.get(SITE_LOGO)
    return pick_logo(tk.config.get(SITE_LOGO), option.default if option else None)
