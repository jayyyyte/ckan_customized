"""`/dataset/<id>/openmetadata`: the "Technical catalog" tab as an HTML fragment.

The dataset page renders the tab inline when it is the active one (works without
JS); otherwise lakehouse-om-panel.js loads this fragment the first time the tab is
shown, so a slow OpenMetadata never delays the page itself.
"""
from __future__ import annotations

from flask import Blueprint

import ckan.plugins.toolkit as tk

from ckanext.lakehouse.om import panel

dataset = Blueprint("lakehouse_om", __name__)


def fragment(id: str) -> str:  # noqa: A002 - CKAN's URL parameter name
    try:
        pkg = tk.get_action("package_show")({}, {"id": id})
    except tk.ObjectNotFound:
        return tk.abort(404, tk._("Dataset not found"))
    except tk.NotAuthorized:
        return tk.abort(403, tk._("Not authorized to see this page"))
    data = panel.panel(pkg)
    if data is None:
        return tk.abort(404, tk._("Dataset not found"))
    return tk.render("lakehouse/om_panel.html", {"pkg": pkg, "om": data})


dataset.add_url_rule("/dataset/<id>/openmetadata", view_func=fragment, endpoint="panel")
