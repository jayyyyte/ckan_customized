"""Tests through CKAN (database, Solr): bootstrap, OpenMetadata sync, the dataset tab.

Run in CI (.github/workflows/lakehouse.yml) or wherever `ckan_test` exists:
    pytest --ckan-ini=test.ini ckanext/lakehouse/tests/test_app.py
OpenMetadata is replaced by FakeClient, serving tools/openmetadata/sample-snapshot.json.
"""
from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Any

import pytest

import ckan.model as model
import ckan.plugins.toolkit as tk
from ckan.tests import factories

from ckanext.lakehouse import bootstrap
from ckanext.lakehouse.om import mapping, panel, scaffold
from ckanext.lakehouse.om.client import OMClient, OMError
from ckanext.lakehouse.om.sync import Syncer, load_rules

pytestmark = [
    pytest.mark.ckan_config("ckan.plugins", "evntheme lakehouse activity tracking"),
    pytest.mark.ckan_config("ckanext.lakehouse.om.include", "trino_lakehouse.iceberg_curated.*"),
    pytest.mark.ckan_config("ckanext.lakehouse.om.cache_ttl", "0"),
    # The portal's locale; test-core.ini says en.
    pytest.mark.ckan_config("ckan.locale_default", "vi"),
    pytest.mark.usefixtures("with_plugins", "clean_db", "clean_index", "lakehouse_db"),
]

SAMPLE = json.loads((Path(__file__).parents[4] / "tools" / "openmetadata" / "sample-snapshot.json").read_text("utf-8"))
CUR = "trino_lakehouse.iceberg_curated"
OUTAGE = f"{CUR}.van_hanh.curated_outage_summary"
OUTAGE_NAME = mapping.dataset_name(OUTAGE)
DEMO = (Path(bootstrap.__file__).parent / "demo" / "portal.yaml").read_text("utf-8")


class FakeClient(OMClient):
    """OMClient answering from the sample snapshot; `down` makes every call fail."""

    def __init__(self, snapshot: dict[str, Any] | None = None) -> None:
        super().__init__("http://om.test")
        self.snapshot = copy.deepcopy(snapshot or SAMPLE)
        self.down = False

    def _check(self) -> None:
        if self.down:
            raise OMError("cannot reach OpenMetadata: ConnectionError")

    def iter_tables(self, schema_fqn=None):
        self._check()
        yield from self.snapshot["tables"]

    def table(self, fqn):
        self._check()
        for table in self.snapshot["tables"]:
            if table["fullyQualifiedName"] == fqn:
                return table
        raise OMError("not found", 404)

    def profile(self, fqn):
        self._check()
        return self.snapshot["profiles"].get(fqn)

    def lineage(self, fqn, depth=1):
        table = self.table(fqn)
        return {"entity": {"id": table["id"]}, **self.snapshot["lineage"].get(fqn, {})}

    def test_cases(self, fqn, limit=50):
        self._check()
        return self.snapshot["testCases"].get(fqn, [])

    def user(self, name):
        self._check()
        return next((u for u in self.snapshot["users"] if u["name"] == name), None)

    def iter_teams(self):
        self._check()
        yield from self.snapshot["teams"]

    def iter_domains(self):
        self._check()
        yield from self.snapshot["domains"]

    def iter_users(self):
        self._check()
        yield from self.snapshot["users"]


@pytest.fixture
def lakehouse_db(clean_db, migrate_db_for):
    for plugin in ("activity", "tracking", "evntheme"):
        migrate_db_for(plugin)


@pytest.fixture
def portal():
    """The demo structure, created by the bootstrap as a sysadmin."""
    admin = factories.Sysadmin(name="admin")
    job = bootstrap.Bootstrap(bootstrap.load(DEMO), admin["name"])
    return job.run()


def _sync(client: FakeClient, **kwargs: Any):
    return Syncer(client, load_rules(), "om-sync", **kwargs).run()


# --- bootstrap ---------------------------------------------------------------------------


