"""Blueprint of the "Danh mục chuẩn" pages: /mds, /mds/<code>, /mds/<code>/download.<fmt>."""
from __future__ import annotations

from flask import Blueprint, Response

import ckan.plugins.toolkit as tk

from ckanext.evntheme.mds import service

mds = Blueprint("evntheme_mds", __name__, url_prefix="/mds")

EXPORT_FORMATS = ("csv", "json")


def index() -> str:
    """Show the first catalog of the tree (or an empty state)."""
    code = service.first_catalog_code()
    return _render(service.get_catalog(code) if code else None)


def read(code: str) -> str:
    page = service.get_catalog(code)
    if page is None:
        return tk.abort(404, tk._("Code list not found"))
    return _render(page)


def download(code: str, fmt: str) -> Response:
    if fmt not in EXPORT_FORMATS:
        return tk.abort(404)
    page = service.get_catalog(code)
    if page is None:
        return tk.abort(404, tk._("Code list not found"))
    body, mimetype = service.export(page, fmt)
    filename = f"{page.catalog.code}-v{page.catalog.version or 'latest'}.{fmt}"
    return Response(body, mimetype=mimetype, headers={"Content-Disposition": f'attachment; filename="{filename}"'})


def _render(page: service.CatalogPage | None) -> str:
    return tk.render(
        "evntheme/mds/index.html",
        {"page": page, "tree": service.catalog_tree(), "summary": service.summary()},
    )


mds.add_url_rule("/", view_func=index, endpoint="index")
mds.add_url_rule("/<code>", view_func=read, endpoint="read")
mds.add_url_rule("/<code>/download.<fmt>", view_func=download, endpoint="download")
