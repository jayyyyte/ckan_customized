#!/usr/bin/env bash
# CKAN 2.12.x prerequisites — run this INSIDE your WSL Ubuntu terminal.
# It needs your sudo password interactively, so it can't be run non-interactively for you.
# Safe to re-run: existing role/database are detected and skipped.
#
# Usage (from a WSL Ubuntu shell):
#   bash /mnt/c/Users/Tlinh/ckan_customized/setup_step1_system.sh
set -euo pipefail

echo "== Installing system packages =="
# Ubuntu 24.04: 'git-core' no longer exists (use 'git'); 'libmagic1' is a virtual
# package resolved to 'libmagic1t64' (64-bit time_t transition).
sudo apt update
sudo apt install -y python3-dev libpq-dev python3-pip python3-venv \
    git redis-server libmagic1t64 postgresql postgresql-contrib

echo "== Enabling Postgres + Redis =="
sudo systemctl enable --now postgresql
sudo systemctl enable --now redis-server

echo "== Creating CKAN working dirs under your home (no sudo needed) =="
# Layout (see docs/phase-1-local-source.md): venv ~/ckan/default, config ~/ckan/etc, uploads ~/ckan/storage
mkdir -p "$HOME/ckan/etc" "$HOME/ckan/storage"

echo "== Creating Postgres role + database for CKAN =="
# Run psql from a dir the postgres user can read, to avoid "could not change directory" noise.
cd /tmp
pg_exists() { sudo -u postgres psql -tAc "$1" | grep -q 1; }

if pg_exists "SELECT 1 FROM pg_roles WHERE rolname='ckan_default'"; then
  echo "Role ckan_default already exists — skipping"
else
  # Prompts you to set a password for the ckan_default DB role.
  sudo -u postgres createuser -S -D -R -P ckan_default
fi

if pg_exists "SELECT 1 FROM pg_database WHERE datname='ckan_default'"; then
  echo "Database ckan_default already exists — skipping"
else
  sudo -u postgres createdb -O ckan_default ckan_default -E utf-8
fi

echo "== Verifying =="
pg_isready
redis-cli ping

echo "== Done. Postgres (DB ckan_default), Redis, ~/ckan/etc and ~/ckan/storage are ready. =="
echo "Remember the ckan_default DB password you just set — it goes into ckan.ini next."
