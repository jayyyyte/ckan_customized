"""'Download all' for a dataset: one zip with every file uploaded to CKAN storage.

Linked resources (external URLs, JDBC, APIs) cannot be bundled and are skipped.
Works with the default local-disk uploader; an IUploader for object storage
(MinIO/S3) has no local path, so its files are skipped too.

Also: a full, unbounded CSV export of an OpenMetadata-synced resource's Trino table
(`download_full`), for when the 1000-row DataStore preview is not enough.
"""
from __future__ import annotations

import csv
import io
import os
import posixpath
import tempfile
import zipfile
from typing import Any
from urllib.parse import urlsplit

from flask import Blueprint, Response, send_file, stream_with_context

import ckan.plugins.toolkit as tk
from ckan.lib import uploader

from ckanext.evntheme import config
from ckanext.evntheme.openmetadata import TrinoConfig, TrinoError, open_cursor

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


def _trino_table(pkg: dict[str, Any]) -> tuple[str, str, str] | None:
    """(catalog, schema, table) from the `openmetadata_fqn` extra `sync-openmetadata` writes
    (service.database.schema.table); None for datasets not synced from OpenMetadata."""
    fqn = next((e["value"] for e in pkg.get("extras", []) if e["key"] == "openmetadata_fqn"), None)
    if not fqn or fqn.count(".") < 2:
        return None
    catalog, schema, table = fqn.split(".")[-3:]
    return catalog, schema, table


def download_full(id: str, resource_id: str) -> Any:
    """Stream every row of the resource's Trino table as CSV — unlike the DataStore preview
    (capped at `openmetadata_preview_rows`), this queries Trino live and copies nothing into
    CKAN's own database. Can be slow for a very large table: it is not paginated."""
    try:
        pkg = tk.get_action("package_show")({}, {"id": id})
    except (tk.ObjectNotFound, tk.NotAuthorized):
        return tk.abort(404, tk._("Dataset not found"))
    resource = next((r for r in pkg["resources"] if r["id"] == resource_id), None)
    if resource is None:
        return tk.abort(404, tk._("Resource not found"))

    table = _trino_table(pkg)
    trino_user = config.get("trino_user")
    if not table or not trino_user:
        return tk.abort(404, tk._("This resource has no full data source to download"))

    cfg = TrinoConfig(
        config.get("trino_query_host") or config.get("openmetadata_trino_host"),
        trino_user, config.get("trino_password"),
    )
    try:
        conn, columns, cursor = open_cursor(cfg, *table)
    except TrinoError as err:
        return tk.abort(502, str(err))

    def rows() -> Any:
        buf = io.StringIO()
        writer = csv.writer(buf)
        writer.writerow(columns)
        yield buf.getvalue()
        try:
            while True:
                buf.seek(0)
                buf.truncate(0)
                batch = cursor.fetchmany(1000)
                if not batch:
                    return
                writer.writerows(batch)
                yield buf.getvalue()
        finally:
            conn.close()

    filename = f"{resource.get('name') or table[2]}.csv"
    return Response(
        stream_with_context(rows()), mimetype="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


dataset.add_url_rule("/dataset/<id>/download-all", view_func=download_all, endpoint="download_all")
dataset.add_url_rule(
    "/dataset/<id>/resource/<resource_id>/download-full", view_func=download_full, endpoint="download_full",
)
