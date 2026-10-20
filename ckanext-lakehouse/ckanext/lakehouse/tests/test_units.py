"""Tests without a database: mapping, merge rules, client, panel shaping, bootstrap validation, scaffold.

    python -m pytest -o addopts="" -p no:ckan -p no:ckan_fixtures ckanext/lakehouse/tests/test_units.py
"""
from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Any

import pytest

from ckanext.lakehouse import bootstrap
from ckanext.lakehouse.om import mapping, panel, scaffold
from ckanext.lakehouse.om.client import OMClient, OMError

SAMPLE = Path(__file__).parents[4] / "tools" / "openmetadata" / "sample-snapshot.json"
CUR = "trino_lakehouse.iceberg_curated"
OUTAGE = f"{CUR}.van_hanh.curated_outage_summary"


@pytest.fixture(scope="module")
def snapshot() -> dict[str, Any]:
    return json.loads(SAMPLE.read_text("utf-8"))


def _table(snapshot: dict[str, Any], fqn: str) -> dict[str, Any]:
    return copy.deepcopy(next(t for t in snapshot["tables"] if t["fullyQualifiedName"] == fqn))


@pytest.fixture
def rules() -> mapping.Rules:
    return mapping.Rules(
        include=[f"{CUR}.*"], team_orgs={"dieudo": "a0", "kinhdoanh": "ban-kinh-doanh"},
        fqn_orgs=[(f"{CUR}.van_hanh.*", "a0")], domain_groups={"vanhanh": "ky-thuat-an-toan"},
        ui_url="http://om.test", trino_jdbc_url="jdbc:trino://trino.test:30800",
    )


# --- mapping ------------------------------------------------------------------------------


def test_split_fqn_keeps_quoted_dots():
    assert mapping.split_fqn('svc.db."my.schema".t') == ["svc", "db", "my.schema", "t"]


@pytest.mark.parametrize("fqn,expected", [
    ("svc.db.schema.Orders", "om-svc-db-schema-orders"),
    ('svc.db."a b".t', "om-svc-db-a-b-t"),
])
def test_dataset_name(fqn, expected):
    assert mapping.dataset_name(fqn) == expected


def test_long_dataset_name_is_cut_with_a_stable_digest():
    fqn = "svc.db.schema." + "x" * 200
    name = mapping.dataset_name(fqn)
    assert len(name) <= 100 and name == mapping.dataset_name(fqn) and name != mapping.dataset_name(fqn + "y")


def test_scope(snapshot, rules):
    assert mapping.in_scope(_table(snapshot, OUTAGE), rules)
    assert not mapping.in_scope(_table(snapshot, "trino_lakehouse.iceberg_raw.ingest.raw_outage_events"), rules)
    rules.require_tags = ["Tier.Tier1"]
    assert mapping.in_scope(_table(snapshot, OUTAGE), rules)
    assert not mapping.in_scope(_table(snapshot, f"{CUR}.kinh_doanh.fact_electricity_sales"), rules)
    rules.require_tags, rules.exclude = [], [f"{CUR}.van_hanh.*"]
    assert not mapping.in_scope(_table(snapshot, OUTAGE), rules)


def test_schema_prefixes():
    assert mapping.schema_prefixes(["s.d.a.*", "s.d.b.t", "s.d.a.x"]) == ["s.d.a", "s.d.b"]
    assert mapping.schema_prefixes(["s.d.*"]) is None
    assert mapping.schema_prefixes(["s.*.a.*"]) is None


def test_org_resolution_order(snapshot, rules):
    assert mapping.resolve_org(_table(snapshot, OUTAGE), rules) == "a0"  # owner team
    grid = _table(snapshot, f"{CUR}.van_hanh.grid_loss_monthly")       # user owner -> FQN pattern
    assert mapping.resolve_org(grid, rules) == "a0"
    inventory = _table(snapshot, f"{CUR}.tai_chinh.fact_inventory")   # nobody claims it
    assert mapping.resolve_org(inventory, rules) is None
    rules.default_org = "fallback"
    assert mapping.resolve_org(inventory, rules) == "fallback"