def test_bootstrap_creates_users_and_roles(portal):
    assert len(portal.credentials) == 9
    assert model.User.by_name("quantri-portal").sysadmin
    assert not model.User.by_name("om-sync").sysadmin
    members = tk.get_action("member_list")({"ignore_auth": True}, {"id": "evnnpc", "object_type": "user",
                                                                   "capacity": "editor"})
    assert [model.User.get(m[0]).name for m in members] == ["npc-bientap"]
    org = tk.get_action("organization_show")({"ignore_auth": True}, {"id": "ban-kinh-doanh"})
    extras = {e["key"]: json.loads(e["value"]) for e in org["extras"] if e["key"].startswith("om_")}
    assert extras == {"om_teams": ["KinhDoanh"], "om_fqn_patterns": [f"{CUR}.kinh_doanh.*"]}


def test_bootstrap_runs_again_without_changes(portal):
    again = bootstrap.Bootstrap(bootstrap.load(DEMO), "admin").run()
    assert not (again.created or again.updated or again.memberships or again.removed or again.credentials)


def test_bootstrap_prune_removes_undeclared_members(portal):
    stranger = factories.User()
    tk.get_action("organization_member_create")({"ignore_auth": True},
                                                {"id": "evnnpc", "username": stranger["name"], "role": "editor"})
    kept = bootstrap.Bootstrap(bootstrap.load(DEMO), "admin").run()
    assert not kept.removed
    pruned = bootstrap.Bootstrap(bootstrap.load(DEMO), "admin").run(prune=True)
    assert pruned.removed == [f"organization evnnpc: {stranger['name']}"]


@pytest.mark.parametrize("user,action,allowed", [
    ("npc-bientap", "package_create", True),
    ("npc-quantri", "organization_member_create", True),
    ("npc-bientap", "organization_member_create", False),
    ("nguoidung-xem", "package_create", False),
])
def test_declared_roles_grant_the_expected_rights(portal, user, action, allowed):
    data = {"owner_org": "evnnpc"} if action == "package_create" else {"id": "evnnpc"}
    try:
        tk.check_access(action, {"user": user}, data)
        granted = True
    except tk.NotAuthorized:
        granted = False
    assert granted is allowed


# --- sync ---------------------------------------------------------------------------------


def test_sync_creates_private_datasets_in_the_right_places(portal):
    report = _sync(FakeClient())
    assert len(report.created) == 5 and not report.errors
    assert [fqn for fqn, _ in report.skipped] == [f"{CUR}.tai_chinh.fact_inventory"]
    pkg = tk.get_action("package_show")({"ignore_auth": True}, {"id": OUTAGE_NAME})
    assert pkg["private"] is True
    assert pkg["organization"]["name"] == "trung-tam-dieu-do-htd-qg"
    # Groups set although om-sync is not a member of the group (gotchas 28).
    assert [g["name"] for g in pkg["groups"]] == ["ky-thuat-an-toan"]
    assert pkg["resources"] == []  # om.trino_jdbc_url not set: no Trino link
    # Activities of private datasets are filtered by the caller's permissions: ask as a sysadmin.
    activity_users = {a["user_id"] for a in tk.get_action("package_activity_list")(
        {"user": "admin"}, {"id": pkg["id"]})}
    assert activity_users == {model.User.by_name("om-sync").id}


@pytest.mark.ckan_config("ckanext.lakehouse.om.trino_jdbc_url", "jdbc:trino://trino.test:30800")
def test_second_sync_changes_nothing_and_keeps_hand_edits(portal):
    _sync(FakeClient())
    tk.get_action("package_patch")({"user": "admin"}, {
        "id": OUTAGE_NAME, "private": False,
        "tags": [{"name": "DataLayer.Gold"}, {"name": "do-tin-cay"}],
    })
    report = _sync(FakeClient())
    assert report.unchanged == 5 and not report.updated
    pkg = tk.get_action("package_show")({"ignore_auth": True}, {"id": OUTAGE_NAME})
    assert pkg["private"] is False and {t["name"] for t in pkg["tags"]} == {"DataLayer.Gold", "do-tin-cay"}
    assert pkg["resources"][0]["url"] == "jdbc:trino://trino.test:30800/iceberg_curated/van_hanh"


