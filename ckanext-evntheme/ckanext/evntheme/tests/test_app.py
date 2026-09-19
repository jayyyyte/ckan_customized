"""Tests that go through the CKAN app: pages render, MDS blueprint, downloads.

They need the CKAN test database and Solr, so they run in CI
(.github/workflows/evntheme.yml at the repository root) or wherever
`ckan_test` exists: pytest --ckan-ini=test.ini ckanext/evntheme/tests/test_app.py
"""
from __future__ import annotations

import base64
import io
import json
import re

import pytest

import ckan.plugins as plugins
from ckan.tests import factories

from ckanext.evntheme import cache
from ckanext.evntheme.mds import service

pytestmark = [
    pytest.mark.ckan_config("ckan.plugins", "evntheme activity tracking"),
    pytest.mark.usefixtures("with_plugins", "clean_db", "clean_index", "evntheme_db"),
]

CATALOG = {
    "code": "MDS-T-001",
    "name": "Nhóm vật tư thử",
    "group": "Tài sản & Vật tư",
    "version": "1.0",
    "effective_from": "2026-07-01",
    "issuer": "Ban Thử nghiệm",
    "name_label": "Tên nhóm",
    "count_label": "Số vật tư",
    "codes": [
        {"code": "T-01", "name": "Thiết bị chính", "count": 10},
        {"code": "T-01-01", "name": "Máy biến áp", "parent": "T-01", "count": 4, "status": "new"},
    ],
    "versions": [{"version": "1.0", "note": "Ban hành", "date": "2026-07-01"}],
    "consumers": [{"name": "ERP", "sync": "02:00", "status": "late"}],
}


@pytest.fixture
def evntheme_db(clean_db, migrate_db_for):
    for plugin in ("activity", "tracking", "evntheme"):
        migrate_db_for(plugin)
    service._tables_ready = False
    cache.clear_all()
    yield
    cache.clear_all()


@pytest.fixture
def dataset():
    org = factories.Organization(
        name="ban-thu", title="Ban Thử nghiệm",
        extras=[{"key": "org_type", "value": "department"}, {"key": "abbreviation", "value": "BTN"}],
    )
    group = factories.Group(name="tai-chinh-vat-tu", title="Tài chính – Vật tư")
    return factories.Dataset(
        name="danh-muc-thu", title="Danh mục thử", owner_org=org["id"], groups=[{"name": group["name"]}],
        notes="Mô tả **thử**.", tags=[{"name": "vật tư"}],
        extras=[
            {"key": "data_type", "value": "master"},
            {"key": "update_frequency", "value": "daily"},
            {"key": "record_count", "value": "1204"},
            {"key": "quality_completeness", "value": "98.4"},
            {"key": "open_level", "value": "3"},
        ],
        resources=[
            {"name": "full.csv", "url": "http://example.com/full.csv", "format": "CSV"},
            {"name": "trino", "url": "jdbc:trino://trino.local:8080/iceberg/demo", "format": "JDBC"},
        ],
    )


def _text(response) -> str:
    return response.get_data(as_text=True)


def test_plugin_loaded():
    assert plugins.plugin_loaded("evntheme")


# 1x1 transparent PNG
PNG = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNkYPhfDwAChwGA60e6kgAAAABJRU5ErkJggg=="
)


@pytest.fixture
def storage(ckan_config, monkeypatch, tmp_path):
    """Upload folder; request it before `app`, which serves /uploads/ from it."""
    monkeypatch.setitem(ckan_config, "ckan.storage_path", str(tmp_path))
    return tmp_path


def test_sysadmin_uploads_a_raster_logo(storage, app):
    token = factories.SysadminWithToken()["token"]

    def upload(content: bytes, filename: str):
        return app.post("/api/3/action/config_option_update", headers={"Authorization": token},
                        data={"logo_upload": (io.BytesIO(content), filename)})

    assert upload(b'<svg xmlns="http://www.w3.org/2000/svg"/>', "logo.svg").status_code == 409
    assert upload(PNG, "evn-logo.png").status_code == 200

    body = _text(app.get("/"))
    logo = re.search(r'class="evn-brand__logo" src="([^"]+)"', body).group(1)
    assert logo.startswith("/uploads/admin/") and logo.endswith(".png")
    assert f'class="evn-footer__logo" src="{logo}"' in body
    assert app.get(logo).status_code == 200


