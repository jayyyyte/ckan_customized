#!/usr/bin/env bash
# CKAN 2.12.x prerequisites — run this INSIDE your WSL Ubuntu terminal.
# It needs your sudo password interactively, so it can't be run non-interactively for you.
#
# Usage (from a WSL Ubuntu shell):
#   bash /mnt/c/Users/Tlinh/ckan_customized/setup_step1_system.sh
set -euo pipefail

echo "== Installing system packages =="
sudo apt update
sudo apt install -y python3-dev libpq-dev python3-pip python3-venv \
    git-core redis-server libmagic1 postgresql postgresql-contrib

echo "== Enabling Postgres + Redis =="
sudo systemctl enable --now postgresql
sudo systemctl enable --now redis-server

echo "== Creating CKAN working dirs under your home (no sudo needed) =="
# Layout (see docs/phase-1-local-source.md): venv ~/ckan/default, config ~/ckan/etc, uploads ~/ckan/storage
mkdir -p "$HOME/ckan/etc" "$HOME/ckan/storage"

echo "== Creating Postgres role + database for CKAN =="
# Prompts you to set a password for the ckan_default DB role.
sudo -u postgres createuser -S -D -R -P ckan_default
sudo -u postgres createdb -O ckan_default ckan_default -E utf-8

echo "== Done. Postgres, Redis, and /usr/lib/ckan/default are ready. =="
echo "Remember the ckan_default DB password you just set — it goes into ckan.ini next."
