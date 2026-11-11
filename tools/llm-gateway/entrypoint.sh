#!/bin/sh
# Install dbt packages into the Project checkout, start dbt-mcp, then start the Gateway.
# dbt-mcp runs `dbt parse` / `dbt list` per tool call; both fail without packages.
set -eu

: "${DBT_PROJECT_DIR:?DBT_PROJECT_DIR must be set}"
: "${DBT_PROFILES_DIR:?DBT_PROFILES_DIR must be set}"

echo "[entrypoint] dbt deps in ${DBT_PROJECT_DIR}"
cd "${DBT_PROJECT_DIR}"
/opt/envs/dbt/.venv/bin/dbt deps
# One real parse now, so dbt-mcp's per-call parse can be skipped (dbt-skip-fresh-parse.sh).
/opt/envs/dbt/.venv/bin/dbt parse --quiet

# dbt-mcp stays running (streamable HTTP on 127.0.0.1:8000, its fixed default), so tool
# calls skip its ~8s startup. Restarted if it exits. See ADR 0003.
echo "[entrypoint] starting dbt-mcp on 127.0.0.1:8000"
(
  export MCP_TRANSPORT=streamable-http \
    DBT_PATH=/opt/gateway/dbt-skip-fresh-parse.sh \
    DBT_MCP_ENABLE_TOOLS=get_lineage_dev,get_node_details_dev,list \
    DO_NOT_TRACK=1 \
    DBT_SEND_ANONYMOUS_USAGE_STATS=false \
    DBT_VERSION_CHECK=false
  while true; do
    /opt/envs/dbt-mcp/.venv/bin/dbt-mcp || true
    echo "[entrypoint] dbt-mcp exited, restarting in 2s" >&2
    sleep 2
  done
) &

# Wait until dbt-mcp accepts connections, so LiteLLM finds its tools on the first request.
python3 -c '
import socket, sys, time
for _ in range(120):
    try:
        socket.create_connection(("127.0.0.1", 8000), timeout=1).close()
        sys.exit(0)
    except OSError:
        time.sleep(0.5)
sys.exit("[entrypoint] dbt-mcp did not start within 60s")
'

echo "[entrypoint] starting LiteLLM on :4000"
cd /opt/gateway
exec /opt/envs/litellm/.venv/bin/litellm --config /opt/gateway/config.yaml --host 0.0.0.0 --port 4000