@pytest.mark.parametrize("url", ["/", "/dataset/", "/organization/", "/group/", "/mds/", "/about"])
def test_pages_render_with_the_theme(app, dataset, url):
    response = app.get(url)
    assert response.status_code == 200
    body = _text(response)
    assert 'class="evn-header"' in body
    assert "evn-footer" in body


def test_home_shows_counters_and_recent_dataset(app, dataset):
    body = _text(app.get("/"))
    assert "evn-hero" in body
    assert "Danh mục thử" in body
    assert "Tài chính – Vật tư" in body  # data domain card


@pytest.mark.parametrize("tab", ["overview", "preview", "api", "activity"])
def test_dataset_tabs(app, dataset, tab):
    response = app.get(f"/dataset/{dataset['name']}", query_string={"tab": tab})
    assert response.status_code == 200
    body = _text(response)
    assert f'id="tab-{tab}"' in body
    assert "Master data" in body  # hero badge from the data_type extra
    assert "1,204" in body or "1.204" in body


def test_dataset_api_tab_falls_back_to_package_show_without_datastore(app, dataset):
    body = _text(app.get(f"/dataset/{dataset['name']}", query_string={"tab": "api"}))
    assert "package_show" in body


def test_search_facets_and_chips(app, dataset):
    body = _text(app.get("/dataset/", query_string={"data_type": "master"}))
    assert "evn-chip" in body
    assert 'name="data_type"' in body  # the "Data type" facet
    assert "Danh mục thử" in body


def test_organization_directory_and_page(app, dataset):
    body = _text(app.get("/organization/"))
    assert "Ban Thử nghiệm" in body and "BTN" in body
    body = _text(app.get("/organization/", query_string={"type": "corporation"}))
    assert "Ban Thử nghiệm" not in body
    assert app.get("/organization/ban-thu").status_code == 200


def test_resource_page_has_trino_box(app, dataset):
    resource = dataset["resources"][1]
    body = _text(app.get(f"/dataset/{dataset['name']}/resource/{resource['id']}"))
    assert "trino --server http://trino.local:8080" in body


def test_download_all_needs_uploaded_files(app, dataset):
    assert app.get(f"/dataset/{dataset['name']}/download-all").status_code == 404


def test_mds_pages_and_exports(app):
    service.load_many([CATALOG])
    cache.clear_all()

    body = _text(app.get("/mds/"))
    assert "Nhóm vật tư thử" in body and "T-01-01" in body
    assert "evn-level-2" in body  # T-01-01 is indented under T-01

    csv_response = app.get("/mds/MDS-T-001/download.csv")
    assert csv_response.status_code == 200
    assert _text(csv_response).lstrip("﻿").startswith("code,name,parent_code,item_count,status")

    payload = json.loads(_text(app.get("/mds/MDS-T-001/download.json")))
    assert [c["code"] for c in payload["codes"]] == ["T-01", "T-01-01"]

    assert app.get("/mds/UNKNOWN").status_code == 404
    assert app.get("/mds/MDS-T-001/download.xml").status_code == 404


def test_mds_load_replaces_codes(app):
    service.load_many([CATALOG])
    changed = {**CATALOG, "codes": [{"code": "T-01", "name": "Đổi tên"}]}
    service.load_many([changed])
    page = service.get_catalog("MDS-T-001")
    assert [(r.code.code, r.code.name) for r in page.rows] == [("T-01", "Đổi tên")]


def test_mds_rejects_unknown_status():
    with pytest.raises(ValueError):
        service.load_many([{**CATALOG, "status": "bogus"}])
