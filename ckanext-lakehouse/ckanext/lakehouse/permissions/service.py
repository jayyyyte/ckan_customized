"""Sysadmin user & role management: read/write memberships, effective access preview, user lifecycle.

In CKAN 2.11:
* Ownership and private dataset visibility strictly follow the owning **Organization** (`owner_org`).
* Any member (`admin`, `editor`, `member`) of an organization can read its private datasets.
* Only `admin` and `editor` of the organization can create or edit its datasets; only `admin` can
  manage organization members or delete datasets.
* **Groups** (data domains) classify datasets by topic across organizations; being in a group never
  grants read access to a private dataset owned by another organization.
"""
from __future__ import annotations

import csv
import io
import json
import re
import secrets
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from sqlalchemy import func

import ckan.model as model
import ckan.plugins.toolkit as tk

from ckanext.lakehouse.bootstrap import GROUP_ROLES, ORG_ROLES
from ckanext.lakehouse.om import mapping

_NAME_RE = re.compile(r"^[a-z0-9_-]{2,100}$")
_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
MIN_PASSWORD_LEN = 8


class PermissionFormError(ValueError):
    """User-facing validation error on the permissions admin page."""


@dataclass
class UnitMember:
    username: str
    display_name: str
    email: str
    sysadmin: bool
    state: str
    role: str


@dataclass
class UnitInfo:
    id: str
    name: str
    title: str
    description: str
    is_org: bool
    abbreviation: str = ""
    org_type: str = ""
    om_teams: list[str] = field(default_factory=list)
    om_fqn_patterns: list[str] = field(default_factory=list)
    om_domains: list[str] = field(default_factory=list)
    public_datasets: int = 0
    private_datasets: int = 0
    members: list[UnitMember] = field(default_factory=list)

    @property
    def total_datasets(self) -> int:
        return self.public_datasets + self.private_datasets

    @property
    def role_counts(self) -> dict[str, int]:
        counts = {"admin": 0, "editor": 0, "member": 0}
        for member in self.members:
            if member.role in counts:
                counts[member.role] += 1
        return counts


@dataclass
class UserAccessPreview:
    is_sysadmin: bool
    is_active: bool
    total_public_datasets: int
    accessible_private_datasets: int
    total_accessible_datasets: int
    read_private_orgs: list[UnitInfo] = field(default_factory=list)
    edit_orgs: list[UnitInfo] = field(default_factory=list)
    manage_orgs: list[UnitInfo] = field(default_factory=list)
    manage_groups: list[UnitInfo] = field(default_factory=list)
    member_groups: list[UnitInfo] = field(default_factory=list)


@dataclass
class UserRow:
    id: str
    name: str
    fullname: str
    display_name: str
    email: str
    about: str
    sysadmin: bool
    state: str
    created: datetime | None
    org_roles: dict[str, str] = field(default_factory=dict)
    group_roles: dict[str, str] = field(default_factory=dict)
    access: UserAccessPreview | None = None

    @property
    def is_active(self) -> bool:
        return self.state == "active"

    @property
    def is_unassigned(self) -> bool:
        return not self.sysadmin and not self.org_roles and not self.group_roles


@dataclass
class Summary:
    total_users: int = 0
    active_users: int = 0
    sysadmin_count: int = 0
    unassigned_users: int = 0
    deleted_users: int = 0
    org_count: int = 0
    group_count: int = 0
    public_datasets: int = 0
    private_datasets: int = 0


@dataclass
class Overview:
    summary: Summary
    organizations: list[UnitInfo]
    groups: list[UnitInfo]
    users: list[UserRow]
    all_users: list[UserRow]


def _json_list(raw: str | None) -> list[str]:
    if not raw:
        return []
    try:
        parsed = json.loads(raw)
    except ValueError:
        return []
    return [str(v) for v in parsed if v] if isinstance(parsed, list) else []


