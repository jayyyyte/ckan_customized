"""`ckan lakehouse ...`: portal structure and permissions, OpenMetadata sync."""
from __future__ import annotations

import collections
import functools
import os
import sys
from collections.abc import Callable
from typing import Any

import click


def _with_request(fn: Callable[..., Any]) -> Callable[..., Any]:
    """Run inside a test request: actions build URLs (url_for) that need one, and CKAN's CLI does not push it."""

    @functools.wraps(fn)
    def wrapper(*args: Any, **kwargs: Any) -> Any:
        flask_app = click.get_current_context().meta["flask_app"]
        with flask_app.test_request_context():
            return fn(*args, **kwargs)

    return wrapper


def _lines(title: str, items: list[Any], colour: str | None = None) -> None:
    if items:
        click.secho(f"{title} ({len(items)}):", fg=colour, bold=True)
        for item in items:
            click.echo(f"  - {item if not isinstance(item, tuple) else ': '.join(item)}")


@click.group(short_help="Cổng dữ liệu EVN: đơn vị, nhóm, người dùng, đồng bộ OpenMetadata.")
def lakehouse() -> None:
    pass


# --- bootstrap ---------------------------------------------------------------------------


@lakehouse.command()
@click.argument("path", type=click.File("r", encoding="utf-8"))
@click.option("--user", "username", default="admin", show_default=True,
              help="Sysadmin the changes are made as (shown in activity streams).")
@click.option("--credentials", "credentials", type=click.Path(dir_okay=False, allow_dash=True),
              help="Where to write the passwords of new users (CSV, mode 600, must not exist); '-' prints them. "
                   "Required when the file creates users.")
@click.option("--prune", is_flag=True,
              help="Also remove memberships the file does not declare (in the organizations/groups it lists).")
