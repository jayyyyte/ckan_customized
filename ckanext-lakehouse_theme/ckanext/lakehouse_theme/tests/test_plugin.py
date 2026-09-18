import pytest

import ckan.plugins as plugins


@pytest.mark.ckan_config("ckan.plugins", "lakehouse_theme")
@pytest.mark.usefixtures("with_plugins")
def test_plugin_loaded():
    assert plugins.plugin_loaded("lakehouse_theme")