def test_table_leaving_scope_is_deleted_then_restored(portal):
    client = FakeClient()
    _sync(client)
    gone = [t for t in client.snapshot["tables"] if t["fullyQualifiedName"] == OUTAGE]
    client.snapshot["tables"].remove(gone[0])
    assert _sync(client).removed == [OUTAGE_NAME]
    assert model.Package.get(OUTAGE_NAME).state == "deleted"
    client.snapshot["tables"].append(gone[0])
    report = _sync(client)
    assert report.updated == [f"{OUTAGE_NAME} (state)"]
    assert model.Package.get(OUTAGE_NAME).state == "active"


def test_nothing_in_scope_removes_nothing(portal):
    client = FakeClient()
    _sync(client)
    client.snapshot["tables"] = []
    report = _sync(client)
    assert not report.removed and "not removing them" in report.notes[0]


def test_unreachable_openmetadata_changes_nothing(portal):
    client = FakeClient()
    client.down = True
    with pytest.raises(OMError):
        _sync(client)
    assert model.Session.query(model.Package).count() == 0


def test_name_taken_by_a_hand_made_dataset_is_skipped(portal):
    factories.Dataset(name=OUTAGE_NAME, owner_org=model.Group.get("evnnpc").id)
    report = _sync(FakeClient())
    assert (OUTAGE, f"dataset name {OUTAGE_NAME!r} is taken by a dataset that does not come from OpenMetadata") \
        in report.skipped


# --- scaffold: OpenMetadata teams and domains -> organizations, groups, roles --------------


def _scaffold_and_bootstrap(client: FakeClient) -> bootstrap.Result:
    draft = scaffold.build(list(client.iter_teams()), list(client.iter_domains()), list(client.iter_users()),
                           scaffold.ckan_state(load_rules()))
    return bootstrap.Bootstrap(bootstrap.load(scaffold.render(draft)), "admin").run()


def _can(user: str, action: str, data: dict[str, Any]) -> bool:
    try:
        tk.check_access(action, {"user": user}, data)
    except tk.NotAuthorized:
        return False
    return True


def test_scaffolded_structure_gives_openmetadata_teams_their_rights():
    factories.Sysadmin(name="admin")
    factories.User(name="om-sync")
    client = FakeClient()
    created = _scaffold_and_bootstrap(client)
    assert "organization dieu-do" in created.created and "group dich-vu-khach-hang" in created.created

    report = _sync(client)
    # fact_inventory, owned by team DataPlatform, now has an organization too.
    assert len(report.created) == 6 and not report.skipped and not report.errors

    def show(fqn: str) -> dict[str, Any]:
        return tk.get_action("package_show")({"ignore_auth": True}, {"id": mapping.dataset_name(fqn)})

    outage = show(OUTAGE)
    grid = show(f"{CUR}.van_hanh.grid_loss_monthly")      # owned by the person nguyen.van.an (team DieuDo)
    customer = show(f"{CUR}.kinh_doanh.dim_customer")     # subdomain KinhDoanh.DichVuKhachHang
    assert outage["organization"]["name"] == grid["organization"]["name"] == "dieu-do"
    assert [g["name"] for g in outage["groups"]] == ["van-hanh"]
    assert [g["name"] for g in customer["groups"]] == ["dich-vu-khach-hang"]

    # Team owner -> admin, member -> reads the private dataset only, other teams -> nothing.
    assert _can("nguyen-van-an", "package_update", {"id": outage["id"]})
    assert _can("do-thi-hoa", "package_show", {"id": outage["id"]})
    assert not _can("do-thi-hoa", "package_update", {"id": outage["id"]})
    assert not _can("tran-thi-binh", "package_show", {"id": outage["id"]})
    assert _can("tran-thi-binh", "package_update", {"id": customer["id"]})
    # DataSteward as the team's default role -> editor.
    substation = show(f"{CUR}.ky_thuat.dim_substation")
    assert _can("pham-thi-dung", "package_update", {"id": substation["id"]})
    # Domain owner -> admin of the group.
    assert _can("tran-thi-binh", "group_member_create", {"id": "mien-kinh-doanh"})