def test_person_owner_stands_for_their_team(snapshot, rules):
    grid = _table(snapshot, f"{CUR}.van_hanh.grid_loss_monthly")  # owner: nguyen.van.an
    rules.fqn_orgs = []
    assert mapping.resolve_org(grid, rules) is None
    rules.user_teams = {"nguyen.van.an": ["DieuDo"]}
    assert mapping.resolve_org(grid, rules) == "a0"
    assert mapping.user_org("Nguyen.Van.An", rules) == ("a0", "via team DieuDo")
    # Teams of two organizations: ambiguous, so the FQN patterns / default decide.
    rules.user_teams = {"nguyen.van.an": ["DieuDo", "KinhDoanh"]}
    assert mapping.resolve_org(grid, rules) is None
    assert "several organizations" in mapping.user_org("nguyen.van.an", rules)[1]
    # An owner team beats an owner person.
    grid["owners"].append({"type": "team", "name": "KinhDoanh"})
    assert mapping.resolve_org(grid, rules) == "ban-kinh-doanh"


def test_unmapped_subdomain_joins_the_parent_group(snapshot, rules):
    customer = _table(snapshot, f"{CUR}.kinh_doanh.dim_customer")  # domain KinhDoanh.DichVuKhachHang
    assert mapping.resolve_groups(customer, rules) == []
    rules.domain_groups["kinhdoanh"] = "kinh-doanh-dvkh"
    assert mapping.resolve_groups(customer, rules) == ["kinh-doanh-dvkh"]
    rules.domain_groups["kinhdoanh.dichvukhachhang"] = "dvkh"
    assert mapping.resolve_groups(customer, rules) == ["dvkh"]


def test_legacy_owner_and_domain(snapshot, rules):
    table = _table(snapshot, OUTAGE)
    table["owner"], table["domain"] = table.pop("owners")[0], table.pop("domains")[0]
    assert mapping.resolve_org(table, rules) == "a0"
    assert mapping.resolve_groups(table, rules) == ["ky-thuat-an-toan"]


def test_desired_dataset(snapshot, rules):
    profile = snapshot["profiles"][OUTAGE]
    want = mapping.desired(_table(snapshot, OUTAGE), rules, profile)
    assert want["name"] == "om-trino_lakehouse-iceberg_curated-van_hanh-curated_outage_summary"
    assert want["title"] == "Tổng hợp sự cố mất điện theo ngày"
    assert want["owner_org"] == "a0" and want["groups"] == ["ky-thuat-an-toan"]
    assert want["tags"] == ["DataLayer.Gold"]  # Tier goes to an extra, not a tag
    extras = want["extras"]
    assert extras[mapping.Ext.TIER] == "Tier1"
    assert extras[mapping.Ext.URL] == "http://om.test/table/" + OUTAGE
    assert extras[mapping.RECORD_COUNT] == "1284530"
    assert extras[mapping.Ext.UPDATED].endswith("Z")
    assert [c["name"] for c in json.loads(extras[mapping.Ext.COLUMNS])][:2] == ["outage_date", "province_code"]
    assert want["fill_extras"][mapping.SOURCE_SYSTEM] == "Trino · trino_lakehouse"
    (trino,) = want["resources"]
    assert trino["url"] == "jdbc:trino://trino.test:30800/iceberg_curated/van_hanh"
    assert trino[mapping.RESOURCE_KIND] == mapping.TRINO


def test_trino_link_needs_a_catalog(snapshot, rules):
    table = _table(snapshot, OUTAGE)
    table["serviceType"] = "Iceberg"
    assert mapping.trino_url(table, rules) is None
    rules.trino_catalogs = {"trino_lakehouse.iceberg_curated": "lake"}
    assert mapping.trino_url(table, rules) == "jdbc:trino://trino.test:30800/lake/van_hanh"


def test_ckan_tag_sanitising():
    assert mapping.ckan_tag("PII.Sensitive") == "PII.Sensitive"
    assert mapping.ckan_tag("Glossary.Điện năng/Thương phẩm") == "Glossary.Điện năng-Thương phẩm"
    assert mapping.ckan_tag("x") is None


# --- merge rules ---------------------------------------------------------------------------


def _existing(want: dict[str, Any]) -> dict[str, Any]:
    """What package_show returns right after the sync created the dataset."""
    payload = mapping.create_payload(want, private=True)
    return {
        **payload, "id": "pkg-1", "state": "active", "organization": {"name": payload["owner_org"]},
        "owner_org": "org-uuid",
        "resources": [{**r, "id": f"res-{i}"} for i, r in enumerate(payload["resources"])],
    }


def test_unchanged_dataset_is_not_written(snapshot, rules):
    want = mapping.desired(_table(snapshot, OUTAGE), rules)
    assert mapping.update_payload(_existing(want), want) == {}