def compute_access_preview(
    *,
    is_sysadmin: bool,
    is_active: bool,
    org_roles: dict[str, str],
    group_roles: dict[str, str],
    organizations: list[UnitInfo],
    groups: list[UnitInfo],
    total_public_datasets: int,
    total_private_datasets: int,
) -> UserAccessPreview:
    """Pure calculation of what a user can view, edit, and manage given their roles."""
    if not is_active:
        return UserAccessPreview(
            is_sysadmin=is_sysadmin,
            is_active=False,
            total_public_datasets=0,
            accessible_private_datasets=0,
            total_accessible_datasets=0,
        )
    if is_sysadmin:
        return UserAccessPreview(
            is_sysadmin=True,
            is_active=True,
            total_public_datasets=total_public_datasets,
            accessible_private_datasets=total_private_datasets,
            total_accessible_datasets=total_public_datasets + total_private_datasets,
            read_private_orgs=list(organizations),
            edit_orgs=list(organizations),
            manage_orgs=list(organizations),
            manage_groups=list(groups),
            member_groups=list(groups),
        )

    read_orgs = [org for org in organizations if org_roles.get(org.name) in ORG_ROLES]
    edit_orgs = [org for org in organizations if org_roles.get(org.name) in ("admin", "editor")]
    manage_orgs = [org for org in organizations if org_roles.get(org.name) == "admin"]
    manage_groups = [grp for grp in groups if group_roles.get(grp.name) == "admin"]
    member_groups = [grp for grp in groups if group_roles.get(grp.name) in GROUP_ROLES]
    private_count = sum(org.private_datasets for org in read_orgs)

    return UserAccessPreview(
        is_sysadmin=False,
        is_active=True,
        total_public_datasets=total_public_datasets,
        accessible_private_datasets=private_count,
        total_accessible_datasets=total_public_datasets + private_count,
        read_private_orgs=read_orgs,
        edit_orgs=edit_orgs,
        manage_orgs=manage_orgs,
        manage_groups=manage_groups,
        member_groups=member_groups,
    )


def _site_user_name() -> str:
    try:
        return tk.get_action("get_site_user")({"ignore_auth": True}, {})["name"]
    except Exception:
        return "default"


def _load_units() -> tuple[list[UnitInfo], list[UnitInfo], int, int]:
    """Load all active organizations and groups with dataset counts and OpenMetadata mappings."""
    group_rows = (
        model.Session.query(model.Group)
        .filter(model.Group.state == "active")
        .order_by(model.Group.title.asc(), model.Group.name.asc())
        .all()
    )

    # Count active public and private datasets per organization (owner_org).
    org_pkg_rows = (
        model.Session.query(model.Package.owner_org, model.Package.private, func.count(model.Package.id))
        .filter(model.Package.state == "active", model.Package.type == "dataset")
        .group_by(model.Package.owner_org, model.Package.private)
        .all()
    )
    org_public: dict[str, int] = {}
    org_private: dict[str, int] = {}
    total_public = 0
    total_private = 0
    for owner_org, is_private, count in org_pkg_rows:
        if is_private:
            total_private += int(count)
            if owner_org:
                org_private[owner_org] = int(count)
        else:
            total_public += int(count)
            if owner_org:
                org_public[owner_org] = int(count)

    # Count active public and private datasets per group (via Member table_name='package').
    grp_pkg_rows = (
        model.Session.query(model.Member.group_id, model.Package.private, func.count(model.Package.id))
        .join(model.Package, model.Package.id == model.Member.table_id)
        .filter(
            model.Member.table_name == "package",
            model.Member.state == "active",
            model.Package.state == "active",
            model.Package.type == "dataset",
        )
        .group_by(model.Member.group_id, model.Package.private)
        .all()
    )
    grp_public: dict[str, int] = {}
    grp_private: dict[str, int] = {}
    for group_id, is_private, count in grp_pkg_rows:
        if is_private:
            grp_private[group_id] = int(count)
        else:
            grp_public[group_id] = int(count)

    organizations: list[UnitInfo] = []
    groups: list[UnitInfo] = []
    for grp in group_rows:
        extras = {k: v.value for k, v in (grp._extras or {}).items() if v.state == "active"}
        if grp.is_organization:
            organizations.append(
                UnitInfo(
                    id=grp.id,
                    name=grp.name,
                    title=grp.title or grp.name,
                    description=grp.description or "",
                    is_org=True,
                    abbreviation=extras.get("abbreviation", ""),
                    org_type=extras.get("org_type", ""),
                    om_teams=_json_list(extras.get(mapping.ORG_TEAMS)),
                    om_fqn_patterns=_json_list(extras.get(mapping.ORG_FQN_PATTERNS)),
                    public_datasets=org_public.get(grp.id, 0),
                    private_datasets=org_private.get(grp.id, 0),
                )
            )
        else:
            groups.append(
                UnitInfo(
                    id=grp.id,
                    name=grp.name,
                    title=grp.title or grp.name,
                    description=grp.description or "",
                    is_org=False,
                    om_domains=_json_list(extras.get(mapping.GROUP_DOMAINS)),
                    public_datasets=grp_public.get(grp.id, 0),
                    private_datasets=grp_private.get(grp.id, 0),
                )
            )
    return organizations, groups, total_public, total_private