def test_scaffold_again_changes_nothing():
    factories.Sysadmin(name="admin")
    client = FakeClient()
    _scaffold_and_bootstrap(client)
    again = _scaffold_and_bootstrap(client)
    assert not (again.created or again.updated or again.memberships or again.removed), again


# --- dataset page ---------------------------------------------------------------------------


@pytest.fixture
def synced(portal, monkeypatch):
    client = FakeClient()
    _sync(client)
    monkeypatch.setattr(panel, "_client", lambda: client)
    monkeypatch.setattr("ckanext.lakehouse.config.om_enabled", lambda: True)
    return client


def _login_headers(username: str) -> dict[str, str]:
    token = tk.get_action("api_token_create")({"ignore_auth": True, "user": username},
                                             {"user": username, "name": "test"})["token"]
    return {"Authorization": token}


def test_tab_is_listed_and_renders_inline(app, synced):
    response = app.get(f"/dataset/{OUTAGE_NAME}", query_string={"tab": "openmetadata"},
                       headers=_login_headers("ktsx-bientap"))
    body = response.get_data(as_text=True)
    assert 'id="tab-openmetadata"' in body and "Danh mục kỹ thuật" in body
    assert "province_in_code_list" in body           # failed test, listed first
    assert "airflow_lakehouse.curated_outage_summary" in body
    assert "<dt>om_columns</dt>" not in body         # bookkeeping extras stay out of the sidebar
    assert "<dt>Bảng nguồn</dt>" in body
    assert f"/dataset/{mapping.dataset_name(CUR + '.van_hanh.grid_loss_monthly')}" in body


def test_fragment_respects_dataset_permissions(app, synced):
    url = f"/dataset/{OUTAGE_NAME}/openmetadata"
    assert app.get(url, status=403).status_code == 403                                   # private
    assert app.get(url, headers=_login_headers("nguoidung-xem"), status=403).status_code == 403
    body = app.get(url, headers=_login_headers("a0-thanhvien")).get_data(as_text=True)  # org member
    assert "saidi_minutes" in body


def test_fragment_falls_back_to_synced_columns(app, synced):
    synced.down = True
    body = app.get(f"/dataset/{OUTAGE_NAME}/openmetadata",
                   headers=_login_headers("a0-thanhvien")).get_data(as_text=True)
    assert "Hiện không kết nối được OpenMetadata" in body
    assert "saidi_minutes" in body and "province_in_code_list" not in body


def test_hand_made_dataset_has_no_tab(app, portal):
    pkg = factories.Dataset(owner_org=model.Group.get("evnnpc").id)
    body = app.get(f"/dataset/{pkg['name']}").get_data(as_text=True)
    assert 'id="tab-openmetadata"' not in body
    app.get(f"/dataset/{pkg['name']}/openmetadata", status=404)



# --- sysadmin permissions UI (/ckan-admin/permissions) --------------------------------------


def test_permissions_ui_requires_sysadmin(app, synced):
    url = "/ckan-admin/permissions"
    assert app.get(url, status=403).status_code == 403
    assert app.get(url, headers=_login_headers("npc-quantri"), status=403).status_code == 403

    # Sysadmin renders users tab, units tab, and matrix tab, plus the link in the header menu.
    body_users = app.get(url, query_string={"user": "a0-thanhvien"},
                         headers=_login_headers("quantri-portal")).get_data(as_text=True)
    assert "Phân quyền người dùng" in body_users
    assert "Trung tâm Điều độ Hệ thống điện Quốc gia" in body_users

    body_units = app.get(url, query_string={"tab": "units", "kind": "organization", "unit": "evnnpc"},
                         headers=_login_headers("quantri-portal")).get_data(as_text=True)
    assert "npc-quantri" in body_units and "npc-bientap" in body_units

    body_matrix = app.get(url, query_string={"tab": "matrix"},
                          headers=_login_headers("quantri-portal")).get_data(as_text=True)
    assert "Ma trận phân quyền" in body_matrix


