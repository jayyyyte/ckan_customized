"""Blueprint `/ckan-admin/permissions`: sysadmin UI for user roles, units, and access matrix."""
from __future__ import annotations

from typing import Any

from flask import Blueprint, Response
from flask import session as flask_session

import ckan.plugins.toolkit as tk

from ckanext.lakehouse.permissions import service

permissions = Blueprint("lakehouse_permissions", __name__, url_prefix="/ckan-admin/permissions")

TABS = ("users", "units", "matrix")
FILTERS = ("all", "sysadmin", "unassigned", "inactive")
_CRED_SESSION_KEY = "_lh_temp_credentials"


@permissions.before_request
def _require_sysadmin() -> None:
    try:
        tk.check_access("sysadmin", {"user": tk.current_user.name, "auth_user_obj": tk.current_user})
    except tk.NotAuthorized:
        tk.abort(403, tk._("Not authorized to see this page"))


def _extract_prefixed(form: Any, prefix: str) -> dict[str, str]:
    return {key[len(prefix):]: str(form.get(key) or "").strip() for key in form if key.startswith(prefix)}


def _render_index(
    *,
    tab: str = "users",
    q: str = "",
    role_filter: str = "all",
    selected_user: str = "",
    new_user: bool = False,
    form_data: dict[str, Any] | None = None,
    selected_kind: str = "organization",
    selected_unit: str = "",
    credentials: dict[str, str] | None = None,
) -> str:
    active_tab = tab if tab in TABS else "users"
    active_filter = role_filter if role_filter in FILTERS else "all"
    overview = service.load_overview(q=q, role_filter=active_filter)

    user_obj: service.UserRow | None = None
    if not new_user:
        by_name = {u.name: u for u in overview.all_users}
        if selected_user and selected_user in by_name:
            user_obj = by_name[selected_user]
        elif overview.users:
            user_obj = overview.users[0]

    unit_obj: service.UnitInfo | None = None
    org_by_name = {o.name: o for o in overview.organizations}
    grp_by_name = {g.name: g for g in overview.groups}
    if selected_kind == "group" and selected_unit in grp_by_name:
        unit_obj = grp_by_name[selected_unit]
    elif selected_unit in org_by_name:
        unit_obj = org_by_name[selected_unit]
        selected_kind = "organization"
    elif selected_unit in grp_by_name:
        unit_obj = grp_by_name[selected_unit]
        selected_kind = "group"
    elif overview.organizations:
        unit_obj = overview.organizations[0]
        selected_kind = "organization"
    elif overview.groups:
        unit_obj = overview.groups[0]
        selected_kind = "group"

    available_to_add: list[service.UserRow] = []
    if unit_obj is not None:
        existing_members = {m.username for m in unit_obj.members}
        available_to_add = [u for u in overview.all_users if u.is_active and u.name not in existing_members]

    if credentials is None:
        credentials = flask_session.pop(_CRED_SESSION_KEY, None)

    return tk.render(
        "lakehouse/permissions/index.html",
        {
            "tab": active_tab,
            "q": q,
            "role_filter": active_filter,
            "overview": overview,
            "selected_user": user_obj,
            "new_user": new_user,
            "form_data": form_data or {},
            "selected_kind": selected_kind,
            "selected_unit": unit_obj,
            "available_to_add": available_to_add,
            "credentials": credentials,
        },
    )


def index() -> str:
    args = tk.request.args
    return _render_index(
        tab=args.get("tab", "users"),
        q=args.get("q", ""),
        role_filter=args.get("filter", "all"),
        selected_user=args.get("user", ""),
        new_user=(args.get("new") == "1"),
        selected_kind=args.get("kind", "organization"),
        selected_unit=args.get("unit", ""),
    )


def create_user() -> str | Response:
    form = tk.request.form
    name = (form.get("name") or "").strip()
    fullname = (form.get("fullname") or "").strip()
    email = (form.get("email") or "").strip()
    about = (form.get("about") or "").strip()
    password = (form.get("password") or "").strip()
    sysadmin = form.get("sysadmin") == "1"
    org_roles = _extract_prefixed(form, "org_role__")
    group_roles = _extract_prefixed(form, "group_role__")

    try:
        username, final_password = service.create_user_with_roles(
            tk.current_user.name,
            name=name,
            email=email,
            fullname=fullname,
            about=about,
            password=password,
            sysadmin=sysadmin,
            org_roles=org_roles,
            group_roles=group_roles,
        )
    except service.PermissionFormError as err:
        tk.h.flash_error(str(err))
        return _render_index(
            tab="users",
            new_user=True,
            form_data={
                "name": name,
                "fullname": fullname,
                "email": email,
                "about": about,
                "sysadmin": sysadmin,
                "org_roles": org_roles,
                "group_roles": group_roles,
            },
        )

    flask_session[_CRED_SESSION_KEY] = {
        "username": username,
        "email": email,
        "password": final_password,
        "mode": "created",
    }
    tk.h.flash_success(tk._("Created user '{user}' and assigned permissions.").format(user=username))
    return tk.redirect_to("lakehouse_permissions.index", tab="users", user=username)


