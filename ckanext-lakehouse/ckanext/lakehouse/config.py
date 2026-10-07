"""Config options of the extension (``ckanext.lakehouse.*``) and typed accessors.

Inspect them with ``ckan config declaration lakehouse``. On Kubernetes each key can be
set as an env var (ckanext-envvars): ``ckanext.lakehouse.om.url`` is
``CKANEXT__LAKEHOUSE__OM__URL``. The token belongs in the Secret, never in a ConfigMap.
"""
from __future__ import annotations

from typing import Any

import ckan.plugins.toolkit as tk

PREFIX = "ckanext.lakehouse."

# key -> (default, description). Types come from the default value.
OPTIONS: dict[str, tuple[Any, str]] = {
    # Connection
    "om.url": ("", "OpenMetadata server, e.g. http://openmetadata:8585 (without /api). Empty turns "
                   "every OpenMetadata feature off."),
    "om.ui_url": ("", "OpenMetadata address for browser links. Empty: same as om.url."),
    "om.api_token": ("", "JWT of an OpenMetadata bot with read access (Settings > Bots). Secret."),
    "om.timeout": (5, "Seconds to wait for OpenMetadata while rendering the dataset page."),
    "om.sync_timeout": (30, "Seconds to wait for each OpenMetadata request during a sync."),
    "om.verify_ssl": (True, "Verify the TLS certificate of an https:// OpenMetadata."),
    # What the sync publishes
    "om.include": ("", "Table FQN patterns to publish as datasets (fnmatch, space separated), e.g. "
                       "'trino_lakehouse.iceberg_curated.*'. Empty publishes nothing."),
    "om.exclude": ("", "Table FQN patterns left out even when they match om.include."),
    "om.require_tags": ("", "Tag FQNs, space separated: only tables carrying at least one of them are "
                            "published (e.g. 'Tier.Tier1'). Empty: no tag needed."),
    "om.default_org": ("", "Organization for tables no organization claims (om_teams / om_fqn_patterns). "
                           "Empty: such tables are skipped."),
    "om.private": (True, "Create new datasets as private; editors publish them. Never changed afterwards."),
    "om.on_removed": ("delete", "Dataset of a table that left OpenMetadata or the scope: 'delete' "
                                "(soft delete, restored if the table comes back) or 'keep'."),
    "om.sync_user": ("om-sync", "CKAN user the sync acts as, so activity streams name it. Falls back to "
                                "the site user if missing."),
    "om.fetch_profile": (True, "Read the latest table profile (row count) of each table during a sync."),
    # Resources
    "om.trino_jdbc_url": ("", "Trino JDBC base, e.g. jdbc:trino://10.1.117.91:30800. Each table of a "
                              "Trino service gets a jdbc:trino://.../catalog/schema link. Empty: no link."),
    "om.trino_catalogs": ("", "'service.database=catalog' pairs, space separated, for services whose "
                              "OpenMetadata database name is not the Trino catalog."),
    # Dataset page
    "om.cache_ttl": (600, "Seconds the 'Technical catalog' tab keeps OpenMetadata answers (Redis). "
                          "0 disables the cache."),
}


def declare(declaration: Any, key: Any) -> None:
    """IConfigDeclaration: register every option with its type and description."""
    for name, (default, description) in OPTIONS.items():
        option_key = key.from_string(PREFIX + name)
        if isinstance(default, bool):
            option = declaration.declare_bool(option_key, default)
        elif isinstance(default, int):
            option = declaration.declare_int(option_key, default)
        else:
            option = declaration.declare(option_key, default)
        option.set_description(description)


def get(name: str) -> Any:
    if name not in OPTIONS:
        raise KeyError(f"Unknown lakehouse option: {name}")
    return tk.config.get(PREFIX + name)


def get_list(name: str) -> list[str]:
    return [item for item in (get(name) or "").split() if item]


def om_enabled() -> bool:
    return bool(get("om.url"))


def om_ui_url() -> str:
    return (get("om.ui_url") or get("om.url") or "").rstrip("/")
