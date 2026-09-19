"""Controlled vocabularies of the portal: one place for every code -> label/tone mapping.

Templates, helpers, the demo seed and the tests all read these tables, so adding a
data type, a frequency or an organisation type is a one-line change here (plus its
Vietnamese label in the .po file).

Labels are *msgids*: they are marked with ``N_`` so Babel extracts them, and are
translated at render time with ``toolkit._`` (never at import time, when no request
locale exists yet).
"""
from __future__ import annotations

from dataclasses import dataclass


def N_(msgid: str) -> str:
    """Mark a string for extraction without translating it (see setup.cfg keywords)."""
    return msgid


@dataclass(frozen=True)
class Term:
    code: str
    label: str
    tone: str = "neutral"


def _index(*terms: Term) -> dict[str, Term]:
    return {t.code: t for t in terms}


# Dataset extras understood by the theme. With ckanext-scheming these become
# top-level fields; helpers.dataset.field() reads both places.
class Extra:
    DATA_TYPE = "data_type"
    FREQUENCY = "update_frequency"
    SOURCE_SYSTEM = "source_system"
    RECORD_COUNT = "record_count"
    GOLDEN_RECORD = "golden_record"
    METADATA_STANDARD = "metadata_standard"
    SPATIAL = "spatial_coverage"
    TEMPORAL = "temporal_coverage"
    OPEN_LEVEL = "open_level"
    RATING_AVERAGE = "rating_average"
    RATING_COUNT = "rating_count"


# Organization extras.
class OrgExtra:
    TYPE = "org_type"
    ABBREVIATION = "abbreviation"
    DOMAIN = "domain"


# Group extras (data domains).
class GroupExtra:
    TONE = "tone"


# --- Datasets -------------------------------------------------------------------

# "Loại dữ liệu". Codes are stored in the `data_type` extra and faceted as-is:
# CKAN also indexes each extra as a plain Solr string field named after its key.
DATA_TYPES = _index(
    Term("master", N_("Master data"), "orange"),
    Term("transaction", N_("Transactional data"), "blue"),
    Term("reference", N_("Reference data"), "sand"),
)


@dataclass(frozen=True)
class Frequency(Term):
    # A dataset is "published on time" when its last update is at most this old.
    # None: no schedule, excluded from the on-time rate.
    max_age_days: float | None = None


FREQUENCIES = _index(
    Frequency("realtime", N_("real time"), max_age_days=1),
    Frequency("hourly", N_("hourly"), max_age_days=1),
    Frequency("daily", N_("daily"), max_age_days=2),
    Frequency("weekly", N_("weekly"), max_age_days=9),
    Frequency("monthly", N_("monthly"), max_age_days=36),
    Frequency("quarterly", N_("quarterly"), max_age_days=100),
    Frequency("yearly", N_("yearly"), max_age_days=380),
    Frequency("irregular", N_("irregular")),
)

# Quality scores (percent, 0-100) stored as extras; shown as progress bars.
QUALITY_METRICS = (
    Term("quality_completeness", N_("Completeness"), "green"),
    Term("quality_uniqueness", N_("Uniqueness"), "green"),
    Term("quality_validity", N_("Valid format"), "blue"),
    Term("quality_timeliness", N_("Updated on time"), "orange"),
)

# Resource formats with a dedicated badge colour; anything else uses "other".
# Keys are upper-cased `resource.format` values.
FORMAT_STYLES = {
    "CSV": "csv",
    "JSON": "json",
    "API": "api",
    "XLSX": "xlsx",
    "XLS": "xlsx",
    "GEOJSON": "geojson",
    "PDF": "pdf",
}
FORMAT_LABELS = {"GEOJSON": "GeoJSON"}

# Formats that mean "this dataset exposes an API" (plus any DataStore resource).
API_FORMATS = frozenset({"API"})

# Resource formats the "Map" preview can draw.
MAP_FORMATS = frozenset({"GEOJSON"})

# --- Organizations ---------------------------------------------------------------

ORG_TYPES = _index(
    Term("department", N_("Department")),
    Term("corporation", N_("Power corporation")),
    Term("affiliate", N_("Affiliated unit")),
    Term("other", N_("Other unit")),
)

# Filter tabs on /organization. "other" collects every type without its own tab.
ORG_FILTERS = (
    Term("all", N_("All")),
    Term("department", N_("Departments")),
    Term("corporation", N_("Power corporations")),
    Term("other", N_("Other units")),
)

# Colour pairs for avatars and domain icons, see $tones in _tokens.scss.
TONES = ("blue", "orange", "green", "sky", "sand")

# --- Search ----------------------------------------------------------------------

# Facets queried on dataset searches, in display order, with their titles.
# `groups` is queried (so filter chips show domain names) but not shown in the
# sidebar by default, see config `ckanext.evntheme.sidebar_facets`.
FACETS = (
    Term("organization", N_("Publisher")),
    Term("res_format", N_("File format")),
    Term("data_type", N_("Data type")),
    Term("tags", N_("Popular tags")),
    Term("license_id", N_("License")),
    Term("groups", N_("Data domain")),
)

# Short prefixes for the "Đang lọc:" chips. Fields without a prefix show the value only.
CHIP_PREFIXES = {
    "organization": N_("Publisher"),
    "res_format": N_("Format"),
    "tags": N_("Tag"),
    "license_id": N_("License"),
    "groups": N_("Domain"),
}

# --- Dataset page ----------------------------------------------------------------

# Tabs of the dataset page, selected with ?tab=<code> (overview has no parameter).
DATASET_TABS = (
    Term("overview", N_("Overview")),
    Term("preview", N_("Data preview")),
    Term("api", N_("Try the API")),
    Term("activity", N_("Activity")),
)

# --- Activity stream -------------------------------------------------------------

ACTIVITY_KINDS = {
    "new package": Term("new package", N_("{actor} published this dataset."), "created"),
    "changed package": Term("changed package", N_("{actor} updated this dataset."), "updated"),
    "deleted package": Term("deleted package", N_("{actor} deleted this dataset."), "warning"),
}
DEFAULT_ACTIVITY = Term("other", N_("{actor} changed this dataset."), "edited")

# --- Danh mục chuẩn (MDS) --------------------------------------------------------

MDS_CATALOG_STATUSES = _index(
    Term("active", N_("Currently in force"), "green"),
    Term("draft", N_("Draft"), "orange"),
    Term("retired", N_("Retired"), "sand"),
)
MDS_CODE_STATUSES = _index(
    Term("active", N_("In force"), "green"),
    Term("new", N_("New"), "orange"),
    Term("retired", N_("Retired"), "sand"),
)
MDS_CONSUMER_STATUSES = _index(
    Term("ok", N_("Synced"), "green"),
    Term("live", N_("Live API"), "blue"),
    Term("late", N_("Late"), "orange"),
)
