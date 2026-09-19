"""Unit tests that need neither a CKAN app nor a database.

Run locally without the CKAN pytest plugins (they connect to the test DB on start,
docs/gotchas.md 6k):

    python -m pytest -o addopts="" -p no:ckan -p no:ckan_fixtures ckanext/evntheme/tests/test_units.py
"""
from __future__ import annotations

import datetime as dt
from pathlib import Path
from types import SimpleNamespace

import pytest
from babel.messages.pofile import read_po

from ckanext.evntheme import config, formatting, stats, vocab
from ckanext.evntheme.helpers import common, trino
from ckanext.evntheme.mds import service

NOW = dt.datetime(2026, 9, 19, 12, 0, tzinfo=dt.timezone.utc)
PACKAGE_DIR = Path(__file__).resolve().parents[1]


# --- formatting ------------------------------------------------------------------


@pytest.mark.parametrize(
    ("value", "decimals", "locale", "expected"),
    [
        (1204, 0, "vi", "1.204"),
        (99.974, 2, "vi", "99,97"),
        (128402, 0, "en", "128,402"),
        ("12", 0, "vi", "12"),
        (None, 0, "vi", ""),
        ("n/a", 0, "vi", "n/a"),
    ],
)
def test_number(value, decimals, locale, expected):
    assert formatting.number(value, decimals, locale) == expected


def test_percent_drops_useless_decimals():
    assert formatting.percent(98.4, locale="vi") == "98,4%"
    assert formatting.percent(100, locale="vi") == "100%"


@pytest.mark.parametrize(
    "value",
    ["2026-09-19T10:00:00.123456", "2026-09-19T10:00:00.1Z", "2026-09-19T10:00:00Z"],
)
def test_parse_datetime_accepts_ckan_and_solr_formats(value):
    parsed = formatting.parse_datetime(value)
    assert parsed is not None and parsed.tzinfo is not None
    assert parsed.replace(microsecond=0) == dt.datetime(2026, 9, 19, 10, tzinfo=dt.timezone.utc)


def test_parse_datetime_rejects_garbage():
    assert formatting.parse_datetime("yesterday") is None
    assert formatting.parse_datetime(None) is None


def test_date_uses_full_vietnamese_pattern():
    assert formatting.date(dt.date(2026, 7, 1), locale="vi") == "01/07/2026"
    assert formatting.date(None, locale="vi") == ""


def test_duration_is_readable():
    assert formatting.duration(dt.timedelta(minutes=5), locale="vi") == "5 phút"
    assert formatting.duration(dt.timedelta(hours=23), locale="en") == "23 hours"


# --- portal statistics -------------------------------------------------------------


def _row(org, hours_ago, frequency=None, formats=("CSV",), datastore=()):
    row = {
        "organization": org,
        "metadata_modified": (NOW - dt.timedelta(hours=hours_ago)).strftime("%Y-%m-%dT%H:%M:%S.%fZ"),
        "res_format": list(formats),
        "res_extras_datastore_active": list(datastore),
    }
    if frequency:
        row["update_frequency"] = frequency  # package_search strips the extras_ prefix
    return row


def test_compute_counts_datasets_apis_and_on_time():
    rows = [
        _row("a", 1, "daily", formats=("API", "JSON")),
        _row("a", 100, "daily"),                       # 4 days old: late for a daily dataset
        _row("b", 5, "monthly", datastore=("True",)),  # DataStore counts as an API
        _row("b", 2, None),                            # no schedule: not in the on-time rate
        _row(None, 2, "yearly"),                       # no organisation
    ]
    result = stats.compute(rows, now=NOW)

    assert result.datasets == 5
    assert result.api_datasets == 2
    assert result.on_time.scheduled == 4
    assert result.on_time.rate == pytest.approx(75.0)

    a, b = result.org("a"), result.org("b")
    assert (a.datasets, a.api_datasets, a.on_time.rate) == (2, 1, 50.0)
    assert (b.datasets, b.api_datasets, b.on_time.rate) == (2, 1, 100.0)
    assert b.last_modified == NOW - dt.timedelta(hours=2)
    assert result.org("missing").datasets == 0


def test_on_time_rate_is_none_without_schedules():
    assert stats.compute([_row("a", 1)], now=NOW).on_time.rate is None


def test_is_api_dataset():
    assert stats.is_api_dataset(["api"], [])
    assert stats.is_api_dataset(["CSV"], ["true"])
    assert not stats.is_api_dataset(["CSV", "PDF"], ["False"])


# --- helpers ------------------------------------------------------------------------


def test_field_reads_top_level_then_extras():
    pkg = {"data_type": "", "extras": [{"key": "data_type", "value": "master"}], "update_frequency": "daily"}
    assert common.field(pkg, "data_type") == "master"
    assert common.field(pkg, "update_frequency") == "daily"
    assert common.field(pkg, "missing") is None
    assert common.field(None, "x") is None


def test_initials_and_tone_are_stable():
    assert common.initials("Ban Quản lý đấu thầu") == "BQLĐ"
    assert common.initials("") == "?"
    assert common.tone_for("evnnpc") == common.tone_for("evnnpc")
    assert common.tone_for("evnnpc") in vocab.TONES


