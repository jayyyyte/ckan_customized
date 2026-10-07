"""`ckan lakehouse bootstrap FILE`: organizations, groups, users and who may do what.

The YAML file is the source of truth for what it lists (format: demo/portal.yaml).
Running it again is safe: existing objects are patched, memberships set to the
declared role. With `prune`, memberships the file does not declare are removed from
the organizations and groups it lists (sysadmins are left alone: they can do
everything anyway).

New users get a random password, written once to the credentials file. Existing users
are never modified, except being promoted to sysadmin when the file says so.

CKAN roles (ckan/authz.py):
  organization  admin   manage members, edit/delete every dataset of the organization
                editor  create and edit every dataset of the organization
                member  read the organization's private datasets
  group         admin   manage members, add/remove datasets
                member  add/remove datasets they can edit
"""
from __future__ import annotations

import csv
import io
import json
import re
import secrets
from dataclasses import dataclass, field
from typing import Any

import yaml

import ckan.model as model
import ckan.plugins.toolkit as tk

from ckanext.lakehouse.om import mapping

ORG_ROLES = ("admin", "editor", "member")
GROUP_ROLES = ("admin", "member")
_USER_KEYS = ("name", "fullname", "email", "about")
_GROUP_KEYS = ("name", "title", "description", "image_url")
# CKAN user and group names: lower-case letters, digits, - and _ (no dots).
_NAME = re.compile(r"^[a-z0-9_-]{2,100}$")


class BootstrapError(ValueError):
    pass


@dataclass
class Result:
    created: list[str] = field(default_factory=list)
    updated: list[str] = field(default_factory=list)
    memberships: list[str] = field(default_factory=list)
    removed: list[str] = field(default_factory=list)
    credentials: list[tuple[str, str, str]] = field(default_factory=list)  # name, email, password
    notes: list[str] = field(default_factory=list)


def load(text: str) -> dict[str, Any]:
    """Parse and validate the file before anything is written."""
    data = yaml.safe_load(text) or {}
    if not isinstance(data, dict):
        raise BootstrapError("the file must be a mapping with users / organizations / groups")
    for section in ("users", "organizations", "groups"):
        data.setdefault(section, [])
        if not isinstance(data[section], list):
            raise BootstrapError(f"{section}: must be a list")
    users = set()
    for user in data["users"]:
        if not user.get("name") or not user.get("email"):
            raise BootstrapError(f"user {user!r}: name and email are required")
        if not _NAME.match(str(user["name"])):
            raise BootstrapError(f"user {user['name']!r}: use 2-100 lower-case letters, digits, - or _")
        users.add(user["name"])
    for section, roles in (("organizations", ORG_ROLES), ("groups", GROUP_ROLES)):
        for item in data[section]:
            if not _NAME.match(str(item.get("name") or "")):
                raise BootstrapError(f"{section}: {item.get('name')!r} is not a valid name "
                                     "(2-100 lower-case letters, digits, - or _)")
            for username, role in (item.get("members") or {}).items():
                if role not in roles:
                    raise BootstrapError(f"{item['name']}: role {role!r} of {username} must be one of "
                                         f"{', '.join(roles)}")
    return data


def _extras(item: dict[str, Any], om: dict[str, list[str]]) -> list[dict[str, str]]:
    extras = {str(k): str(v) for k, v in (item.get("extras") or {}).items()}
    for key, values in om.items():
        if values:
            extras[key] = json.dumps(list(values), ensure_ascii=False)
    return [{"key": k, "value": v} for k, v in sorted(extras.items())]


