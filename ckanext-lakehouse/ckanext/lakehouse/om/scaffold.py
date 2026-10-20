"""`ckan lakehouse om scaffold`: a bootstrap file drafted from OpenMetadata's teams and domains.

A person reviews the draft (merges teams into one unit, renames, removes test teams),
then applies it with `ckan lakehouse bootstrap`. Nothing here writes to CKAN.

  OpenMetadata                          bootstrap file (CKAN)
  team, any type but Organization   ->  organization, openmetadata.teams = [team]
    owner of the team (a person)    ->    admin
    member holding an editor role   ->    editor  (role of the person, or default role of the team)
    other member                    ->    member  (reads the organization's private datasets)
  domain or subdomain               ->  group, openmetadata.domains = [domain FQN]
    owner of the domain (a person)  ->    admin
    expert                          ->    member
  person                            ->  user; a CKAN account with the same e-mail is reused

Organizations and groups CKAN already has keep their CKAN name, title and description (the
OpenMetadata title goes in a comment), and teams mapped to the same organization come out as
one entry, so scaffolding again yields a file that `bootstrap` applies without changes where
OpenMetadata did not change.
"""
from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field
from typing import Any

import yaml

from ckanext.lakehouse.om import mapping

EDITOR_ROLES = ("DataSteward",)
ROOT_TEAM_TYPE = "Organization"
_RANK = {"member": 0, "editor": 1, "admin": 2}
_CAMEL = re.compile(r"(?<=[a-z0-9])(?=[A-Z])")
_INVALID = re.compile(r"[^a-z0-9_-]+")


def slug(text: str) -> str:
    """CKAN name from an OpenMetadata name: 'BanKinhDoanh' / 'Ban Kỹ thuật' -> 'ban-kinh-doanh' / 'ban-ky-thuat'."""
    text = _CAMEL.sub("-", (text or "").replace("đ", "d").replace("Đ", "D"))
    text = "".join(c for c in unicodedata.normalize("NFKD", text) if not unicodedata.combining(c))
    text = re.sub(r"-{2,}", "-", _INVALID.sub("-", text.lower())).strip("-_")
    return text[:100].rstrip("-_")


def _refs(entity: dict[str, Any], plural: str) -> list[dict[str, Any]]:
    """`owners` (1.5+) or the older single `owner`."""
    if entity.get(plural):
        return list(entity[plural])
    single = entity.get(plural[:-1])
    return [single] if single else []


def _names(refs: list[dict[str, Any]] | None) -> list[str]:
    return sorted({r["name"] for r in refs or [] if r.get("name")})


@dataclass
class Ckan:
    """What CKAN already has, so the draft reuses names instead of colliding with them."""

    users_by_email: dict[str, str] = field(default_factory=dict)  # casefolded e-mail -> user name
    user_names: set[str] = field(default_factory=set)
    orgs: set[str] = field(default_factory=set)
    groups: set[str] = field(default_factory=set)
    texts: dict[str, dict[str, str]] = field(default_factory=dict)  # org/group -> {title, description}
    team_orgs: dict[str, str] = field(default_factory=dict)       # casefolded team -> org (om_teams)
    domain_groups: dict[str, str] = field(default_factory=dict)   # casefolded domain -> group (om_domains)


def ckan_state(rules: mapping.Rules) -> Ckan:
    """What CKAN has now: accounts, organizations, groups and their current mappings (reads the database)."""
    import ckan.model as model

    users = model.Session.query(model.User.name, model.User.email).filter(model.User.state != "deleted").all()
    groups = model.Session.query(model.Group.name, model.Group.is_organization, model.Group.title,
                                 model.Group.description).filter(model.Group.state == "active").all()
    return Ckan(
        users_by_email={email.casefold(): name for name, email in users if email},
        user_names={name for name, _ in users},
        orgs={name for name, is_org, _, _ in groups if is_org},
        groups={name for name, is_org, _, _ in groups if not is_org},
        texts={name: {"title": title or "", "description": text or ""} for name, _, title, text in groups},
        team_orgs=dict(rules.team_orgs), domain_groups=dict(rules.domain_groups),
    )


@dataclass
class Draft:
    users: list[dict[str, Any]] = field(default_factory=list)
    organizations: list[dict[str, Any]] = field(default_factory=list)
    groups: list[dict[str, Any]] = field(default_factory=list)
    comments: dict[tuple[str, str], list[str]] = field(default_factory=dict)
    notes: list[str] = field(default_factory=list)

    def data(self) -> dict[str, Any]:
        return {"users": self.users, "organizations": self.organizations, "groups": self.groups}


def _unique(base: str, taken: set[str], prefix: str) -> str:
    name = f"{prefix}{base}" if base else f"{prefix}x"
    candidate, n = name, 2
    while candidate in taken:
        candidate, n = f"{name}-{n}", n + 1
    return candidate