def test_permissions_ui_create_user_update_roles_reset_password_and_lock(app, synced):
    headers = _login_headers("quantri-portal")

    # 1. Create a new user with editor role in EVNNPC and member role in domain ky-thuat-an-toan.
    res = app.post(
        "/ckan-admin/permissions/users/new",
        data={
            "name": "canbo-moi",
            "fullname": "Cán bộ mới",
            "email": "canbo-moi@evn.example",
            "about": "Thử nghiệm phân quyền",
            "org_role__evnnpc": "editor",
            "group_role__ky-thuat-an-toan": "member",
        },
        headers=headers,
        follow_redirects=True,
    )
    body = res.get_data(as_text=True)
    assert res.status_code == 200
    assert 'id="lh-cred-password"' in body  # one-time generated password shown once
    assert _can("canbo-moi", "package_create", {"owner_org": "evnnpc"})
    assert not _can("canbo-moi", "package_show", {"id": OUTAGE_NAME})  # private dataset of A0

    # Reloading does not show the one-time password again.
    reload_body = app.get("/ckan-admin/permissions", query_string={"user": "canbo-moi"},
                          headers=headers).get_data(as_text=True)
    assert 'id="lh-cred-password"' not in reload_body

    # 2. Grant member role in A0 -> user can now read A0's private dataset.
    app.post(
        "/ckan-admin/permissions/users/canbo-moi/roles",
        data={
            "org_role__evnnpc": "editor",
            "org_role__trung-tam-dieu-do-htd-qg": "member",
            "group_role__ky-thuat-an-toan": "member",
        },
        headers=headers,
        follow_redirects=True,
    )
    assert _can("canbo-moi", "package_show", {"id": OUTAGE_NAME})
    assert not _can("canbo-moi", "package_update", {"id": OUTAGE_NAME})

    # 3. Reset password with a custom password and verify it validates.
    pw_res = app.post(
        "/ckan-admin/permissions/users/canbo-moi/password",
        data={"new_password": "NewSecretPassword123"},
        headers=headers,
        follow_redirects=True,
    )
    assert "NewSecretPassword123" in pw_res.get_data(as_text=True)
    assert model.User.by_name("canbo-moi").validate_password("NewSecretPassword123")

    # 4. Self-protection: quantri-portal cannot demote or lock themselves.
    app.post(
        "/ckan-admin/permissions/users/quantri-portal/roles",
        data={},
        headers=headers,
        follow_redirects=True,
    )
    assert model.User.by_name("quantri-portal").sysadmin is True

    app.post(
        "/ckan-admin/permissions/users/quantri-portal/state",
        data={"active": "0"},
        headers=headers,
        follow_redirects=True,
    )
    assert model.User.by_name("quantri-portal").state == "active"

    # 5. Lock and reactivate canbo-moi.
    app.post(
        "/ckan-admin/permissions/users/canbo-moi/state",
        data={"active": "0"},
        headers=headers,
        follow_redirects=True,
    )
    assert model.User.by_name("canbo-moi").state == "deleted"
    assert not _can("canbo-moi", "package_create", {"owner_org": "evnnpc"})

    app.post(
        "/ckan-admin/permissions/users/canbo-moi/state",
        data={"active": "1"},
        headers=headers,
        follow_redirects=True,
    )
    assert model.User.by_name("canbo-moi").state == "active"

    # 6. Manage members from the unit tab (add canbo-moi to A0 as editor, remove a0-thanhvien).
    app.post(
        "/ckan-admin/permissions/units/organization/trung-tam-dieu-do-htd-qg",
        data={
            "member_role__ktsx-bientap": "editor",
            "member_role__a0-thanhvien": "",
            "add_username": "canbo-moi",
            "add_role": "editor",
        },
        headers=headers,
        follow_redirects=True,
    )
    assert _can("canbo-moi", "package_update", {"id": OUTAGE_NAME})
    assert not _can("a0-thanhvien", "package_show", {"id": OUTAGE_NAME})
