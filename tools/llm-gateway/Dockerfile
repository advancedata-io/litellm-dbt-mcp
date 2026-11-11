# Gateway image: LiteLLM + dbt-mcp + dbt, each in its own venv.
# Separate venvs because dbt-mcp 2.10.1 pins mcp==1.30.0 while litellm 1.109 needs mcp>=2.3.
# They only talk over local HTTP / subprocess, so isolation costs nothing.
FROM python:3.12-slim-bookworm

COPY --from=ghcr.io/astral-sh/uv:0.6.5 /uv /usr/local/bin/uv
# Node runs the Prisma CLI (generate at build, migrate deploy at start); openssl for its engines.
RUN apt-get update \
 && apt-get install -y --no-install-recommends nodejs npm openssl \
 && rm -rf /var/lib/apt/lists/*
# One HOME for build and runtime, so Prisma's cache (node, CLI, engines) from the build is reused.
ENV HOME=/opt/home \
    UV_LINK_MODE=copy \
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
# Generate the Prisma client and fetch the engines now, not on every container start.
RUN PATH=/opt/envs/litellm/.venv/bin:$PATH \
    prisma generate --schema /opt/envs/litellm/.venv/lib/python3.12/site-packages/litellm/proxy/schema.prisma \
 && chmod -R a+rwX /opt/home

COPY profiles/ /opt/gateway/profiles/
COPY config.yaml models.yaml entrypoint.sh dbt-skip-fresh-parse.sh /opt/gateway/
RUN chmod 0755 /opt/gateway/entrypoint.sh /opt/gateway/dbt-skip-fresh-parse.sh

# Runs as the UID that owns the Project checkout (set in docker-compose.yml).
ENV PATH=/opt/envs/litellm/.venv/bin:$PATH
EXPOSE 4000
ENTRYPOINT ["/opt/gateway/entrypoint.sh"]