def test_trino_connection():
    info = trino.trino_connection("jdbc:trino://10.1.117.91:30800/iceberg_curated/demo?SSL=true")
    assert info["server"] == "https://10.1.117.91:30800"
    assert (info["catalog"], info["schema"], info["ssl"]) == ("iceberg_curated", "demo", True)
    assert trino.trino_connection("https://example.org/file.csv") is None
    assert trino.trino_connection("jdbc:trino://:abc") is None


def test_public_action_refuses_anything_but_public_reads():
    from ckanext.evntheme import public

    with pytest.raises(ValueError):
        public.action("package_delete", {"id": "x"})


# --- code lists ----------------------------------------------------------------------


def test_code_levels_follow_parents_and_survive_cycles():
    codes = [
        SimpleNamespace(code="VT-01", parent_code=None),
        SimpleNamespace(code="VT-01-01", parent_code="VT-01"),
        SimpleNamespace(code="VT-01-01-01", parent_code="VT-01-01"),
        SimpleNamespace(code="X", parent_code="Y"),       # parent outside the list
        SimpleNamespace(code="A", parent_code="B"),       # A <-> B cycle
        SimpleNamespace(code="B", parent_code="A"),
    ]
    levels = service._levels(codes)
    assert levels["VT-01"] == 1
    assert levels["VT-01-01"] == 2
    assert levels["VT-01-01-01"] == 3
    assert levels["X"] == 1
    assert levels["A"] in (1, 2) and levels["B"] in (1, 2)


# --- configuration and translations -------------------------------------------------------


def test_config_defaults_are_typed():
    assert isinstance(config.OPTIONS["stats_cache_seconds"][0], int)
    assert isinstance(config.OPTIONS["hot_searches"][0], str)


def test_logo_uses_the_theme_file_only_while_ckan_default():
    ckan_default = "/base/images/ckan-logo.png"
    assert config.pick_logo(ckan_default, ckan_default) == config.THEME_LOGO
    assert config.pick_logo(None, ckan_default) == config.THEME_LOGO
    for configured in ("/uploads/admin/2026-09-19-logo.jpg", "/evntheme/images/evn-logo.png", "https://cdn.x/l.webp"):
        assert config.pick_logo(configured, ckan_default) == configured
    assert config.pick_logo("", ckan_default) == ""  # cleared on /ckan-admin/config: title only
    assert (PACKAGE_DIR / "public" / config.THEME_LOGO.lstrip("/")).is_file()


def test_declaration_fills_core_gaps_but_never_redeclares():
    from ckan.config.declaration import Declaration, Key

    fresh = Declaration()
    config.declare(fresh, Key())
    assert fresh.get("ckan.upload.admin.mimetypes").default == ["image/png", "image/jpeg", "image/gif", "image/webp"]

    upgraded = Declaration()  # a CKAN release that declares the key itself
    upgraded.declare_list(Key().ckan.upload.admin.types, ["image", "text"])
    config.declare(upgraded, Key())
    assert upgraded.get("ckan.upload.admin.types").default == ["image", "text"]


def _vi_catalog():
    path = PACKAGE_DIR / "i18n" / "vi" / "LC_MESSAGES" / "ckanext-evntheme.po"
    with path.open("rb") as fh:
        return read_po(fh, locale="vi")


def _all_vocab_labels():
    terms = [
        *vocab.DATA_TYPES.values(), *vocab.FREQUENCIES.values(), *vocab.QUALITY_METRICS,
        *vocab.ORG_TYPES.values(), *vocab.ORG_FILTERS, *vocab.FACETS, *vocab.DATASET_TABS,
        *vocab.ACTIVITY_KINDS.values(), vocab.DEFAULT_ACTIVITY, *vocab.MDS_CATALOG_STATUSES.values(),
        *vocab.MDS_CODE_STATUSES.values(), *vocab.MDS_CONSUMER_STATUSES.values(),
    ]
    return {t.label for t in terms} | set(vocab.CHIP_PREFIXES.values())


def test_every_vocabulary_label_is_translated():
    catalog = _vi_catalog()
    missing = [label for label in _all_vocab_labels() if not (catalog.get(label) and catalog.get(label).string)]
    assert missing == []


def test_placeholders_survive_translation():
    """A translation must keep the {placeholders} / %(named)s of its msgid, or .format() breaks."""
    import re

    pattern = re.compile(r"\{\w*\}|%\(\w+\)s")
    for message in _vi_catalog():
        if not message.id:
            continue
        source = message.id[0] if isinstance(message.id, tuple) else message.id
        targets = message.string if isinstance(message.string, tuple) else (message.string,)
        for target in targets:
            assert set(pattern.findall(target)) == set(pattern.findall(source)), source


def test_compiled_css_is_committed_and_has_no_important():
    css = (PACKAGE_DIR / "assets" / "css" / "evn-theme.css").read_text("utf-8")
    assert "--evn-blue" in css
    assert "!important" not in css