@_with_request
def bootstrap(path: Any, username: str, credentials: str | None, prune: bool) -> None:
    """Create or update organizations, groups, users and roles from a YAML file ('-' reads stdin).

    Format: ckanext/lakehouse/demo/portal.yaml. Safe to run again.
    """
    from ckanext.lakehouse.bootstrap import Bootstrap, BootstrapError, credentials_csv, load

    try:
        job = Bootstrap(load(path.read()), username)
    except BootstrapError as err:
        raise click.UsageError(str(err)) from err

    new_users = job.new_users()
    if new_users and not credentials:
        raise click.UsageError(f"{len(new_users)} new user(s) ({', '.join(new_users)}): pass --credentials FILE "
                               "to receive their passwords")
    out = None
    if new_users and credentials != "-":
        # Open before writing anything: a bad path must not leave users with unknown passwords.
        try:
            fd = os.open(credentials, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        except OSError as err:
            raise click.UsageError(f"cannot create {credentials}: {err.strerror} (it must not exist yet)") from err
        out = os.fdopen(fd, "w", encoding="utf-8", newline="")

    try:
        result = job.run(prune=prune)
    finally:
        if out is not None:
            out.write(credentials_csv(job.result.credentials))
            out.close()

    _lines("Created", result.created, "green")
    _lines("Updated", result.updated, "cyan")
    _lines("Roles set", result.memberships, "cyan")
    _lines("Memberships removed", result.removed, "yellow")
    _lines("Notes", result.notes, "yellow")
    if result.credentials:
        if credentials == "-":
            click.echo(credentials_csv(result.credentials), nl=False)
        else:
            click.secho(f"Passwords of {len(result.credentials)} new user(s) written to {credentials}. "
                        "Hand them over, then delete the file.", fg="yellow")
    if not any((result.created, result.updated, result.memberships, result.removed)):
        click.secho("Nothing to change.", fg="green")


# --- OpenMetadata ------------------------------------------------------------------------


@lakehouse.group()
def om() -> None:
    """OpenMetadata: check the connection, publish tables as datasets."""


def _require_om() -> None:
    from ckanext.lakehouse import config

    if not config.om_enabled():
        click.secho("OpenMetadata is not configured (ckanext.lakehouse.om.url): nothing to do.", fg="yellow")
        sys.exit(0)


@om.command()
@_with_request
def check() -> None:
    """Connection, version, and how the in-scope tables map onto organizations and groups."""
    from ckanext.lakehouse.om import mapping
    from ckanext.lakehouse.om.client import OMError
    from ckanext.lakehouse.om.sync import client_for_sync, load_rules

    _require_om()
    client = client_for_sync()
    rules = load_rules()
    try:
        click.echo(f"OpenMetadata {client.version()} at {client.api}")
        tables = list(client.iter_tables())
    except OMError as err:
        raise click.ClickException(str(err)) from err
    click.echo(f"{len(tables)} table(s) visible to the token; include={rules.include or '(empty)'}")

    in_scope = [t for t in tables if mapping.in_scope(t, rules)]
    services: collections.Counter[str] = collections.Counter(mapping.service_name(t) for t in tables)
    teams: collections.Counter[str] = collections.Counter()
    domains: collections.Counter[str] = collections.Counter()
    orgs: collections.Counter[str] = collections.Counter()
    for table in in_scope:
        for owner in mapping.owners(table):
            if owner.get("type", "team") == "team":
                teams[owner.get("name", "?")] += 1
        for domain in mapping.domains(table):
            domains[domain.get("name", "?")] += 1
        orgs[mapping.resolve_org(table, rules) or "(none: skipped)"] += 1

    def show(title: str, counter: collections.Counter[str], mapped: dict[str, str] | None = None) -> None:
        click.secho(title, bold=True)
        for key, count in counter.most_common():
            target = ""
            if mapped is not None:
                target = f" -> {mapped.get(key.casefold(), '(not mapped)')}"
            click.echo(f"  {count:5d}  {key}{target}")

    show("Services (all tables):", services)
    click.secho(f"{len(in_scope)} table(s) in scope", fg="green" if in_scope else "yellow")
    show("Owner teams (in scope):", teams, rules.team_orgs)
    show("Domains (in scope):", domains, rules.domain_groups)
    show("Organizations the sync would use:", orgs)


@om.command()
@click.option("--dry-run", is_flag=True, help="Show what would change without writing.")
@click.option("--allow-empty", is_flag=True,
              help="Remove every OpenMetadata dataset when nothing is in scope (normally refused).")
@click.option("--user", "username", default=None, help="Act as this user (default: ckanext.lakehouse.om.sync_user).")
@_with_request
def sync(dry_run: bool, allow_empty: bool, username: str | None) -> None:
    """Create, update and remove datasets so CKAN matches the tables in scope."""
    from ckanext.lakehouse import config
    from ckanext.lakehouse.om.client import OMError
    from ckanext.lakehouse.om.sync import Syncer, client_for_sync, load_rules, sync_user

    _require_om()
    syncer = Syncer(client_for_sync(), load_rules(), username or sync_user(),
                    private=config.get("om.private"), on_removed=config.get("om.on_removed"),
                    fetch_profile=config.get("om.fetch_profile"), dry_run=dry_run)
    try:
        report = syncer.run(allow_empty=allow_empty)
    except OMError as err:
        raise click.ClickException(f"{err} — nothing was changed") from err

    prefix = "[dry run] " if dry_run else ""
    click.echo(f"{prefix}{report.tables} table(s) listed, {report.in_scope} in scope, "
               f"{report.unchanged} unchanged")
    _lines(f"{prefix}Created", report.created, "green")
    _lines(f"{prefix}Updated", report.updated, "cyan")
    _lines(f"{prefix}Removed", report.removed, "yellow")
    _lines("Skipped", report.skipped, "yellow")
    _lines("Notes", report.notes, "yellow")
    _lines("Errors", report.errors, "red")
    if report.errors:
        sys.exit(1)