def load_overview(q: str = "", role_filter: str = "all") -> Overview:
    """Load organizations, groups, users, memberships, and access previews."""
    site_user = _site_user_name()
    organizations, groups, total_public, total_private = _load_units()
    org_by_id = {o.id: o for o in organizations}
    group_by_id = {g.id: g for g in groups}

    # Read raw capacities from `member` table (gotchas 29: member_list translates capacities).
    member_rows = (
        model.Session.query(model.Member.group_id, model.Member.table_id, model.Member.capacity)
        .join(model.Group, model.Group.id == model.Member.group_id)
        .filter(
            model.Member.table_name == "user",
            model.Member.state == "active",
            model.Group.state == "active",
        )
        .all()
    )

    user_org_roles: dict[str, dict[str, str]] = {}
    user_group_roles: dict[str, dict[str, str]] = {}
    for group_id, user_id, capacity in member_rows:
        role = (capacity or "").lower()
        if group_id in org_by_id and role in ORG_ROLES:
            user_org_roles.setdefault(user_id, {})[org_by_id[group_id].name] = role
        elif group_id in group_by_id and role in GROUP_ROLES:
            user_group_roles.setdefault(user_id, {})[group_by_id[group_id].name] = role

    db_users = (
        model.Session.query(model.User)
        .filter(model.User.name != site_user)
        .order_by(model.User.state.asc(), model.User.sysadmin.desc(), model.User.name.asc())
        .all()
    )

    all_users: list[UserRow] = []
    user_by_name: dict[str, UserRow] = {}
    for u in db_users:
        org_roles = user_org_roles.get(u.id, {})
        group_roles = user_group_roles.get(u.id, {})
        access = compute_access_preview(
            is_sysadmin=bool(u.sysadmin),
            is_active=(u.state == "active"),
            org_roles=org_roles,
            group_roles=group_roles,
            organizations=organizations,
            groups=groups,
            total_public_datasets=total_public,
            total_private_datasets=total_private,
        )
        row = UserRow(
            id=u.id,
            name=u.name,
            fullname=u.fullname or "",
            display_name=u.display_name,
            email=u.email or "",
            about=u.about or "",
            sysadmin=bool(u.sysadmin),
            state=u.state or "active",
            created=u.created,
            org_roles=org_roles,
            group_roles=group_roles,
            access=access,
        )
        all_users.append(row)
        user_by_name[u.name] = row

    # Populate unit.members for each organization and group (active users only, sorted by role then name).
    role_rank = {"admin": 0, "editor": 1, "member": 2}
    for org in organizations:
        members = [
            UnitMember(
                username=u.name,
                display_name=u.display_name,
                email=u.email,
                sysadmin=u.sysadmin,
                state=u.state,
                role=u.org_roles[org.name],
            )
            for u in all_users
            if u.is_active and org.name in u.org_roles
        ]
        org.members = sorted(members, key=lambda m: (role_rank.get(m.role, 9), m.username))

    for grp in groups:
        members = [
            UnitMember(
                username=u.name,
                display_name=u.display_name,
                email=u.email,
                sysadmin=u.sysadmin,
                state=u.state,
                role=u.group_roles[grp.name],
            )
            for u in all_users
            if u.is_active and grp.name in u.group_roles
        ]
        grp.members = sorted(members, key=lambda m: (role_rank.get(m.role, 9), m.username))

    active_users = [u for u in all_users if u.is_active]
    summary = Summary(
        total_users=len(all_users),
        active_users=len(active_users),
        sysadmin_count=sum(1 for u in active_users if u.sysadmin),
        unassigned_users=sum(1 for u in active_users if u.is_unassigned),
        deleted_users=sum(1 for u in all_users if not u.is_active),
        org_count=len(organizations),
        group_count=len(groups),
        public_datasets=total_public,
        private_datasets=total_private,
    )

    filtered = filter_users(all_users, q=q, role_filter=role_filter)
    return Overview(
        summary=summary,
        organizations=organizations,
        groups=groups,
        users=filtered,
        all_users=all_users,
    )


