"""Template helpers, registered in plugin.py with the `lakehouse_theme_` prefix."""
from __future__ import annotations

from typing import Any
from urllib.parse import parse_qsl, urlsplit

import ckan.plugins.toolkit as tk

_JDBC_TRINO = "jdbc:trino://"
_LINK_KEYS = ("organization_name", "contact_email", "openmetadata_url", "trino_docs_url")


def trino_connection(url: str | None) -> dict[str, Any] | None:
    """Split `jdbc:trino://host[:port][/catalog[/schema]][?SSL=true]` for the "How to connect" box.

    Returns None when the URL is not a usable Trino JDBC URL.
    """
    if not url or not url.lower().startswith(_JDBC_TRINO):
        return None
    parts = urlsplit(url[len("jdbc:"):])
    try:
        port = parts.port
    except ValueError:
        return None
    if not parts.hostname:
        return None
    ssl = dict(parse_qsl(parts.query)).get("SSL", "").lower() == "true"
    port = port or (443 if ssl else 80)
    path = [p for p in parts.path.split("/") if p]
    return {
        "jdbc_url": url,
        "host": parts.hostname,
        "port": port,
        "ssl": ssl,
        "catalog": path[0] if path else None,
        "schema": path[1] if len(path) > 1 else None,
        "server": f"{'https' if ssl else 'http'}://{parts.hostname}:{port}",
    }


def links() -> dict[str, str]:
    """Owner info and external links for the footer (`ckanext.lakehouse_theme.*`)."""
    return {k: tk.config.get(f"ckanext.lakehouse_theme.{k}") for k in _LINK_KEYS}


def recent_datasets(count: int = 5) -> list[dict[str, Any]]:
    """Newest datasets the current user can see, for the home page.

    The CKAN 2.11 classic templates have no "Recent Datasets" section (2.12 Midnight Blue did).
    """
    result = tk.get_action("package_search")({}, {"rows": count, "sort": "metadata_modified desc"})
    return result["results"]
