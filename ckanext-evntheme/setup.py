from setuptools import setup

# Project metadata lives in pyproject.toml; setup.py only carries the Babel
# extraction map, which pyproject.toml cannot express yet
# (https://github.com/ckan/ckan/issues/8382).
setup(
    message_extractors={
        "ckanext": [
            ("**.py", "python", None),
            ("**.js", "javascript", None),
            ("**/templates/**.html", "ckan", None),
        ],
    }
)
