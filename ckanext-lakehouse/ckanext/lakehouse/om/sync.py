"""`ckan lakehouse om sync`: publish OpenMetadata tables as CKAN datasets.

Idempotent: a dataset is only written when something OpenMetadata owns changed (see
mapping.py), so an hourly run leaves the activity streams quiet. Datasets are matched
by the OpenMetadata table id (extra `om_id`), so renaming a table keeps its CKAN URL.

Safety: if listing OpenMetadata fails nothing is written; if it succeeds but nothing
is in scope while datasets exist, nothing is removed unless `allow_empty`.
"""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from typing import Any

import ckan.model as model
import ckan.plugins.toolkit as tk

from ckanext.lakehouse import config
from ckanext.lakehouse.om import mapping
from ckanext.lakehouse.om.client import OMClient, OMError

log = logging.getLogger(__name__)


@dataclass
class Report:
    tables: int = 0
    in_scope: int = 0
    created: list[str] = field(default_factory=list)
    updated: list[str] = field(default_factory=list)
    unchanged: int = 0
    removed: list[str] = field(default_factory=list)
    skipped: list[tuple[str, str]] = field(default_factory=list)
    errors: list[tuple[str, str]] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)


def _json_list(value: Any) -> list[str]:
    try:
        data = json.loads(value or "[]")
    except (TypeError, ValueError):
        return []
    return [str(v) for v in data] if isinstance(data, list) else []


def load_rules() -> mapping.Rules:
    """Scope from config, ownership from the extras `ckan lakehouse bootstrap` put on orgs and groups."""
    rules = mapping.Rules(
        include=config.get_list("om.include"),
        exclude=config.get_list("om.exclude"),
        require_tags=config.get_list("om.require_tags"),
        default_org=config.get("om.default_org") or None,
        ui_url=config.om_ui_url(),
        trino_jdbc_url=config.get("om.trino_jdbc_url") or "",
        trino_catalogs=dict(p.split("=", 1) for p in config.get_list("om.trino_catalogs") if "=" in p),
    )
    groups = model.Session.query(model.Group).filter(model.Group.state == "active")
    for group in groups:
        extras = dict(group.extras or {})
        if group.is_organization:
            for team in _json_list(extras.get(mapping.ORG_TEAMS)):
                rules.team_orgs[team.casefold()] = group.name
            for pattern in _json_list(extras.get(mapping.ORG_FQN_PATTERNS)):
                rules.fqn_orgs.append((pattern, group.name))
        else:
            for domain in _json_list(extras.get(mapping.GROUP_DOMAINS)):
                rules.domain_groups[domain.casefold()] = group.name
    return rules


def client_for_sync() -> OMClient:
    return OMClient(config.get("om.url"), config.get("om.api_token") or "",
                    timeout=config.get("om.sync_timeout"), verify=config.get("om.verify_ssl"))


def managed_datasets() -> dict[str, dict[str, str]]:
    """om_id -> {name, state} of every dataset a sync created, deleted ones included."""
    rows = (
        model.Session.query(model.Package.name, model.Package.state, model.PackageExtra.value)
        .join(model.PackageExtra, model.PackageExtra.package_id == model.Package.id)
        .filter(model.PackageExtra.key == mapping.Ext.ID, model.PackageExtra.state == "active")
        .filter(model.Package.state != "draft")
    )
    return {om_id: {"name": name, "state": state} for name, state, om_id in rows}


