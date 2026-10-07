"""OpenMetadata table -> CKAN dataset, as pure functions (no database, no request).

Ownership rules, so a sync never overwrites what people edit in CKAN:

* OpenMetadata owns: title, owner_org, the ``om_*`` extras, ``record_count``, the tags
  and domain groups it added (remembered in ``om_tags`` / ``om_groups``), and resources
  marked ``om_kind``. The description too, but only while OpenMetadata has one.
* CKAN owns everything else: other extras (update_frequency, data_type, ...), tags,
  groups and resources added by hand, license, ``private`` after creation.
* ``source_system`` is filled from OpenMetadata only while empty.
"""
from __future__ import annotations

import fnmatch
import hashlib
import json
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any
from urllib.parse import quote


class Ext:
    """Dataset extras written by the sync. Every key starts with OM_PREFIX."""

    ID = "om_id"
    FQN = "om_fqn"
    URL = "om_url"
    SERVICE = "om_service"
    SERVICE_TYPE = "om_service_type"
    TABLE_TYPE = "om_table_type"
    TIER = "om_tier"
    OWNERS = "om_owners"
    UPDATED = "om_updated_at"
    VERSION = "om_version"
    COLUMNS = "om_columns"
    TAGS = "om_tags"
    GROUPS = "om_groups"


OM_PREFIX = "om_"
# Theme extras (ckanext-evntheme vocab.Extra) the sync fills.
RECORD_COUNT = "record_count"
SOURCE_SYSTEM = "source_system"

# Organization / group extras written by `ckan lakehouse bootstrap`: JSON lists.
ORG_TEAMS = "om_teams"
ORG_FQN_PATTERNS = "om_fqn_patterns"
GROUP_DOMAINS = "om_domains"

RESOURCE_KIND = "om_kind"
TRINO = "trino"

NAME_PREFIX = "om-"
NAME_MAX = 100
MAX_COLUMNS = 500
TIER_PREFIX = "tier."
_TAG_INVALID = re.compile(r"[^\w .-]+", re.UNICODE)
_NAME_INVALID = re.compile(r"[^a-z0-9_-]+")


@dataclass
class Rules:
    """Everything `desired()` needs besides the table: scope, ownership and link settings."""

    include: list[str] = field(default_factory=list)
    exclude: list[str] = field(default_factory=list)
    require_tags: list[str] = field(default_factory=list)
    team_orgs: dict[str, str] = field(default_factory=dict)          # casefolded team -> org name
    fqn_orgs: list[tuple[str, str]] = field(default_factory=list)    # (pattern, org name)
    domain_groups: dict[str, str] = field(default_factory=dict)      # casefolded domain -> group name
    default_org: str | None = None
    ui_url: str = ""
    trino_jdbc_url: str = ""
    trino_catalogs: dict[str, str] = field(default_factory=dict)     # "service.database" -> catalog


# --- reading OpenMetadata entities ------------------------------------------------------


def split_fqn(fqn: str) -> list[str]:
    """'svc.db."my.schema".t' -> ['svc', 'db', 'my.schema', 't'] (OpenMetadata quotes dotted names)."""
    parts, current, quoted = [], [], False
    for char in fqn:
        if char == '"':
            quoted = not quoted
        elif char == "." and not quoted:
            parts.append("".join(current))
            current = []
        else:
            current.append(char)
    parts.append("".join(current))
    return parts


def ref_name(ref: dict[str, Any] | None) -> str:
    if not ref:
        return ""
    return ref.get("displayName") or ref.get("name") or ref.get("fullyQualifiedName") or ""


def owners(table: dict[str, Any]) -> list[dict[str, Any]]:
    """`owners` (1.5+) or the older single `owner`."""
    if table.get("owners"):
        return list(table["owners"])
    return [table["owner"]] if table.get("owner") else []


