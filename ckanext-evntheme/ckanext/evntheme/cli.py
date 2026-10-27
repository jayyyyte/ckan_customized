"""`ckan evntheme ...` commands: demo content and the shared code lists (MDS)."""
from __future__ import annotations

import functools
import json
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


@click.group(short_help="Cổng dữ liệu EVN: dữ liệu demo, danh mục chuẩn (MDS).")
def evntheme() -> None:
    pass


@evntheme.command("seed-demo")
@click.option("--user", "username", default="admin", show_default=True,
              help="Sysadmin who creates the demo content (shown in activity streams).")
@click.option("--usage/--no-usage", default=True, show_default=True,
              help="Simulate page views and downloads (needs the tracking plugin).")
@click.option("--reset", is_flag=True, help="Purge the demo content before loading it again.")
@_with_request
def seed_demo(username: str, usage: bool, reset: bool) -> None:
    """Load the demo groups, organisations, datasets and code lists. Local development only."""
    from ckanext.evntheme.demo.seed import Seeder

    try:
        seeder = Seeder(username)
    except ValueError as err:
        raise click.UsageError(str(err)) from err
    if reset:
        seeder.reset()
        click.secho("Demo content purged.", fg="yellow")
    seeder.run(usage=usage)
    click.secho("Demo content loaded.", fg="green")


@evntheme.command("sync-openmetadata")
@click.option("--user", "username", default="admin", show_default=True,
              help="Sysadmin the sync runs as (shown in activity streams).")
@click.option("--service", default="",
              help="Limit to one OpenMetadata database service (e.g. trino). Empty: every service.")
@click.option("--tag", "publish_tag", default="",
              help="Only tables carrying this OpenMetadata tag (e.g. CKAN.Publish, Tier.Gold). "
                   "Empty: ckanext.evntheme.openmetadata_publish_tag, or every table if that is empty too.")
@click.option("--dry-run", is_flag=True, help="List what would change, without writing anything.")
@_with_request
def sync_openmetadata(username: str, service: str, publish_tag: str, dry_run: bool) -> None:
    """Create/update one CKAN dataset per table catalogued in OpenMetadata (Trino/Iceberg)."""
    from ckanext.evntheme import config
    from ckanext.evntheme.openmetadata import OpenMetadataClient, OpenMetadataError, Syncer, TrinoConfig

    api_url = config.get("openmetadata_api_url")
    if not api_url:
        raise click.UsageError("ckanext.evntheme.openmetadata_api_url is not set.")

    trino_user = config.get("trino_user")
    preview_rows = config.get("openmetadata_preview_rows")
    # Password is optional: this cluster's Trino has no authenticator configured, so a
    # username alone connects. TrinoConfig.password="" then skips BasicAuthentication.
    # query_host is the in-cluster address CKAN itself connects to; openmetadata_trino_host is
    # the externally reachable one shown in the JDBC resource, and they can differ (gotchas: a
    # NodePort a browser reaches is not always the address a pod should use).
    query_host = config.get("trino_query_host") or config.get("openmetadata_trino_host")
    trino = TrinoConfig(
        query_host, trino_user, config.get("trino_password"),
    ) if (trino_user and preview_rows > 0) else None
    try:
        syncer = Syncer(
            username, config.get("openmetadata_owner_org"), config.get("openmetadata_trino_host"),
            trino=trino, preview_rows=preview_rows,
        )
    except ValueError as err:
        raise click.UsageError(str(err)) from err

    client = OpenMetadataClient(api_url, config.get("openmetadata_token"))
    tag = publish_tag or config.get("openmetadata_publish_tag")
    counts = {"create": 0, "update": 0}
    try:
        for table in client.tables(service, tag):
            action = syncer.sync(table, dry_run=dry_run)
            counts[action] += 1
            click.echo(f"{action:>6}  {table.dataset_name}  ({table.fqn})")
    except OpenMetadataError as err:
        raise click.ClickException(str(err)) from err

    verb = "Would create/update" if dry_run else "Created/updated"
    click.secho(f"{verb} {counts['create']} new, {counts['update']} existing dataset(s).", fg="green")


@evntheme.group()
def mds() -> None:
    """Shared code lists ("Danh mục chuẩn")."""


@mds.command("load")
@click.argument("path", type=click.Path(exists=True, dir_okay=False))
@_with_request
def mds_load(path: str) -> None:
    """Create or replace code lists from a JSON file (format: ckanext/evntheme/demo/mds.json)."""
    from ckanext.evntheme.cache import clear_all
    from ckanext.evntheme.mds import service

    with open(path, encoding="utf-8") as fh:
        payload = json.load(fh)
    try:
        catalogs = service.load_many(payload)
    except ValueError as err:
        raise click.ClickException(str(err)) from err
    clear_all()
    click.secho(f"Loaded {len(catalogs)} code list(s).", fg="green")


@mds.command("export")
@click.argument("code")
@click.option("--format", "fmt", type=click.Choice(["json", "csv"]), default="json", show_default=True)
@_with_request
def mds_export(code: str, fmt: str) -> None:
    """Print one code list to stdout."""
    from ckanext.evntheme.mds import service

    page = service.get_catalog(code)
    if page is None:
        raise click.ClickException(f"code list {code!r} not found")
    body, _ = service.export(page, fmt)
    sys.stdout.buffer.write(body)