def filter_users(users: list[UserRow], q: str = "", role_filter: str = "all") -> list[UserRow]:
    """Filter user rows by search query and role filter."""
    needle = q.strip().casefold()
    result: list[UserRow] = []
    for u in users:
        if role_filter == "sysadmin" and not (u.is_active and u.sysadmin):
            continue
        if role_filter == "unassigned" and not (u.is_active and u.is_unassigned):
            continue
        if role_filter == "inactive" and u.is_active:
            continue
        if role_filter == "active" and not u.is_active:
            continue
        if needle:
            haystack = f"{u.name} {u.fullname} {u.email}".casefold()
            if needle not in haystack:
                continue
        result.append(u)
    return result


def matrix_csv(overview: Overview) -> str:
    """Serialize the user × organization & domain access matrix to UTF-8 CSV (with BOM for Excel)."""
    buf = io.StringIO()
    writer = csv.writer(buf)
    header = [
        "username",
        "fullname",
        "email",
        "state",
        "sysadmin",
        "private_datasets_readable",
        "total_datasets_readable",
    ]
    for org in overview.organizations:
        label = org.abbreviation or org.title or org.name
        header.append(f"org:{org.name} ({label})")
    for grp in overview.groups:
        label = grp.title or grp.name
        header.append(f"domain:{grp.name} ({label})")
    writer.writerow(header)

    for u in overview.users:
        priv = u.access.accessible_private_datasets if u.access else 0
        total = u.access.total_accessible_datasets if u.access else 0
        row: list[Any] = [
            u.name,
            u.fullname,
            u.email,
            u.state,
            "true" if u.sysadmin else "false",
            priv,
            total,
        ]
        for org in overview.organizations:
            if not u.is_active:
                row.append("")
            elif org.name in u.org_roles:
                row.append(u.org_roles[org.name])
            elif u.sysadmin:
                row.append("sysadmin")
            else:
                row.append("")
        for grp in overview.groups:
            if not u.is_active:
                row.append("")
            elif grp.name in u.group_roles:
                row.append(u.group_roles[grp.name])
            elif u.sysadmin:
                row.append("sysadmin")
            else:
                row.append("")
        writer.writerow(row)
    return "\ufeff" + buf.getvalue()



def validate_username_and_email(name: str, email: str) -> tuple[str, str]:
    clean_name = name.strip()
    clean_email = email.strip()
    if not _NAME_RE.match(clean_name):
        raise PermissionFormError(
            tk._("Username must be 2–100 characters using only lower-case letters, digits, '-' or '_'.")
        )
    if not _EMAIL_RE.match(clean_email):
        raise PermissionFormError(tk._("Please enter a valid email address."))
    return clean_name, clean_email


def _action(acting_user: str, name: str, data: dict[str, Any]) -> Any:
    return tk.get_action(name)({"user": acting_user, "ignore_auth": True}, data)


def _current_unit_memberships(user_id: str, is_org: bool) -> dict[str, str]:
    rows = (
        model.Session.query(model.Group.name, model.Member.capacity)
        .join(model.Member, model.Member.group_id == model.Group.id)
        .filter(
            model.Member.table_id == user_id,
            model.Member.table_name == "user",
            model.Member.state == "active",
            model.Group.state == "active",
            model.Group.is_organization.is_(is_org),
        )
        .all()
    )
    return {name: (cap or "").lower() for name, cap in rows}


