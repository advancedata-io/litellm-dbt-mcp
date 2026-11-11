#!/bin/sh
# Pull the Project checkout and restart the Gateway (re-runs dbt deps).
set -eu
cd "$(dirname "$0")"
git pull --ff-only
docker compose up -d --build --force-recreate gateway