def test_hand_edits_survive_a_sync(snapshot, rules):
    want = mapping.desired(_table(snapshot, OUTAGE), rules)
    pkg = _existing(want)
    pkg["tags"].append({"name": "do-tin-cay"})
    pkg["groups"].append({"name": "kinh-doanh-dvkh"})
    pkg["extras"] += [{"key": "update_frequency", "value": "daily"}]
    pkg["extras"] = [e if e["key"] != mapping.SOURCE_SYSTEM else {**e, "value": "OMS"} for e in pkg["extras"]]
    pkg["resources"].append({"id": "csv", "name": "export.csv", "url": "http://x/export.csv", "format": "CSV"})
    pkg["private"] = False
    assert mapping.update_payload(pkg, want) == {}

    # OpenMetadata changes: a tag replaced, a new title
    table = _table(snapshot, OUTAGE)
    table["tags"] = [{"tagFQN": "DataLayer.Silver"}]
    table["displayName"] = "Sự cố mất điện"
    patch = mapping.update_payload(pkg, mapping.desired(table, rules))
    assert patch["title"] == "Sự cố mất điện"
    assert {t["name"] for t in patch["tags"]} == {"do-tin-cay", "DataLayer.Silver"}
    assert "groups" not in patch and "resources" not in patch and "private" not in patch
    extras = {e["key"]: e["value"] for e in patch["extras"]}
    assert extras["update_frequency"] == "daily" and extras[mapping.SOURCE_SYSTEM] == "OMS"


def test_empty_description_keeps_the_ckan_one(snapshot, rules):
    table = _table(snapshot, OUTAGE)
    want = mapping.desired(table, rules)
    pkg = _existing(want)
    pkg["notes"] = "Viết bởi biên tập viên"
    table["description"] = ""
    assert "notes" not in mapping.update_payload(pkg, mapping.desired(table, rules))


def test_owned_resource_is_updated_in_place(snapshot, rules):
    want = mapping.desired(_table(snapshot, OUTAGE), rules)
    pkg = _existing(want)
    rules.trino_jdbc_url = "jdbc:trino://new-host:443?SSL=true"
    patch = mapping.update_payload(pkg, mapping.desired(_table(snapshot, OUTAGE), rules))
    (res,) = patch["resources"]
    assert res["id"] == "res-0" and res["url"].startswith("jdbc:trino://new-host:443?SSL=true/")


def test_deleted_dataset_is_restored(snapshot, rules):
    want = mapping.desired(_table(snapshot, OUTAGE), rules)
    pkg = {**_existing(want), "state": "deleted"}
    assert mapping.update_payload(pkg, want) == {"state": "active"}


# --- client --------------------------------------------------------------------------------


class FakeResponse:
    def __init__(self, status: int, body: Any) -> None:
        self.status_code = status
        self._body = body
        self.text = json.dumps(body)

    def json(self) -> Any:
        return self._body


class FakeSession:
    """Answers like OpenMetadata < 1.5: `owners` and `domains` are unknown fields."""

    def __init__(self, tables: list[dict[str, Any]]) -> None:
        self.tables = tables
        self.calls: list[tuple[str, dict[str, Any]]] = []

    def get(self, url: str, params: dict[str, Any], headers: dict[str, str], timeout: float, verify: bool):
        self.calls.append((url, dict(params)))
        assert headers["Authorization"] == "Bearer t0k"
        for bad in ("owners", "domains"):
            if bad in params.get("fields", "").split(","):
                return FakeResponse(400, {"code": 400, "message": f"Invalid field name {bad}"})
        start = int(params.get("after", 0))
        page = self.tables[start:start + 2]
        paging = {"after": str(start + 2)} if start + 2 < len(self.tables) else {}
        return FakeResponse(200, {"data": page, "paging": paging})


def test_client_negotiates_fields_and_pages(snapshot):
    session = FakeSession(snapshot["tables"])
    client = OMClient("http://om.test/", "t0k", session=session)
    fqns = [t["fullyQualifiedName"] for t in client.iter_tables()]
    assert len(fqns) == len(snapshot["tables"])
    assert client._fields["table"] == "owner,domain"
    accepted = [p["fields"] for u, p in session.calls if "owner,domain" in p.get("fields", "")]
    assert len(accepted) == 4  # every page once negotiated: 7 tables, 2 per page
    assert all(u == "http://om.test/api/v1/tables" for u, _ in session.calls)