class _Builder:
    def __init__(self, ckan: Ckan, editor_roles: set[str], users: list[dict[str, Any]]) -> None:
        self.ckan = ckan
        self.editor_roles = {r.casefold() for r in editor_roles}
        self.people = {u["name"]: u for u in users if u.get("name") and not u.get("isBot")}
        self.draft = Draft()
        # Organizations and groups share one namespace in CKAN (the `group` table). Names
        # already mapped to a team/domain are kept for it, never handed to another one.
        self.used: set[str] = set()
        self.reserved = set(ckan.team_orgs.values()) | set(ckan.domain_groups.values())
        self.entries: dict[str, dict[str, Any]] = {}
        self.user_names: dict[str, str | None] = {}   # OM user name -> CKAN user name

    def _comment(self, section: str, name: str, *lines: str) -> None:
        self.draft.comments.setdefault((section, name), []).extend(lines)

    def _claim(self, mapped: str | None, base: str, own: set[str], other: set[str], prefix: str) -> tuple[str, str]:
        """(CKAN name, how it was chosen) for a team or a domain."""
        if mapped:
            self.used.add(mapped)
            return mapped, "mapped"
        if len(base) >= 2 and base not in self.used | other | self.reserved:
            self.used.add(base)
            return base, "existing" if base in own else "new"
        name = _unique(base, self.used | own | other | self.reserved, prefix)
        self.used.add(name)
        return name, "new"

    # --- people ----------------------------------------------------------------------------

    def person(self, om_name: str) -> str | None:
        """CKAN user name of an OpenMetadata person, adding them to the draft; None if unusable."""
        if om_name in self.user_names:
            return self.user_names[om_name]
        self.user_names[om_name] = None
        user = self.people.get(om_name)
        if user is None:
            self.draft.notes.append(f"{om_name}: not a person the OpenMetadata API lists (bot or deleted), left out")
            return None
        email = (user.get("email") or "").strip()
        name = self.ckan.users_by_email.get(email.casefold()) if email else None
        if name:
            self._comment("users", name, f"OpenMetadata {om_name}: existing CKAN account (same e-mail), not modified")
        elif not email:
            self.draft.notes.append(f"{om_name}: no e-mail in OpenMetadata, cannot create a CKAN account; left out")
            return None
        else:
            base = slug(om_name)
            taken = self.ckan.user_names | {n for n in self.user_names.values() if n}
            name = base if len(base) >= 2 and base not in taken else _unique(base, taken, "u-")
            if name != base:
                self._comment("users", name, f"OpenMetadata {om_name}: {base!r} is taken in CKAN or too short")
        if user.get("isAdmin"):
            self._comment("users", name, "OpenMetadata admin: add `sysadmin: true` only if they run the portal too")
        self.user_names[om_name] = name
        if all(u["name"] != name for u in self.draft.users):
            self.draft.users.append({"name": name, "fullname": user.get("displayName") or om_name, "email": email})
        return name

    def _add(self, section: str, entry: dict[str, Any], om_key: str, om_value: str,
             roles: dict[str, str]) -> None:
        """Add an organization/group entry, or merge it into the one of the same CKAN name."""
        members: dict[str, str] = {}
        for om_name, role in roles.items():
            name = self.person(om_name)
            if name and _RANK[role] >= _RANK.get(members.get(name, "member"), 0):
                members[name] = role
        current = self.entries.get(entry["name"])
        ckan_text = self.ckan.texts.get(entry["name"])
        if current is None and ckan_text is not None:
            if ckan_text["title"] and ckan_text["title"] != entry["title"]:
                self._comment(section, entry["name"], f"title in OpenMetadata: {entry['title']}")
            entry = {"name": entry["name"], **{k: v for k, v in ckan_text.items() if v}}
        if current is None:
            entry["openmetadata"] = {om_key: [om_value]}
            self.entries[entry["name"]] = entry
            getattr(self.draft, section).append(entry)
            current, old = entry, {}
        else:
            current["openmetadata"][om_key].append(om_value)
            old = current.get("members") or {}
        for name, role in members.items():
            if _RANK[role] >= _RANK.get(old.get(name, "member"), 0):
                old[name] = role
        if old:
            current["members"] = dict(sorted(old.items()))

    def _owners(self, section: str, name: str, entity: dict[str, Any], roles: dict[str, str]) -> None:
        for owner in _refs(entity, "owners"):
            if owner.get("type", "user") == "user" and owner.get("name"):
                roles[owner["name"]] = "admin"
            elif owner.get("name"):
                self._comment(section, name, f"owned by team {owner['name']}: give its people a role by hand")

    # --- teams -> organizations -------------------------------------------------------------

    def team(self, team: dict[str, Any]) -> None:
        om_name = team["name"]
        name, how = self._claim(self.ckan.team_orgs.get(om_name.casefold()), slug(om_name),
                                self.ckan.orgs, self.ckan.groups, "to-chuc-")
        default_roles = {r.casefold() for r in _names(team.get("defaultRoles"))}
        roles: dict[str, str] = {}
        for om_user in _names(team.get("users")):
            held = default_roles | {r.casefold() for r in _names((self.people.get(om_user) or {}).get("roles"))}
            roles[om_user] = "editor" if held & self.editor_roles else "member"
        self._owners("organizations", name, team, roles)
        parents = ", ".join(_names(team.get("parents"))) or "-"
        children = ", ".join(_names(team.get("children")))
        self._comment("organizations", name, f"OpenMetadata team {om_name} ({team.get('teamType') or '?'}), "
                                             f"parent {parents}" + (f", children {children}" if children else "")
                      + ("" if roles else ", no members"))
        if how == "mapped":
            self._comment("organizations", name, f"{om_name} is already mapped to this organization (om_teams)")
        elif how == "existing":
            self._comment("organizations", name, "exists in CKAN, not mapped yet: bootstrap adds the mapping")
        if team.get("teamType") not in (None, "Group"):
            self._comment("organizations", name, "not a Group team: usually owns no table itself; keep it only "
                                                 "to merge its Group teams into one unit")
        entry = {"name": name, "title": team.get("displayName") or om_name}
        if team.get("description"):
            entry["description"] = team["description"]
        self._add("organizations", entry, "teams", om_name, roles)

    # --- domains -> groups -------------------------------------------------------------------

    def domain(self, domain: dict[str, Any]) -> None:
        fqn = domain.get("fullyQualifiedName") or domain["name"]
        mapped = self.ckan.domain_groups.get(fqn.casefold()) or self.ckan.domain_groups.get(domain["name"].casefold())
        name, how = self._claim(mapped, slug(domain["name"]), self.ckan.groups, self.ckan.orgs, "mien-")
        roles = {expert: "member" for expert in _names(domain.get("experts"))}
        self._owners("groups", name, domain, roles)
        info = f"OpenMetadata domain {fqn} ({domain.get('domainType') or '?'})"
        parent = mapping.split_fqn(fqn)[:-1]
        if parent:
            info += f", subdomain of {'.'.join(parent)}: drop this entry to put its tables in the parent's group"
        self._comment("groups", name, info)
        if how == "mapped":
            self._comment("groups", name, f"{fqn} is already mapped to this group (om_domains)")
        elif how == "existing":
            self._comment("groups", name, "exists in CKAN, not mapped yet: bootstrap adds the mapping")
        entry = {"name": name, "title": domain.get("displayName") or domain["name"]}
        if domain.get("description"):
            entry["description"] = domain["description"]
        self._add("groups", entry, "domains", fqn, roles)


