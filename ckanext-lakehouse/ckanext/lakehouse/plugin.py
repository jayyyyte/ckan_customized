"""Lakehouse integration of the EVN data portal. Wiring only: the logic lives in the modules it points to."""
from __future__ import annotations

from typing import Any

import ckan.plugins as plugins
import ckan.plugins.toolkit as tk
from ckan.lib.plugins import DefaultTranslation

from ckanext.lakehouse import cli, config, helpers
from ckanext.lakehouse.om.views import dataset


class LakehousePlugin(plugins.SingletonPlugin, DefaultTranslation):
    plugins.implements(plugins.IConfigurer)
    plugins.implements(plugins.IConfigDeclaration)
    plugins.implements(plugins.ITemplateHelpers)
    plugins.implements(plugins.ITranslation)
    plugins.implements(plugins.IBlueprint)
    plugins.implements(plugins.IClick)

    # IConfigurer

    def update_config(self, config_: Any) -> None:
        tk.add_template_directory(config_, "templates")
        tk.add_resource("assets", "lakehouse")

    # IConfigDeclaration

    def declare_config_options(self, declaration: Any, key: Any) -> None:
        config.declare(declaration, key)

    # ITemplateHelpers

    def get_helpers(self) -> dict[str, Any]:
        return helpers.get_helpers()

    # IBlueprint

    def get_blueprint(self) -> list[Any]:
        return [dataset]

    # IClick

    def get_commands(self) -> list[Any]:
        return [cli.lakehouse]