def test_client_reads_teams_with_the_old_owner_field(snapshot):
    session = FakeSession(snapshot["teams"])
    teams = list(OMClient("http://om.test", "t0k", session=session).iter_teams())
    assert len(teams) == len(snapshot["teams"])
    assert session.calls[-1][1]["fields"] == "users,defaultRoles,parents,children,owner"


def test_client_raises_on_http_errors():
    class Down:
        def get(self, *args, **kwargs):
            return FakeResponse(503, {"message": "maintenance"})

    with pytest.raises(OMError) as err:
        OMClient("http://om.test", session=Down()).version()
    assert err.value.status == 503 and "maintenance" in str(err.value)


def test_client_requires_a_url():
    with pytest.raises(OMError):
        OMClient("")


# --- panel shaping -------------------------------------------------------------------------


def test_lineage_sides(snapshot):
    table = _table(snapshot, OUTAGE)
    lineage = {"entity": {"id": table["id"]}, **snapshot["lineage"][OUTAGE]}
    result = panel.summarize_lineage(lineage)
    assert [n["type"] for n in result["upstream"]] == ["table", "pipeline"]
    assert {n["type"] for n in result["downstream"]} == {"dashboard", "table"}


def test_lineage_edges_as_references(snapshot):
    """Some releases put entity references instead of ids in the edges."""
    table = _table(snapshot, OUTAGE)
    raw = snapshot["lineage"][OUTAGE]
    edges = [{"fromEntity": {"id": e["fromEntity"]}, "toEntity": {"id": e["toEntity"]}} for e in raw["upstreamEdges"]]
    result = panel.summarize_lineage({"entity": table, "nodes": raw["nodes"], "upstreamEdges": edges})
    assert len(result["upstream"]) == 2 and result["downstream"] == []


def test_tests_summary(snapshot):
    result = panel.summarize_tests(snapshot["testCases"][OUTAGE])
    assert result["total"] == 4 and result["counts"]["Failed"] == 1 and result["counts"]["Success"] == 3
    assert result["items"][0]["status"] == "Failed" and result["items"][0]["column"] == "province_code"
    assert result["items"][-1]["column"] == ""  # table-level test
    assert "T" in result["items"][0]["at"] and "+" not in result["items"][0]["at"]


# --- bootstrap file ------------------------------------------------------------------------


DEMO = Path(bootstrap.__file__).parent / "demo" / "portal.yaml"


def test_demo_file_is_valid():
    data = bootstrap.load(DEMO.read_text("utf-8"))
    users = {u["name"] for u in data["users"]}
    for section in ("organizations", "groups"):
        for item in data[section]:
            assert set(item.get("members") or {}) <= users, item["name"]


@pytest.mark.parametrize("text,message", [
    ("users: [{name: a.b, email: x@y.z}]", "lower-case"),
    ("users: [{name: ab}]", "email"),
    ("organizations: [{name: org, members: {ab: owner}}]", "admin, editor, member"),
    ("groups: [{name: grp, members: {ab: editor}}]", "admin, member"),
    ("organizations: {name: x}", "must be a list"),
])
def test_bootstrap_rejects_bad_files(text, message):
    with pytest.raises(bootstrap.BootstrapError, match=message):
        bootstrap.load(text)


# --- scaffold ------------------------------------------------------------------------------


@pytest.mark.parametrize("text,expected", [
    ("BanKinhDoanh", "ban-kinh-doanh"),
    ("Ban Kỹ thuật – Sản xuất", "ban-ky-thuat-san-xuat"),
    ("Điều độ", "dieu-do"),
    ("EVNNPC", "evnnpc"),
    ("nguyen.van.an", "nguyen-van-an"),
])
def test_slug(text, expected):
    assert scaffold.slug(text) == expected


def _draft(snapshot: dict[str, Any], ckan: scaffold.Ckan | None = None) -> scaffold.Draft:
    return scaffold.build(snapshot["teams"], snapshot["domains"], snapshot["users"], ckan)