def domains(table: dict[str, Any]) -> list[dict[str, Any]]:
    """`domains` (recent releases) or the older single `domain`."""
    if table.get("domains"):
        return list(table["domains"])
    return [table["domain"]] if table.get("domain") else []


def tag_fqns(table: dict[str, Any]) -> list[str]:
    return [t["tagFQN"] for t in table.get("tags") or [] if t.get("tagFQN")]


def tier(table: dict[str, Any]) -> str:
    for fqn in tag_fqns(table):
        if fqn.lower().startswith(TIER_PREFIX):
            return fqn.split(".", 1)[1]
    return ""


def service_name(table: dict[str, Any]) -> str:
    service = table.get("service") or {}
    return service.get("name") or split_fqn(table.get("fullyQualifiedName", ""))[0]


def table_url(ui_url: str, fqn: str) -> str:
    return f"{ui_url.rstrip('/')}/table/{quote(fqn, safe='')}" if ui_url else ""


def updated_at(table: dict[str, Any]) -> str:
    """OpenMetadata `updatedAt` (epoch ms) as ISO 8601 UTC."""
    millis = table.get("updatedAt")
    if not isinstance(millis, int | float):
        return ""
    return datetime.fromtimestamp(millis / 1000, tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def columns(table: dict[str, Any]) -> list[dict[str, str]]:
    """Compact data dictionary kept on the dataset (searchable, and the tab's offline fallback)."""
    result = []
    for col in (table.get("columns") or [])[:MAX_COLUMNS]:
        item = {"name": col.get("name", ""), "type": col.get("dataTypeDisplay") or col.get("dataType") or ""}
        if col.get("description"):
            item["description"] = col["description"]
        if col.get("constraint"):
            item["constraint"] = col["constraint"]
        result.append(item)
    return result


# --- scope and ownership ----------------------------------------------------------------


def _matches(value: str, patterns: list[str]) -> bool:
    return any(fnmatch.fnmatchcase(value, p) for p in patterns)


def in_scope(table: dict[str, Any], rules: Rules) -> bool:
    fqn = table.get("fullyQualifiedName", "")
    if table.get("deleted") or not _matches(fqn, rules.include) or _matches(fqn, rules.exclude):
        return False
    if rules.require_tags:
        wanted = {t.casefold() for t in rules.require_tags}
        return any(t.casefold() in wanted for t in tag_fqns(table))
    return True


def schema_prefixes(include: list[str]) -> list[str] | None:
    """Schema FQNs to list instead of the whole catalog, when every pattern pins its schema.

    'svc.db.schema.*' -> 'svc.db.schema'. None: some pattern needs a full listing.
    """
    schemas = []
    for pattern in include:
        parts = split_fqn(pattern)
        head = parts[:3]
        if len(parts) < 4 or any(ch in p for p in head for ch in "*?["):
            return None
        schema = ".".join(f'"{p}"' if "." in p else p for p in head)
        if schema not in schemas:
            schemas.append(schema)
    return schemas


def resolve_org(table: dict[str, Any], rules: Rules) -> str | None:
    """Owner team first, then table FQN patterns, then the default organization."""
    for owner in owners(table):
        if owner.get("type", "team") == "team":
            for key in (owner.get("name"), owner.get("displayName")):
                if key and key.casefold() in rules.team_orgs:
                    return rules.team_orgs[key.casefold()]
    fqn = table.get("fullyQualifiedName", "")
    for pattern, org in rules.fqn_orgs:
        if fnmatch.fnmatchcase(fqn, pattern):
            return org
    return rules.default_org or None


def resolve_groups(table: dict[str, Any], rules: Rules) -> list[str]:
    result = []
    for domain in domains(table):
        for key in (domain.get("name"), domain.get("fullyQualifiedName"), domain.get("displayName")):
            group = rules.domain_groups.get((key or "").casefold())
            if group:
                if group not in result:
                    result.append(group)
                break
    return result


# --- the desired dataset ----------------------------------------------------------------


def dataset_name(fqn: str) -> str:
    """Stable CKAN name from the FQN: lower-case, [a-z0-9_-], at most 100 characters."""
    slug = _NAME_INVALID.sub("-", fqn.lower().replace('"', "")).strip("-_")
    name = NAME_PREFIX + slug
    if len(name) > NAME_MAX:
        digest = hashlib.sha1(fqn.encode("utf-8")).hexdigest()[:8]
        name = name[: NAME_MAX - 9].rstrip("-_") + "-" + digest
    return name


def ckan_tag(tag_fqn: str) -> str | None:
    """CKAN accepts letters, digits, space, - _ . and 2..100 characters."""
    tag = _TAG_INVALID.sub("-", tag_fqn).strip(" -")[:100]
    return tag if len(tag) >= 2 else None


def trino_url(table: dict[str, Any], rules: Rules) -> str | None:
    if not rules.trino_jdbc_url:
        return None
    parts = split_fqn(table.get("fullyQualifiedName", ""))
    if len(parts) != 4:
        return None
    service, database, schema, _ = parts
    catalog = rules.trino_catalogs.get(f"{service}.{database}")
    if catalog is None and (table.get("serviceType") or "").lower() == "trino":
        catalog = database
    if not catalog:
        return None
    return f"{rules.trino_jdbc_url.rstrip('/')}/{catalog}/{schema}"


def desired(table: dict[str, Any], rules: Rules, profile: dict[str, Any] | None = None) -> dict[str, Any]:
    """What the sync wants the dataset to look like. `owner_org` is None when no organization claims it."""
    fqn = table["fullyQualifiedName"]
    parts = split_fqn(fqn)
    om_extras = {
        Ext.ID: table.get("id", ""),
        Ext.FQN: fqn,
        Ext.URL: table_url(rules.ui_url, fqn),
        Ext.SERVICE: service_name(table),
        Ext.SERVICE_TYPE: table.get("serviceType") or "",
        Ext.TABLE_TYPE: table.get("tableType") or "",
        Ext.TIER: tier(table),
        Ext.OWNERS: ", ".join(filter(None, (ref_name(o) for o in owners(table)))),
        Ext.UPDATED: updated_at(table),
        Ext.VERSION: str(table.get("version") or ""),
        Ext.COLUMNS: json.dumps(columns(table), ensure_ascii=False, separators=(",", ":")),
    }
    if profile and profile.get("rowCount") is not None:
        om_extras[RECORD_COUNT] = str(int(profile["rowCount"]))
    tags = [t for t in (ckan_tag(f) for f in tag_fqns(table) if not f.lower().startswith(TIER_PREFIX)) if t]
    resources = []
    jdbc = trino_url(table, rules)
    if jdbc:
        resources.append({
            "name": f"Trino: {'.'.join(parts[1:])}" if len(parts) == 4 else f"Trino: {fqn}",
            "url": jdbc,
            "format": "Trino",
            "description": f"`SELECT * FROM {'.'.join(parts[1:]) if len(parts) == 4 else fqn}`",
            RESOURCE_KIND: TRINO,
        })
    return {
        "name": dataset_name(fqn),
        "title": table.get("displayName") or table.get("name") or parts[-1],
        "notes": table.get("description") or "",
        "owner_org": resolve_org(table, rules),
        "extras": {k: v for k, v in om_extras.items() if v != ""},
        "fill_extras": {SOURCE_SYSTEM: " · ".join(filter(None, (table.get("serviceType"), service_name(table))))},
        "tags": sorted(set(tags)),
        "groups": resolve_groups(table, rules),
        "resources": resources,
    }


def create_payload(want: dict[str, Any], private: bool) -> dict[str, Any]:
    extras = {**{k: v for k, v in want["fill_extras"].items() if v}, **want["extras"],
              Ext.TAGS: json.dumps(want["tags"], ensure_ascii=False),
              Ext.GROUPS: json.dumps(want["groups"], ensure_ascii=False)}
    return {
        "name": want["name"],
        "title": want["title"],
        "notes": want["notes"],
        "owner_org": want["owner_org"],
        "private": private,
        "extras": [{"key": k, "value": v} for k, v in sorted(extras.items())],
        "tags": [{"name": t} for t in want["tags"]],
        "groups": [{"name": g} for g in want["groups"]],
        "resources": [dict(r) for r in want["resources"]],
    }


def _json_list(value: str | None) -> list[str]:
    try:
        data = json.loads(value or "[]")
    except ValueError:
        return []
    return [str(v) for v in data] if isinstance(data, list) else []


def update_payload(existing: dict[str, Any], want: dict[str, Any]) -> dict[str, Any]:
    """package_patch payload bringing `existing` to `want`; {} when nothing changed.

    Only changed top-level keys are sent: package_patch keeps the rest, and leaving
    `resources` out avoids re-submitting uploads to XLoader.
    """
    patch: dict[str, Any] = {}
    old_extras = {e["key"]: e.get("value", "") for e in existing.get("extras") or []}

    if want["title"] and existing.get("title") != want["title"]:
        patch["title"] = want["title"]
    # package_show gives owner_org as an id; the rules speak organization names.
    if want["owner_org"] and (existing.get("organization") or {}).get("name") != want["owner_org"]:
        patch["owner_org"] = want["owner_org"]
    if want["notes"] and (existing.get("notes") or "") != want["notes"]:
        patch["notes"] = want["notes"]
    if existing.get("state") == "deleted":
        patch["state"] = "active"

    # Tags and groups: drop what the previous sync added, keep the hand-made ones.
    old_om_tags = set(_json_list(old_extras.get(Ext.TAGS)))
    old_tags = {t["name"] for t in existing.get("tags") or []}
    new_tags = (old_tags - old_om_tags) | set(want["tags"])
    if new_tags != old_tags:
        patch["tags"] = [{"name": t} for t in sorted(new_tags)]

    old_om_groups = set(_json_list(old_extras.get(Ext.GROUPS)))
    old_groups = {g["name"] for g in existing.get("groups") or []}
    new_groups = (old_groups - old_om_groups) | set(want["groups"])
    if new_groups != old_groups:
        patch["groups"] = [{"name": g} for g in sorted(new_groups)]

    extras = {k: v for k, v in old_extras.items() if not k.startswith(OM_PREFIX)}
    if RECORD_COUNT in want["extras"]:
        extras.pop(RECORD_COUNT, None)
    for key, value in want["fill_extras"].items():
        if value and not extras.get(key):
            extras[key] = value
    extras.update(want["extras"])
    extras[Ext.TAGS] = json.dumps(want["tags"], ensure_ascii=False)
    extras[Ext.GROUPS] = json.dumps(want["groups"], ensure_ascii=False)
    if extras != old_extras:
        patch["extras"] = [{"key": k, "value": v} for k, v in sorted(extras.items())]

    resources = _merge_resources(existing.get("resources") or [], want["resources"])
    if resources is not None:
        patch["resources"] = resources
    return patch


_RESOURCE_FIELDS = ("name", "url", "format", "description")


def _merge_resources(existing: list[dict[str, Any]], wanted: list[dict[str, Any]]) -> list[dict[str, Any]] | None:
    """Existing resources with the `om_kind` ones replaced by `wanted`; None when unchanged."""
    by_kind = {r.get(RESOURCE_KIND): r for r in existing if r.get(RESOURCE_KIND)}
    changed = set(by_kind) != {w[RESOURCE_KIND] for w in wanted}
    merged = [r for r in existing if not r.get(RESOURCE_KIND)]
    for want in wanted:
        old = by_kind.get(want[RESOURCE_KIND])
        if old is None:
            merged.append(dict(want))
            continue
        if any((old.get(k) or "") != want[k] for k in _RESOURCE_FIELDS):
            changed = True
        merged.append({**old, **want})
    return merged if changed else None
