"""Read-only actions on *public* data, independent of who is viewing the page.

The theme's counters and lists (header badges, home page, organisation directory,
related datasets) only show public content: `package_search` leaves private and draft
datasets out unless asked. Several of them are cached for every visitor, so they must
not depend on the visitor's permissions: running them as the visitor would tie the
cache to whoever came first, and break every page for a session whose user was deleted
(CKAN then refuses all actions with NotAuthorized).

Only for reads of public data. Anything user-specific (DataStore rows, activity,
following) keeps the visitor's context.
"""
from __future__ import annotations

from typing import Any

import ckan.plugins.toolkit as tk

READ_ONLY_ACTIONS = frozenset({"package_search", "organization_list", "group_list"})


def action(name: str, data_dict: dict[str, Any]) -> Any:
    if name not in READ_ONLY_ACTIONS:
        raise ValueError(f"{name} is not a public read-only action")
    return tk.get_action(name)({"ignore_auth": True}, data_dict)
