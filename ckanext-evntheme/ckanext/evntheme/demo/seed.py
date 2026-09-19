"""Load the demo content of demo/portal.json and demo/mds.json into a local CKAN.

Runs actions as a real sysadmin (not the site user) so the activity stream shows
the changes: activity by the site user is hidden by CKAN.
"""
from __future__ import annotations

import csv
import datetime as dt
import io
import json
import logging
import random
import uuid
from collections.abc import Iterator
from pathlib import Path
from typing import Any

from werkzeug.datastructures import FileStorage

import ckan.model as model
import ckan.plugins.toolkit as tk
from ckan.lib.search import rebuild
from ckan.plugins import plugin_loaded

from ckanext.evntheme.cache import clear_all
from ckanext.evntheme.mds import service as mds_service
from ckanext.evntheme.mds.model import MdsCatalog

log = logging.getLogger(__name__)

DEMO_DIR = Path(__file__).parent
USAGE_KEY_PREFIX = "evntheme-demo-"
USAGE_DAYS = 30
# Keys of a portal.json dataset passed as-is to package_create.
DATASET_FIELDS = ("name", "title", "owner_org", "notes", "license_id", "maintainer", "maintainer_email", "version")


def _read(name: str) -> Any:
    return json.loads((DEMO_DIR / name).read_text("utf-8"))


def _extras(values: dict[str, Any]) -> list[dict[str, str]]:
    return [{"key": k, "value": str(v)} for k, v in values.items()]


def _now() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc).replace(tzinfo=None)


