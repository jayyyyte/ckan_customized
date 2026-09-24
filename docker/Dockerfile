# Cổng dữ liệu EVN — CKAN 2.11.6 + theme evntheme + DataStore/XLoader.
#
# Build from the repository root (the build context is the repo, not docker/):
#   docker build -f docker/Dockerfile -t ckan-lakehouse:0.1.0 .
#
# Facts about the base image checked on 2026-09-18/22 and written down in
# docs/phase-2-docker-packaging.md: one stage, Python 3.10, APP_DIR=/srv/app,
# SRC_DIR=/srv/app/src, CKAN_INI=/srv/app/ckan.ini, storage /var/lib/ckan,
# runtime user `ckan` (503) while /usr/local belongs to `ckan-sys` (502).
FROM ckan/ckan-base:2.11.6

# 2.5.0 is the last XLoader release whose README lists CKAN 2.11 (checked 2026-09-19),
# and the version running in the local install (setup_step3_datastore.sh).
ARG XLOADER_VERSION=2.5.0

# /usr/local (site-packages) belongs to ckan-sys, the default user is ckan (gotchas 12).
USER root

# Third-party extensions are installed EDITABLE, from source.
# A wheel would land in site-packages/ckanext/, which stays invisible behind the
# *-nspkg.pth files of the editable ckan install: `import ckanext.xloader` then fails
# with ModuleNotFoundError although pip reports success (gotchas 6ak, decision 2026-09-22).
# Installing -e also guarantees templates/assets are read from the source tree (gotchas 15).
RUN git clone --depth 1 --branch "${XLOADER_VERSION}" \
        https://github.com/ckan/ckanext-xloader.git "${SRC_DIR}/ckanext-xloader" && \
    pip3 install --no-cache-dir \
        -e "${SRC_DIR}/ckanext-xloader" \
        -r "${SRC_DIR}/ckanext-xloader/requirements.txt" && \
    chown -R ckan-sys:ckan-sys "${SRC_DIR}/ckanext-xloader"

# The theme. .mo files are not committed (decision log 2026-09-14) and .dockerignore
# keeps the local ones out, so compile the catalogue from .po during the build.
# The CSS is committed already compiled, so the image needs no Node/sass.
COPY --chown=ckan-sys:ckan-sys ckanext-evntheme "${SRC_DIR}/ckanext-evntheme"
RUN pip3 install --no-cache-dir -e "${SRC_DIR}/ckanext-evntheme" && \
    pybabel compile -d "${SRC_DIR}/ckanext-evntheme/ckanext/evntheme/i18n" -D ckanext-evntheme && \
    chown -R ckan-sys:ckan-sys "${SRC_DIR}/ckanext-evntheme" && \
    pip3 check && \
    python3 -c "import ckanext.evntheme, ckanext.xloader"

# Startup hooks of the web container: start_ckan.sh sources /docker-entrypoint.d/*.sh
# after prerun.py. The worker container has its own entrypoint (it must not run prerun).
COPY --chown=ckan-sys:ckan-sys docker/docker-entrypoint.d/ /docker-entrypoint.d/
COPY --chown=ckan-sys:ckan-sys docker/worker-entrypoint.sh /srv/app/worker-entrypoint.sh
RUN chmod 0755 /srv/app/worker-entrypoint.sh /docker-entrypoint.d/*.sh

# Same plugin list as the local install, plus envvars last (it must load last to win).
ENV CKAN__PLUGINS="evntheme activity tracking datastore xloader text_view image_view datatables_view envvars"
# Write the list into the image's ini as well. prerun.py applies CKAN__PLUGINS only in the
# web container; ckan.plugins is read before plugins load, so the envvars plugin cannot
# switch plugins on by itself. Without this the worker would run stock CKAN.
RUN ckan config-tool "${CKAN_INI}" "ckan.plugins = ${CKAN__PLUGINS}"

USER ckan