def build(teams: list[dict[str, Any]], domains: list[dict[str, Any]], users: list[dict[str, Any]],
          ckan: Ckan | None = None, editor_roles: tuple[str, ...] | set[str] = EDITOR_ROLES) -> Draft:
    ckan = ckan or Ckan()
    builder = _Builder(ckan, set(editor_roles), users)
    # Mapped ones first: they hold their names whatever the alphabetical order.
    teams = [t for t in teams if t.get("name") and t.get("teamType") != ROOT_TEAM_TYPE and not t.get("deleted")]
    for team in sorted(teams, key=lambda t: (t["name"].casefold() not in ckan.team_orgs, t["name"])):
        builder.team(team)
    domains = [d for d in domains if d.get("name")]
    for domain in sorted(domains, key=lambda d: d.get("fullyQualifiedName") or d["name"]):
        builder.domain(domain)
    draft = builder.draft
    draft.users.sort(key=lambda u: u["name"])
    draft.organizations.sort(key=lambda o: o["name"])
    draft.groups.sort(key=lambda g: g["name"])
    if not draft.organizations:
        draft.notes.append("OpenMetadata has no team besides the root Organization: tables can only be "
                           "claimed by FQN pattern (openmetadata.fqn) or om.default_org")
    return draft


def render(draft: Draft, source: str = "") -> str:
    """The draft as a bootstrap file, with a comment above each entry saying where it comes from."""
    lines = [
        "# Draft of the portal structure, generated by `ckan lakehouse om scaffold`"
        + (f" from {source}" if source else "") + ".",
        "# Review it, then apply it with `ckan lakehouse bootstrap FILE --credentials OUT.csv`:",
        "#  - several teams that are one unit: move their names into one entry's openmetadata.teams;",
        "#  - delete test teams/domains, fix titles, check every role (admin | editor | member).",
        "# It holds names and e-mail addresses of real people: keep it outside git.",
        "# The sync acts as user `om-sync` (ckanext.lakehouse.om.sync_user): declare it if it does not exist.",
    ]
    if draft.notes:
        lines.append("#")
        lines += [f"# NOTE {n}" for n in draft.notes]
    for section, items in draft.data().items():
        lines.append("")
        lines.append(f"{section}:" if items else f"{section}: []")
        for item in items:
            lines += [f"  # {c}" for c in draft.comments.get((section, item["name"]), [])]
            dumped = yaml.safe_dump([item], allow_unicode=True, sort_keys=False, width=200)
            lines += [f"  {line}" for line in dumped.splitlines()]
    return "\n".join(lines) + "\n"
