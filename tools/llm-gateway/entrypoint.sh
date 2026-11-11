#!/bin/sh
# Install dbt packages into the Project checkout, then start the Gateway.
# dbt-mcp runs `dbt parse` / `dbt list` per tool call; both fail without packages.
set -eu

: "${DBT_PROJECT_DIR:?DBT_PROJECT_DIR must be set}"
: "${DBT_PROFILES_DIR:?DBT_PROFILES_DIR must be set}"

echo "[entrypoint] dbt deps in ${DBT_PROJECT_DIR}"
cd "${DBT_PROJECT_DIR}"
/opt/envs/dbt/.venv/bin/dbt deps

echo "[entrypoint] starting LiteLLM on :4000"
cd /opt/gateway
exec /opt/envs/litellm/.venv/bin/litellm --config /opt/gateway/config.yaml --host 0.0.0.0 --port 4000