def _apply_user_unit_roles(
    acting_user: str,
    user: model.User,
    kind: str,
    valid_roles: tuple[str, ...],
    wanted_roles: dict[str, str],
) -> list[str]:
    is_org = kind == "organization"
    current = _current_unit_memberships(user.id, is_org=is_org)
    changes: list[str] = []

    all_units = (
        model.Session.query(model.Group.name)
        .filter(model.Group.state == "active", model.Group.is_organization.is_(is_org))
        .all()
    )
    valid_unit_names = {name for (name,) in all_units}

    for unit_name, role in sorted(wanted_roles.items()):
        if unit_name not in valid_unit_names:
            continue
        clean_role = role.strip().lower() if role else ""
        if clean_role and clean_role not in valid_roles:
            raise PermissionFormError(tk._("Invalid role '{role}' for {unit}.").format(role=clean_role, unit=unit_name))
        old_role = current.get(unit_name, "")
        if clean_role and clean_role != old_role:
            _action(acting_user, f"{kind}_member_create", {"id": unit_name, "username": user.name, "role": clean_role})
            changes.append(f"{unit_name}: {clean_role}")
        elif not clean_role and old_role:
            _action(acting_user, f"{kind}_member_delete", {"id": unit_name, "username": user.name})
            changes.append(f"{unit_name}: removed")
    return changes


def create_user_with_roles(
    acting_user: str,
    *,
    name: str,
    email: str,
    fullname: str = "",
    about: str = "",
    password: str = "",
    sysadmin: bool = False,
    org_roles: dict[str, str] | None = None,
    group_roles: dict[str, str] | None = None,
) -> tuple[str, str]:
    """Create a new CKAN user, optionally promote to sysadmin, and assign organization/group roles."""
    clean_name, clean_email = validate_username_and_email(name, email)
    if model.User.by_name(clean_name) is not None:
        raise PermissionFormError(tk._("Username '{name}' already exists.").format(name=clean_name))

    existing_email = (
        model.Session.query(model.User)
        .filter(func.lower(model.User.email) == clean_email.lower(), model.User.state == "active")
        .first()
    )
    if existing_email is not None:
        raise PermissionFormError(
            tk._("Email '{email}' is already used by active user '{user}'.").format(
                email=clean_email, user=existing_email.name
            )
        )

    chosen_password = password.strip()
    if chosen_password and len(chosen_password) < MIN_PASSWORD_LEN:
        raise PermissionFormError(
            tk._("Password must be at least {n} characters long.").format(n=MIN_PASSWORD_LEN)
        )
    if not chosen_password:
        chosen_password = secrets.token_urlsafe(15)

    payload: dict[str, Any] = {
        "name": clean_name,
        "email": clean_email,
        "password": chosen_password,
    }
    if fullname.strip():
        payload["fullname"] = fullname.strip()
    if about.strip():
        payload["about"] = about.strip()

    _action(acting_user, "user_create", payload)
    user = model.User.by_name(clean_name)
    if user is None:
        raise PermissionFormError(tk._("Could not create user."))

    if sysadmin:
        user.sysadmin = True
        model.Session.commit()

    if org_roles:
        _apply_user_unit_roles(acting_user, user, "organization", ORG_ROLES, org_roles)
    if group_roles:
        _apply_user_unit_roles(acting_user, user, "group", GROUP_ROLES, group_roles)

    return clean_name, chosen_password


def update_user_permissions(
    acting_user: str,
    *,
    username: str,
    sysadmin: bool,
    org_roles: dict[str, str],
    group_roles: dict[str, str],
) -> list[str]:
    """Update a user's sysadmin flag and all organization/group memberships at once."""
    user = model.User.by_name(username)
    if user is None:
        raise PermissionFormError(tk._("User '{name}' not found.").format(name=username))
    if user.state != "active":
        raise PermissionFormError(tk._("Activate this user before changing their permissions."))
    if user.name == acting_user and user.sysadmin and not sysadmin:
        raise PermissionFormError(tk._("You cannot remove sysadmin rights from your own account."))

    changes: list[str] = []
    if bool(user.sysadmin) != bool(sysadmin):
        user.sysadmin = bool(sysadmin)
        model.Session.commit()
        changes.append("sysadmin: on" if sysadmin else "sysadmin: off")

    changes.extend(_apply_user_unit_roles(acting_user, user, "organization", ORG_ROLES, org_roles))
    changes.extend(_apply_user_unit_roles(acting_user, user, "group", GROUP_ROLES, group_roles))
    return changes