class Bootstrap:
    def __init__(self, data: dict[str, Any], acting_user: str) -> None:
        if model.User.by_name(acting_user) is None:
            raise BootstrapError(f"user {acting_user!r} does not exist; pass --user <sysadmin>")
        self.data = data
        self.acting_user = acting_user
        self.result = Result()

    def _action(self, name: str, data: dict[str, Any]) -> Any:
        return tk.get_action(name)({"user": self.acting_user, "ignore_auth": True}, data)

    def new_users(self) -> list[str]:
        return [u["name"] for u in self.data["users"] if model.User.by_name(u["name"]) is None]

    def run(self, prune: bool = False) -> Result:
        for user in self.data["users"]:
            self._user(user)
        for org in self.data["organizations"]:
            om = org.get("openmetadata") or {}
            self._group("organization", org, {mapping.ORG_TEAMS: om.get("teams") or [],
                                              mapping.ORG_FQN_PATTERNS: om.get("fqn") or []})
        for group in self.data["groups"]:
            om = group.get("openmetadata") or {}
            self._group("group", group, {mapping.GROUP_DOMAINS: om.get("domains") or []})
        for kind, section in (("organization", "organizations"), ("group", "groups")):
            for item in self.data[section]:
                self._members(kind, item, prune)
        return self.result

    def _user(self, spec: dict[str, Any]) -> None:
        user = model.User.by_name(spec["name"])
        if user is None:
            password = secrets.token_urlsafe(15)
            payload = {k: spec[k] for k in _USER_KEYS if spec.get(k)}
            self._action("user_create", {**payload, "password": password})
            self.result.created.append(f"user {spec['name']}")
            self.result.credentials.append((spec["name"], spec["email"], password))
            user = model.User.by_name(spec["name"])
        if spec.get("sysadmin") and not user.sysadmin:
            user.sysadmin = True  # what `ckan sysadmin add` does
            model.Session.commit()
            self.result.updated.append(f"user {spec['name']}: sysadmin")
        elif spec.get("sysadmin") is False and user.sysadmin:
            self.result.notes.append(f"{spec['name']} is a sysadmin although the file says no; "
                                     f"demote with `ckan sysadmin remove {spec['name']}`")

    def _group(self, kind: str, spec: dict[str, Any], om: dict[str, list[str]]) -> None:
        payload = {k: spec[k] for k in _GROUP_KEYS if spec.get(k) is not None}
        payload["extras"] = _extras(spec, om)
        try:
            existing = self._action(f"{kind}_show", {"id": spec["name"], "include_datasets": False})
        except tk.ObjectNotFound:
            self._action(f"{kind}_create", payload)
            self.result.created.append(f"{kind} {spec['name']}")
            return
        current = {k: existing.get(k) for k in payload if k != "extras"}
        current_extras = sorted((e["key"], e["value"]) for e in existing.get("extras") or [])
        wanted_extras = sorted((e["key"], e["value"]) for e in payload["extras"])
        if current != {k: v for k, v in payload.items() if k != "extras"} or current_extras != wanted_extras:
            self._action(f"{kind}_patch", {**payload, "id": existing["id"]})
            self.result.updated.append(f"{kind} {spec['name']}")

    def _members(self, kind: str, spec: dict[str, Any], prune: bool) -> None:
        declared = {u: r for u, r in (spec.get("members") or {}).items()}
        # Straight from the member table: member_list translates capacities ("Admin" -> "Quản trị").
        group = model.Group.get(spec["name"])
        rows = (
            model.Session.query(model.User.name, model.Member.capacity)
            .join(model.Member, model.Member.table_id == model.User.id)
            .filter(model.Member.group_id == group.id, model.Member.table_name == "user",
                    model.Member.state == "active")
        )
        current_by_name = dict(rows)

        for username, role in declared.items():
            if model.User.by_name(username) is None:
                self.result.notes.append(f"{kind} {spec['name']}: user {username} does not exist, skipped")
                continue
            if current_by_name.get(username) != role:
                self._action(f"{kind}_member_create", {"id": spec["name"], "username": username, "role": role})
                self.result.memberships.append(f"{kind} {spec['name']}: {username} = {role}")
        if not prune:
            return
        for username in set(current_by_name) - set(declared):
            user = model.User.by_name(username)
            if user is None or user.sysadmin:
                continue
            self._action(f"{kind}_member_delete", {"id": spec["name"], "username": username})
            self.result.removed.append(f"{kind} {spec['name']}: {username}")


def credentials_csv(rows: list[tuple[str, str, str]]) -> str:
    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow(["username", "email", "password"])
    writer.writerows(rows)
    return buffer.getvalue()
