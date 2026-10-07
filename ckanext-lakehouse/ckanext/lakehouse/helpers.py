"""Template helpers, exposed to Jinja as ``h.lakehouse_<name>``."""
from __future__ import annotations

from collections.abc import Callable
from typing import Any

from ckanext.lakehouse import config
from ckanext.lakehouse.om import panel


def om_enabled() -> bool:
    return config.om_enabled()


def om_has_panel(pkg: dict[str, Any]) -> bool:
    """The dataset came from OpenMetadata (it then gets the 'Technical catalog' tab)."""
    return panel.has_panel(pkg)


def om_panel(pkg: dict[str, Any]) -> dict[str, Any] | None:
    return panel.panel(pkg)


_HELPERS: dict[str, Callable[..., Any]] = {
    "om_enabled": om_enabled,
    "om_has_panel": om_has_panel,
    "om_panel": om_panel,
}


def get_helpers() -> dict[str, Callable[..., Any]]:
    return {f"lakehouse_{name}": fn for name, fn in _HELPERS.items()}