def reset_user_password(acting_user: str, *, username: str, new_password: str = "") -> str:
    """Reset a user's password (random if blank) and return the new clear-text password."""
    user = model.User.by_name(username)
    if user is None:
        raise PermissionFormError(tk._("User '{name}' not found.").format(name=username))
    chosen = new_password.strip()
    if chosen and len(chosen) < MIN_PASSWORD_LEN:
        raise PermissionFormError(
            tk._("Password must be at least {n} characters long.").format(n=MIN_PASSWORD_LEN)
        )
    if not chosen:
        chosen = secrets.token_urlsafe(15)
    user.password = chosen
    model.Session.commit()
    return chosen


def set_user_state(acting_user: str, *, username: str, active: bool) -> None:
    """Deactivate (soft-delete) or reactivate a user account."""
    user = model.User.by_name(username)
    if user is None:
        raise PermissionFormError(tk._("User '{name}' not found.").format(name=username))
    if user.name == acting_user and not active:
        raise PermissionFormError(tk._("You cannot deactivate your own account."))

    if active:
        if user.email:
            clash = (
                model.Session.query(model.User)
                .filter(
                    func.lower(model.User.email) == user.email.lower(),
                    model.User.state == "active",
                    model.User.id != user.id,
                )
                .first()
            )
            if clash is not None:
                raise PermissionFormError(
                    tk._("Cannot activate: email '{email}' is already used by '{user}'.").format(
                        email=user.email, user=clash.name
                    )
                )
        user.activate()
        model.Session.commit()
    else:
        user.sysadmin = False
        model.Session.commit()
        _action(acting_user, "user_delete", {"id": user.name})


def update_unit_members(
    acting_user: str,
    *,
    kind: str,
    unit_name: str,
    member_roles: dict[str, str],
    add_username: str = "",
    add_role: str = "",
) -> list[str]:
    """Update roles of members in a single organization or group, and optionally add a new member."""
    if kind not in ("organization", "group"):
        raise PermissionFormError(tk._("Invalid unit type."))
    valid_roles = ORG_ROLES if kind == "organization" else GROUP_ROLES
    is_org = kind == "organization"

    unit = model.Group.get(unit_name)
    if unit is None or unit.state != "active" or bool(unit.is_organization) != is_org:
        raise PermissionFormError(tk._("Unit '{name}' not found.").format(name=unit_name))

    rows = (
        model.Session.query(model.User.name, model.Member.capacity)
        .join(model.Member, model.Member.table_id == model.User.id)
        .filter(
            model.Member.group_id == unit.id,
            model.Member.table_name == "user",
            model.Member.state == "active",
            model.User.state == "active",
        )
        .all()
    )
    current = {uname: (cap or "").lower() for uname, cap in rows}
    changes: list[str] = []

    for username, role in sorted(member_roles.items()):
        if username not in current:
            continue
        clean_role = role.strip().lower() if role else ""
        if clean_role and clean_role not in valid_roles:
            raise PermissionFormError(tk._("Invalid role '{role}'.").format(role=clean_role))
        if clean_role and clean_role != current[username]:
            _action(acting_user, f"{kind}_member_create", {"id": unit_name, "username": username, "role": clean_role})
            changes.append(f"{username}: {clean_role}")
        elif not clean_role:
            _action(acting_user, f"{kind}_member_delete", {"id": unit_name, "username": username})
            changes.append(f"{username}: removed")

    clean_add_user = add_username.strip()
    clean_add_role = add_role.strip().lower()
    if clean_add_user:
        target_user = model.User.by_name(clean_add_user)
        if target_user is None or target_user.state != "active":
            raise PermissionFormError(tk._("Active user '{name}' not found.").format(name=clean_add_user))
        if clean_add_role not in valid_roles:
            raise PermissionFormError(tk._("Invalid role '{role}'.").format(role=clean_add_role))
        if current.get(clean_add_user) != clean_add_role:
            _action(
                acting_user,
                f"{kind}_member_create",
                {"id": unit_name, "username": clean_add_user, "role": clean_add_role},
            )
            changes.append(f"{clean_add_user}: {clean_add_role}")

    return changes
