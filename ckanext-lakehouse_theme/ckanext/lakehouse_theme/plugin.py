import ckan.plugins as plugins
import ckan.plugins.toolkit as toolkit
from ckan.lib.plugins import DefaultTranslation

from ckanext.lakehouse_theme import helpers


class LakehouseThemePlugin(plugins.SingletonPlugin, DefaultTranslation):
    plugins.implements(plugins.IConfigurer)
    plugins.implements(plugins.IConfigDeclaration)
    plugins.implements(plugins.ITemplateHelpers)
    plugins.implements(plugins.ITranslation)

    # IConfigurer

    def update_config(self, config_):
        toolkit.add_template_directory(config_, "templates")
        toolkit.add_public_directory(config_, "public")
        toolkit.add_resource("assets", "lakehouse_theme")

    # IConfigDeclaration

    def declare_config_options(self, declaration, key):
        group = key.ckanext.lakehouse_theme
        declaration.declare(group.organization_name, "Lakehouse Data Platform")
        declaration.declare(group.contact_email, "")
        declaration.declare(group.openmetadata_url, "")
        declaration.declare(group.trino_docs_url, "https://trino.io/docs/current/client/jdbc.html")

    # ITemplateHelpers

    def get_helpers(self):
        return {
            "lakehouse_theme_trino_connection": helpers.trino_connection,
            "lakehouse_theme_links": helpers.links,
            "lakehouse_theme_recent_datasets": helpers.recent_datasets,
        }
