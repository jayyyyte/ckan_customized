"""EVN data portal theme. Wiring only: the logic lives in the modules it points to."""
from __future__ import annotations

from typing import Any

import ckan.plugins as plugins
import ckan.plugins.toolkit as tk
from ckan.lib.plugins import DefaultTranslation

from ckanext.evntheme import cache, cli, config, downloads, helpers
from ckanext.evntheme.helpers import search
from ckanext.evntheme.mds.views import mds


class EvnThemePlugin(plugins.SingletonPlugin, DefaultTranslation):
    plugins.implements(plugins.IConfigurer)
    plugins.implements(plugins.IConfigDeclaration)
    plugins.implements(plugins.ITemplateHelpers)
    plugins.implements(plugins.ITranslation)
    plugins.implements(plugins.IBlueprint)
    plugins.implements(plugins.IClick)
    plugins.implements(plugins.IFacets)
    plugins.implements(plugins.IGroupController, inherit=True)
    plugins.implements(plugins.IPackageController, inherit=True)

    # IConfigurer

    def update_config(self, config_: Any) -> None:
        tk.add_template_directory(config_, "templates")
        tk.add_public_directory(config_, "public")
        tk.add_resource("assets", "evntheme")

    # IConfigDeclaration

    def declare_config_options(self, declaration: Any, key: Any) -> None:
        config.declare(declaration, key)

    # ITemplateHelpers

    def get_helpers(self) -> dict[str, Any]:
        return helpers.get_helpers()

    # IBlueprint

    def get_blueprint(self) -> list[Any]:
        return [mds, downloads.dataset]

    # IClick

    def get_commands(self) -> list[Any]:
        return [cli.evntheme]

    # IFacets: same facets on dataset, organisation and group searches

    def dataset_facets(self, facets_dict: Any, package_type: str) -> Any:
        return search.dataset_facets(facets_dict)

    def organization_facets(self, facets_dict: Any, organization_type: str, package_type: str) -> Any:
        return search.dataset_facets(facets_dict)

    def group_facets(self, facets_dict: Any, group_type: str, package_type: str) -> Any:
        return search.dataset_facets(facets_dict)

    # IGroupController & IPackageController: invalidate cached stats and directory on data changes

    def create(self, entity: Any) -> None:
        cache.clear_all()

    def edit(self, entity: Any) -> None:
        cache.clear_all()

    def delete(self, entity: Any) -> None:
        cache.clear_all()

    def after_dataset_create(self, context: Any, pkg_dict: Any) -> None:
        cache.clear_all()

    def after_dataset_update(self, context: Any, pkg_dict: Any) -> None:
        cache.clear_all()

    def after_dataset_delete(self, context: Any, pkg_dict: Any) -> None:
        cache.clear_all()