def update_user(username: str) -> Response:
    form = tk.request.form
    sysadmin = form.get("sysadmin") == "1"
    org_roles = _extract_prefixed(form, "org_role__")
    group_roles = _extract_prefixed(form, "group_role__")
    return_tab = form.get("return_tab") or "users"
    q = form.get("q") or ""
    role_filter = form.get("filter") or "all"

    try:
        changes = service.update_user_permissions(
            tk.current_user.name,
            username=username,
            sysadmin=sysadmin,
            org_roles=org_roles,
            group_roles=group_roles,
        )
        if changes:
            tk.h.flash_success(
                tk._("Updated permissions for '{user}' ({n} changes).").format(user=username, n=len(changes))
            )
        else:
            tk.h.flash_notice(tk._("No permission changes for '{user}'.").format(user=username))
    except service.PermissionFormError as err:
        tk.h.flash_error(str(err))

    return tk.redirect_to("lakehouse_permissions.index", tab=return_tab, user=username, q=q or None, filter=role_filter)


def reset_password(username: str) -> Response:
    new_password = (tk.request.form.get("new_password") or "").strip()
    try:
        final_password = service.reset_user_password(
            tk.current_user.name,
            username=username,
            new_password=new_password,
        )
        flask_session[_CRED_SESSION_KEY] = {
            "username": username,
            "password": final_password,
            "mode": "reset",
        }
        tk.h.flash_success(tk._("Reset password for '{user}'.").format(user=username))
    except service.PermissionFormError as err:
        tk.h.flash_error(str(err))

    return tk.redirect_to("lakehouse_permissions.index", tab="users", user=username)


def user_state(username: str) -> Response:
    active = tk.request.form.get("active") == "1"
    try:
        service.set_user_state(tk.current_user.name, username=username, active=active)
        if active:
            tk.h.flash_success(tk._("Reactivated user '{user}'.").format(user=username))
        else:
            tk.h.flash_success(tk._("Deactivated user '{user}' and removed their active unit memberships.").format(
                user=username
            ))
    except service.PermissionFormError as err:
        tk.h.flash_error(str(err))

    return tk.redirect_to("lakehouse_permissions.index", tab="users", user=username)


def update_unit(kind: str, unit_name: str) -> Response:
    form = tk.request.form
    member_roles = _extract_prefixed(form, "member_role__")
    add_username = (form.get("add_username") or "").strip()
    add_role = (form.get("add_role") or "").strip()

    try:
        changes = service.update_unit_members(
            tk.current_user.name,
            kind=kind,
            unit_name=unit_name,
            member_roles=member_roles,
            add_username=add_username,
            add_role=add_role,
        )
        if changes:
            tk.h.flash_success(
                tk._("Updated members of '{unit}' ({n} changes).").format(unit=unit_name, n=len(changes))
            )
        else:
            tk.h.flash_notice(tk._("No member changes for '{unit}'.").format(unit=unit_name))
    except service.PermissionFormError as err:
        tk.h.flash_error(str(err))

    return tk.redirect_to("lakehouse_permissions.index", tab="units", kind=kind, unit=unit_name)


def export_matrix_csv() -> Response:
    args = tk.request.args
    q = (args.get("q") or "").strip()
    role_filter = args.get("filter") or "all"
    active_filter = role_filter if role_filter in FILTERS else "all"
    overview = service.load_overview(q=q, role_filter=active_filter)
    return Response(
        service.matrix_csv(overview),
        mimetype="text/csv; charset=utf-8",
        headers={
            "Content-Disposition": 'attachment; filename="ckan-permissions-matrix.csv"',
            "Cache-Control": "no-store",
        },
    )


permissions.add_url_rule("/", view_func=index, endpoint="index", methods=["GET"], strict_slashes=False)
permissions.add_url_rule("/matrix.csv", view_func=export_matrix_csv, endpoint="export_matrix_csv", methods=["GET"])
permissions.add_url_rule("/users/new", view_func=create_user, endpoint="create_user", methods=["POST"])
permissions.add_url_rule("/users/<username>/roles", view_func=update_user, endpoint="update_user", methods=["POST"])
permissions.add_url_rule(
    "/users/<username>/password", view_func=reset_password, endpoint="reset_password", methods=["POST"]
)
permissions.add_url_rule("/users/<username>/state", view_func=user_state, endpoint="user_state", methods=["POST"])
permissions.add_url_rule(
    "/units/<kind>/<unit_name>", view_func=update_unit, endpoint="update_unit", methods=["POST"]
)
