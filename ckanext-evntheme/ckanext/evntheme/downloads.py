"""'Download all' for a dataset: one zip with every file uploaded to CKAN storage.

Linked resources (external URLs, JDBC, APIs) cannot be bundled and are skipped.
Works with the default local-disk uploader; an IUploader for object storage
(MinIO/S3) has no local path, so its files are skipped too.
"""
from __future__ import annotations

import os
import posixpath
import tempfile
import zipfile
from typing import Any
from urllib.parse import urlsplit

from flask import Blueprint, send_file

import ckan.plugins.toolkit as tk
from ckan.lib import uploader

from ckanext.evntheme import config

dataset = Blueprint("evntheme_dataset", __name__)

_MB = 1024 * 1024


def local_files(pkg: dict[str, Any]) -> list[tuple[dict[str, Any], str]]:
    """(resource, path on disk) of every uploaded resource whose file exists."""
    files = []
    for res in pkg.get("resources", []):
        if res.get("url_type") != "upload":
            continue
        get_path = getattr(uploader.get_resource_uploader(res), "get_path", None)
        path = get_path(res["id"]) if get_path else None
        if path and os.path.isfile(path):
            files.append((res, path))
    return files


def _archive_name(res: dict[str, Any], used: set[str]) -> str:
    name = posixpath.basename(urlsplit(res.get("url") or "").path) or res.get("name") or res["id"]
    candidate, n = name, 1
    while candidate in used:
        n += 1
        stem, ext = posixpath.splitext(name)
        candidate = f"{stem}-{n}{ext}"
    used.add(candidate)
    return candidate


def download_all(id: str) -> Any:
    try:
        pkg = tk.get_action("package_show")({}, {"id": id})
    except (tk.ObjectNotFound, tk.NotAuthorized):
        return tk.abort(404, tk._("Dataset not found"))

    files = local_files(pkg)
    if not files:
        return tk.abort(404, tk._("This dataset has no uploaded files"))
    limit = config.get("zip_max_mb") * _MB
    if sum(os.path.getsize(path) for _, path in files) > limit:
        return tk.abort(413, tk._("The files are too large to download together; download them one by one."))

    archive = tempfile.SpooledTemporaryFile(max_size=32 * _MB)
    used: set[str] = set()
    with zipfile.ZipFile(archive, "w", zipfile.ZIP_DEFLATED) as zf:
        for res, path in files:
            zf.write(path, arcname=_archive_name(res, used))
    archive.seek(0)
    return send_file(archive, mimetype="application/zip", as_attachment=True, download_name=f"{pkg['name']}.zip")


dataset.add_url_rule("/dataset/<id>/download-all", view_func=download_all, endpoint="download_all")