def test_scaffold_turns_teams_into_organizations_with_roles(snapshot):
    draft = _draft(snapshot)
    orgs = {o["name"]: o for o in draft.organizations}
    # The root Organization is not a unit; every other team is, the BusinessUnit included.
    assert set(orgs) == {"dieu-do", "kinh-doanh", "ky-thuat-san-xuat", "tai-chinh", "data-platform", "evn"}
    assert orgs["dieu-do"]["openmetadata"] == {"teams": ["DieuDo"]}
    assert orgs["dieu-do"]["title"] == "Trung tâm Điều độ"
    # Team owner -> admin; DataSteward (own role, or the team's default role) -> editor.
    assert orgs["dieu-do"]["members"] == {"do-thi-hoa": "member", "nguyen-van-an": "admin"}
    assert orgs["ky-thuat-san-xuat"]["members"] == {"pham-thi-dung": "editor"}
    assert orgs["kinh-doanh"]["members"] == {"hoang-van-em": "member", "le-van-cuong": "member",
                                             "tran-thi-binh": "admin"}
    assert "members" not in orgs["tai-chinh"]


def test_scaffold_turns_domains_into_groups(snapshot):
    draft = _draft(snapshot)
    groups = {g["name"]: g for g in draft.groups}
    # Organizations and groups share CKAN's namespace: a domain named like a team gets a prefix.
    assert set(groups) == {"van-hanh", "mien-kinh-doanh", "dich-vu-khach-hang", "ky-thuat", "mien-tai-chinh"}
    assert groups["dich-vu-khach-hang"]["openmetadata"] == {"domains": ["KinhDoanh.DichVuKhachHang"]}
    assert groups["mien-kinh-doanh"]["members"] == {"le-van-cuong": "member", "tran-thi-binh": "admin"}
    assert any("subdomain of KinhDoanh" in c for c in draft.comments[("groups", "dich-vu-khach-hang")])


def test_scaffold_output_is_a_valid_bootstrap_file(snapshot):
    draft = _draft(snapshot)
    text = scaffold.render(draft, "OpenMetadata test")
    data = bootstrap.load(text)
    users = {u["name"] for u in data["users"]}
    assert users == {"nguyen-van-an", "do-thi-hoa", "tran-thi-binh", "le-van-cuong", "pham-thi-dung", "hoang-van-em"}
    for section in ("organizations", "groups"):
        for item in data[section]:
            assert set(item.get("members") or {}) <= users, item["name"]
    assert "# OpenMetadata team DieuDo (Group), parent EVN" in text
    assert data == json.loads(json.dumps(draft.data()))


def test_scaffold_reuses_what_ckan_has(snapshot):
    ckan = scaffold.Ckan(
        users_by_email={"tran.thi.binh@evn.example": "kd-bientap"},
        user_names={"kd-bientap", "do-thi-hoa"},          # someone else already is do-thi-hoa
        orgs={"a0", "ban-kinh-doanh", "tai-chinh"}, groups={"ky-thuat-an-toan"},
        texts={"a0": {"title": "Trung tâm Điều độ HTĐ Quốc gia", "description": ""}},
        team_orgs={"dieudo": "a0", "kinhdoanh": "ban-kinh-doanh", "dataplatform": "ban-kinh-doanh"},
        domain_groups={"vanhanh": "ky-thuat-an-toan"},
    )
    draft = _draft(snapshot, ckan)
    orgs = {o["name"]: o for o in draft.organizations}
    # Mapped teams keep their organization; two teams of one organization make one entry.
    assert orgs["a0"]["openmetadata"] == {"teams": ["DieuDo"]}
    # CKAN's title wins over OpenMetadata's, an empty CKAN description is left alone.
    assert orgs["a0"]["title"] == "Trung tâm Điều độ HTĐ Quốc gia" and "description" not in orgs["a0"]
    assert "title in OpenMetadata: Trung tâm Điều độ" in draft.comments[("organizations", "a0")]
    assert orgs["ban-kinh-doanh"]["openmetadata"] == {"teams": ["DataPlatform", "KinhDoanh"]}
    assert orgs["ban-kinh-doanh"]["members"] == {"hoang-van-em": "member", "kd-bientap": "admin",
                                                 "le-van-cuong": "member"}
    assert orgs["a0"]["members"] == {"nguyen-van-an": "admin", "u-do-thi-hoa": "member"}
    assert "tai-chinh" in orgs  # an existing unmapped organization of the same name is reused
    assert {g["name"] for g in draft.groups} >= {"ky-thuat-an-toan", "mien-tai-chinh"}
    assert "kd-bientap" in {u["name"] for u in draft.users}
    assert any("existing CKAN account" in c for c in draft.comments[("users", "kd-bientap")])
