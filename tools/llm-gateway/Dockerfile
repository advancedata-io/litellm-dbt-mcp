# Gateway image: LiteLLM + dbt-mcp + dbt, each in its own venv.
# Separate venvs because dbt-mcp 2.10.1 pins mcp==1.30.0 while litellm 1.109 needs mcp>=2.3.
# They only talk via stdio / subprocess, so isolation costs nothing.
FROM python:3.12-slim-bookworm

COPY --from=ghcr.io/astral-sh/uv:0.6.5 /uv /usr/local/bin/uv
ENV UV_LINK_MODE=copy \
    UV_COMPILE_BYTECODE=1 \
    UV_PYTHON_DOWNLOADS=never \
    UV_PYTHON=/usr/local/bin/python3.12

# Lockfiles first, so code/config changes don't bust the dependency layers.
COPY envs/dbt/pyproject.toml envs/dbt/uv.lock /opt/envs/dbt/
RUN uv sync --frozen --no-cache --project /opt/envs/dbt
COPY envs/dbt-mcp/pyproject.toml envs/dbt-mcp/uv.lock /opt/envs/dbt-mcp/
RUN uv sync --frozen --no-cache --project /opt/envs/dbt-mcp
COPY envs/litellm/pyproject.toml envs/litellm/uv.lock /opt/envs/litellm/
RUN uv sync --frozen --no-cache --project /opt/envs/litellm

COPY profiles/ /opt/gateway/profiles/
COPY config.yaml entrypoint.sh /opt/gateway/
RUN chmod 0755 /opt/gateway/entrypoint.sh

# Runs as the UID that owns the Project checkout (set in docker-compose.yml).
ENV HOME=/tmp
EXPOSE 4000
ENTRYPOINT ["/opt/gateway/entrypoint.sh"]
