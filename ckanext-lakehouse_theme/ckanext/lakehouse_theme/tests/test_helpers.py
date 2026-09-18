import pytest

from ckanext.lakehouse_theme import helpers
from ckanext.lakehouse_theme.helpers import trino_connection


def test_trino_connection_full_url():
    assert trino_connection("jdbc:trino://10.1.117.91:30800/iceberg_curated/demo") == {
        "jdbc_url": "jdbc:trino://10.1.117.91:30800/iceberg_curated/demo",
        "host": "10.1.117.91",
        "port": 30800,
        "ssl": False,
        "catalog": "iceberg_curated",
        "schema": "demo",
        "server": "http://10.1.117.91:30800",
    }


def test_trino_connection_ssl_default_port_without_schema():
    info = trino_connection("jdbc:trino://trino.example.com/hive?SSL=true")
    assert info["server"] == "https://trino.example.com:443"
    assert info["catalog"] == "hive"
    assert info["schema"] is None


@pytest.mark.parametrize("url", [
    None,
    "",
    "https://example.com/orders.csv",
    "jdbc:postgresql://db:5432/ckan",
    "jdbc:trino://",
    "jdbc:trino://host:notaport/x",
])
def test_trino_connection_rejects_other_urls(url):
    assert trino_connection(url) is None


def test_recent_datasets_asks_package_search_for_newest_first(monkeypatch):
    calls = []

    def package_search(context, data_dict):
        calls.append(data_dict)
        return {"count": 1, "results": [{"name": "demo-curated-orders"}]}

    monkeypatch.setattr(helpers.tk, "get_action", lambda name: package_search)
    assert helpers.recent_datasets(3) == [{"name": "demo-curated-orders"}]
    assert calls == [{"rows": 3, "sort": "metadata_modified desc"}]