class Syncer:
    def __init__(self, client: OMClient, rules: mapping.Rules, user: str, *, private: bool = True,
                 on_removed: str = "delete", fetch_profile: bool = True, dry_run: bool = False) -> None:
        self.client = client
        self.rules = rules
        self.user = user
        self.private = private
        self.on_removed = on_removed
        self.fetch_profile = fetch_profile
        self.dry_run = dry_run
        self.report = Report()

    def _action(self, name: str, data: dict[str, Any]) -> Any:
        return tk.get_action(name)({"user": self.user, "ignore_auth": True}, data)

    def _tables(self) -> list[dict[str, Any]]:
        """Every table OpenMetadata lists for the configured scope. Raises OMError."""
        schemas = mapping.schema_prefixes(self.rules.include)
        if schemas is None:
            return list(self.client.iter_tables())
        tables: list[dict[str, Any]] = []
        for schema in schemas:
            try:
                tables.extend(self.client.iter_tables(schema))
            except OMError as err:
                if err.status != 404:  # a pattern naming a schema that does not exist (yet)
                    raise
                self.report.notes.append(f"schema {schema} not found in OpenMetadata")
        return tables

    def run(self, allow_empty: bool = False) -> Report:
        report = self.report
        if not self.rules.include:
            report.notes.append("ckanext.lakehouse.om.include is empty: nothing is published")
        tables = self._tables() if self.rules.include else []
        report.tables = len(tables)
        managed = managed_datasets()
        seen: set[str] = set()
        for table in tables:
            if not mapping.in_scope(table, self.rules):
                continue
            report.in_scope += 1
            seen.add(table.get("id", ""))
            try:
                self._one(table, managed)
            except (tk.ValidationError, OMError) as err:
                message = err.error_summary if isinstance(err, tk.ValidationError) else str(err)
                report.errors.append((table.get("fullyQualifiedName", "?"), str(message)))
                log.warning("om sync %s: %s", table.get("fullyQualifiedName"), message)
                model.Session.rollback()
        self._remove(managed, seen, allow_empty)
        return report

    def _one(self, table: dict[str, Any], managed: dict[str, dict[str, str]]) -> None:
        fqn = table["fullyQualifiedName"]
        profile = None
        if self.fetch_profile:
            try:
                profile = self.client.profile(fqn)
            except OMError as err:
                log.info("om sync %s: no profile (%s)", fqn, err)
        want = mapping.desired(table, self.rules, profile)
        if not want["owner_org"]:
            self.report.skipped.append((fqn, "no organization claims it (om_teams, om_fqn_patterns, om.default_org)"))
            return

        known = managed.get(table.get("id", ""))
        if known is None:
            existing = model.Package.get(want["name"])
            if existing is not None:
                self.report.skipped.append((fqn, f"dataset name {want['name']!r} is taken by a dataset "
                                                 "that does not come from OpenMetadata"))
                return
            payload = mapping.create_payload(want, self.private)
            groups = {g["name"] for g in payload.pop("groups")}
            if not self.dry_run:
                pkg = self._action("package_create", payload)
                self._set_groups(pkg["id"], set(), groups)
            self.report.created.append(want["name"])
            return

        pkg = self._action("package_show", {"id": known["name"]})
        patch = mapping.update_payload(pkg, want)
        if not patch:
            self.report.unchanged += 1
            return
        changed = sorted(patch)
        groups = patch.pop("groups", None)
        if not self.dry_run:
            if patch:
                self._action("package_patch", {**patch, "id": pkg["id"]})
            if groups is not None:
                self._set_groups(pkg["id"], {g["name"] for g in pkg.get("groups") or []},
                                 {g["name"] for g in groups})
        self.report.updated.append(f"{pkg['name']} ({', '.join(changed)})")

    def _set_groups(self, pkg_id: str, old: set[str], new: set[str]) -> None:
        """Group membership through member_create/delete, not package_create/patch.

        Saving `groups` with a dataset checks that the acting user may read each group
        (authz.has_user_permission_for_group_or_org), which `ignore_auth` does not lift:
        for a sync user outside the groups CKAN silently drops them (gotchas 28).
        """
        for group in sorted(new - old):
            self._action("member_create", {"id": group, "object": pkg_id, "object_type": "package",
                                           "capacity": "public"})
        for group in sorted(old - new):
            self._action("member_delete", {"id": group, "object": pkg_id, "object_type": "package"})

    def _remove(self, managed: dict[str, dict[str, str]], seen: set[str], allow_empty: bool) -> None:
        gone = [info["name"] for om_id, info in managed.items() if om_id not in seen and info["state"] == "active"]
        if not gone:
            return
        if self.on_removed != "delete":
            self.report.notes.append(f"{len(gone)} dataset(s) no longer in scope, kept (om.on_removed=keep)")
            return
        if not seen and not allow_empty:
            self.report.notes.append(
                f"nothing in scope but {len(gone)} dataset(s) exist: not removing them "
                "(check om.include, or pass --allow-empty)")
            return
        for name in gone:
            if not self.dry_run:
                self._action("package_delete", {"id": name})
            self.report.removed.append(name)


def sync_user() -> str:
    """The configured sync user, or the site user when it does not exist."""
    name = config.get("om.sync_user")
    if name and model.User.by_name(name) is not None:
        return name
    site_user = tk.get_action("get_site_user")({"ignore_auth": True}, {})
    log.warning("om sync: user %r not found, acting as the site user (hidden from activity)", name)
    return site_user["name"]