class Seeder:
    def __init__(self, username: str) -> None:
        if model.User.by_name(username) is None:
            raise ValueError(f"user {username!r} does not exist; pass --user <sysadmin>")
        self.username = username
        self.portal = _read("portal.json")

    def _context(self) -> dict[str, Any]:
        return {"user": self.username, "ignore_auth": True}

    def _action(self, name: str, data: dict[str, Any]) -> Any:
        return tk.get_action(name)(self._context(), data)

    def _upsert(self, kind: str, data: dict[str, Any]) -> dict[str, Any]:
        try:
            existing = self._action(f"{kind}_show", {"id": data["name"]})
        except tk.ObjectNotFound:
            return self._action(f"{kind}_create", data)
        return self._action(f"{kind}_patch", {**data, "id": existing["id"]})

    # --- steps -----------------------------------------------------------------

    def run(self, usage: bool) -> None:
        for group in self.portal["groups"]:
            data = {k: v for k, v in group.items() if k != "tone"}
            self._upsert("group", {**data, "extras": _extras({"tone": group["tone"]} if "tone" in group else {})})
        for org in self.portal["organizations"]:
            self._upsert("organization", {**org, "extras": _extras(org.get("extras", {}))})
        for spec in self.portal["datasets"]:
            self._dataset(spec)
        self._backdate()
        mds_service.load_many(_read("mds.json"))
        if usage and plugin_loaded("tracking"):
            self._usage()
        clear_all()

    def _dataset(self, spec: dict[str, Any]) -> None:
        data = {key: spec[key] for key in DATASET_FIELDS if key in spec}
        data["tags"] = [{"name": t} for t in spec.get("tags", [])]
        data["groups"] = [{"name": g} for g in spec.get("groups", [])]
        data["extras"] = _extras(spec.get("extras", {}))
        try:
            existing = self._action("package_show", {"id": spec["name"]})
        except tk.ObjectNotFound:
            existing = None
        if existing:
            self._action("package_patch", {**data, "id": existing["id"]})
            return
        pkg = self._action("package_create", data)
        for res in spec.get("resources", []):
            self._action("resource_create", self._resource(pkg, res))
        log.info("created %s", pkg["name"])

    def _resource(self, pkg: dict[str, Any], spec: dict[str, Any]) -> dict[str, Any]:
        data = {"package_id": pkg["id"], "name": spec["name"], "format": spec["format"],
                "description": spec.get("description", "")}
        body = _file_body(spec)
        if body is not None:
            data["upload"] = FileStorage(io.BytesIO(body), filename=spec["name"])
            data["url"] = spec["name"]
        elif spec.get("api"):
            site = tk.config.get("ckan.site_url").rstrip("/")
            data["url"] = f"{site}/api/3/action/package_show?id={pkg['name']}"
        else:
            data["url"] = spec["url"]
        return data

    def _backdate(self) -> None:
        """Spread 'last updated' like a real portal (the API always stamps 'now')."""
        now = _now()
        for spec in self.portal["datasets"]:
            pkg = model.Package.get(spec["name"])
            if pkg is None:
                continue
            when = now - dt.timedelta(hours=spec.get("age_hours", 0))
            pkg.metadata_modified = when
            for res in pkg.resources:
                res.last_modified = when
                res.metadata_modified = when
        model.Session.commit()
        for spec in self.portal["datasets"]:
            pkg = model.Package.get(spec["name"])
            if pkg is not None:
                rebuild(pkg.id)

    def _usage(self) -> None:
        """Simulated page views and downloads, fed through the tracking plugin's own pipeline."""
        from ckanext.tracking.cli.tracking import update_all
        from ckanext.tracking.model import TrackingRaw

        table = TrackingRaw.__table__
        model.Session.execute(table.delete().where(table.c.user_key.like(USAGE_KEY_PREFIX + "%")))
        rows = list(self._usage_rows())
        if rows:
            model.Session.execute(table.insert(), rows)
        model.Session.commit()
        update_all((_now() - dt.timedelta(days=USAGE_DAYS + 1)).strftime("%Y-%m-%d"))

    def _usage_rows(self) -> Iterator[dict[str, Any]]:
        rng = random.Random(20260919)
        now = _now()

        def hits(url: str, kind: str, count: int) -> Iterator[dict[str, Any]]:
            for _ in range(count):
                yield {
                    "user_key": USAGE_KEY_PREFIX + uuid.UUID(int=rng.getrandbits(128)).hex,
                    "url": url,
                    "tracking_type": kind,
                    "access_timestamp": now - dt.timedelta(minutes=rng.randint(1, USAGE_DAYS * 24 * 60)),
                }

        for spec in self.portal["datasets"]:
            try:
                pkg = self._action("package_show", {"id": spec["name"]})
            except tk.ObjectNotFound:
                continue
            yield from hits(f"/dataset/{pkg['name']}", "page", spec.get("views", 0))
            # Same order as created; a resource added by hand later simply gets no simulated usage.
            for res_spec, res in zip(spec.get("resources", []), pkg["resources"], strict=False):
                yield from hits(res["url"], "resource", res_spec.get("downloads", 0))

    def reset(self) -> None:
        """Purge everything the demo created (datasets, organisations, groups, code lists, usage)."""
        for spec in self.portal["datasets"]:
            self._purge("dataset_purge", spec["name"])
        for org in self.portal["organizations"]:
            self._purge("organization_purge", org["name"])
        for group in self.portal["groups"]:
            self._purge("group_purge", group["name"])
        codes = [c["code"] for c in _read("mds.json")["catalogs"]]
        if mds_service.tables_ready():
            for catalog in model.Session.query(MdsCatalog).filter(MdsCatalog.code.in_(codes)):
                model.Session.delete(catalog)
        if plugin_loaded("tracking"):
            from ckanext.tracking.model import TrackingRaw

            table = TrackingRaw.__table__
            model.Session.execute(table.delete().where(table.c.user_key.like(USAGE_KEY_PREFIX + "%")))
        model.Session.commit()
        clear_all()

    def _purge(self, action: str, name: str) -> None:
        try:
            self._action(action, {"id": name})
        except tk.ObjectNotFound:
            pass


def _file_body(spec: dict[str, Any]) -> bytes | None:
    """Uploaded demo files are generated from inline data: rows (CSV), json or geojson."""
    if "rows" in spec:
        buffer = io.StringIO()
        csv.writer(buffer).writerows(spec["rows"])
        return buffer.getvalue().encode("utf-8")
    for key in ("json", "geojson"):
        if key in spec:
            return json.dumps(spec[key], ensure_ascii=False, indent=2).encode("utf-8")
    return None
