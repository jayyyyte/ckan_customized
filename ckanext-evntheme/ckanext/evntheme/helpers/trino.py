"""'How to connect' box for Lakehouse tables published as `jdbc:trino://` resources."""
from __future__ import annotations

from typing import Any
from urllib.parse import parse_qsl, urlsplit

_JDBC_TRINO = "jdbc:trino://"


def trino_connection(url: str | None) -> dict[str, Any] | None:
    """Split `jdbc:trino://host[:port][/catalog[/schema]][?SSL=true]`; None if not a usable Trino URL."""
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
