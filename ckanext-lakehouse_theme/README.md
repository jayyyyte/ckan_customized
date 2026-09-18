[![Tests](https://github.com/jayyyyte/ckanext-lakehouse_theme/workflows/Tests/badge.svg?branch=main)](https://github.com/jayyyyte/ckanext-lakehouse_theme/actions)

# ckanext-lakehouse_theme

Theme for the Lakehouse CKAN data portal, built on the CKAN 2.11 classic templates
(Bootstrap 5): brand header and footer, home page hero with site statistics and the
newest datasets, a "How to connect" box on `jdbc:trino://` resources, and Vietnamese
translations for strings the core `vi` catalog is missing.


## Requirements

Compatibility with core CKAN versions:

| CKAN version    | Compatible?   |
| --------------- | ------------- |
| 2.10 and earlier | not tested   |
| 2.11            | yes (targets 2.11.6, classic templates) |
| 2.12            | not tested (the CSS targets the 2.11 classic markup and Bootstrap 5.1) |


## Installation

**TODO:** Add any additional install steps to the list below.
   For example installing any non-Python dependencies or adding any required
   config settings.

To install ckanext-lakehouse_theme:

1. Activate your CKAN virtual environment, for example:

     . /usr/lib/ckan/default/bin/activate

2. Clone the source and install it on the virtualenv

    git clone https://github.com/jayyyyte/ckanext-lakehouse_theme.git
    cd ckanext-lakehouse_theme
    pip install -e .
	pip install -r requirements.txt

3. Add `lakehouse_theme` to the `ckan.plugins` setting in your CKAN
   config file (by default the config file is located at
   `/etc/ckan/default/ckan.ini`).

4. Restart CKAN. For example if you've deployed CKAN with Apache on Ubuntu:

     sudo service apache2 reload


## Config settings

None at present

**TODO:** Document any optional config settings here. For example:

	# The minimum number of hours to wait before re-checking a resource
	# (optional, default: 24).
	ckanext.lakehouse_theme.some_setting = some_default_value


## Developer installation

To install ckanext-lakehouse_theme for development, activate your CKAN virtualenv and
do:

    git clone https://github.com/jayyyyte/ckanext-lakehouse_theme.git
    cd ckanext-lakehouse_theme
    pip install -e .
    pip install -r dev-requirements.txt


## Tests

To run the tests, do:

    pytest --ckan-ini=test.ini


## Releasing a new version of ckanext-lakehouse_theme

If ckanext-lakehouse_theme should be available on PyPI you can follow these steps to publish a new version:

1. Update the version number in the `pyproject.toml` file. See [PEP 440](http://legacy.python.org/dev/peps/pep-0440/#public-version-identifiers) for how to choose version numbers.

2. Make sure you have the latest version of necessary packages:

    pip install --upgrade setuptools wheel twine

3. Create a source and binary distributions of the new version:

       python -m build && twine check dist/*

   Fix any errors you get.

4. Upload the source distribution to PyPI:

       twine upload dist/*

5. Commit any outstanding changes:

       git commit -a
       git push

6. Tag the new release of the project on GitHub with the version number from
   the `setup.py` file. For example if the version number in `setup.py` is
   0.0.1 then do:

       git tag 0.0.1
       git push --tags

## License

[AGPL](https://www.gnu.org/licenses/agpl-3.0.en.html)
