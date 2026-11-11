# Gateway PoC: dbt Metadata tools behind LiteLLM

A LiteLLM **Gateway** that serves dbt **Metadata tools** to Callers and forwards model calls to the **Managed LiteLLM**.
The design is in [docs/](docs/Local%20dbt%20MCP%20behind%20LiteLLM.html) and [docs/adr/](docs/adr/). The vocabulary is in [GLOSSARY.md](GLOSSARY.md).

PoC scope: no TLS and a shared master key. Postgres backs the Admin UI. ClickHouse is never contacted (ADR 0001).

## Layout

```
docker-compose.yml          Gateway + Postgres (the real setup)
docker-compose.mock.yml     override: mock Managed LiteLLM + fake keys (PoC)
docker-compose.vertex.yml   override: Gemini on Vertex AI via a GCP service account
refresh.sh                  git pull --ff-only, then recreate the Gateway
dbt_dwh/                    sample dbt project (stand-in for the monorepo's dbt_dwh/)
tools/llm-gateway/
  Dockerfile                three venvs: litellm, dbt-mcp, dbt
  envs/{litellm,dbt-mcp,dbt}/  pyproject.toml + uv.lock per venv
  config.yaml               MCP server "dbt" (HTTP, 127.0.0.1:8000); includes models.yaml
  models.yaml               model gpt-5.6-sol (Managed LiteLLM)
  models.vertex.yaml        model gemini (Vertex AI), see docker-compose.vertex.yml
  profiles/profiles.yml     placeholder ClickHouse profile "dev"
  entrypoint.sh             dbt deps, dbt-mcp (kept running), then litellm
  .env.example              secrets template for the real setup
tests/                      mock Managed LiteLLM + smoke test
```

Why three venvs: dbt-mcp 2.10.1 pins `mcp==1.30.0`, while litellm 1.109 needs `mcp>=2.3`. They only talk over local HTTP, so keeping them apart costs nothing.

## Run the PoC (mock upstream)

```sh
docker compose -f docker-compose.yml -f docker-compose.mock.yml up -d --build
LITELLM_MASTER_KEY=sk-poc-master python3 tests/smoke_test.py   # 6 checks, ~1 min
```

## Run against the real Managed LiteLLM

```sh
cp tools/llm-gateway/.env.example tools/llm-gateway/.env   # fill in URL, key, master key
docker compose up -d --build
```

On the Shared host, run this from the root of the Project checkout, which is a dedicated read-write copy of the monorepo.
Set `PROJECT_CHECKOUT` if the compose file lives somewhere else, and `GATEWAY_UID`/`GATEWAY_GID` if the checkout isn't owned by 1000:1000.
After pulling new commits, run `./refresh.sh`. It recreates the container, and the entrypoint runs `dbt deps` again.

## Run against Gemini on Vertex AI

Uses a GCP service account (role `roles/aiplatform.user`) instead of the Managed LiteLLM. Callers use model `gemini`.

```sh
export GCP_SA_KEY_FILE=/path/to/service-account.json   # readable by GATEWAY_UID, never commit it
export VERTEX_PROJECT=<gcp-project-id> VERTEX_MODEL=vertex_ai/<gemini model ID>   # VERTEX_LOCATION defaults to global
docker compose -f docker-compose.yml -f docker-compose.vertex.yml up -d --build
```

## Admin UI

Open `http://<host>:4000/ui`. Log in with username `admin` and the master key as password (`sk-poc-master` with the mock override).
The UI stores its data in the `db` service (Postgres 16, volume `gateway-db`, not published to the host).
Set `POSTGRES_PASSWORD` in your shell or in a root `.env` to override the PoC default `litellm-poc`.

## Calling it

```python
from openai import OpenAI
client = OpenAI(base_url="http://<shared-host>:4000/v1", api_key="<master key>")
r = client.responses.create(
    model="gpt-5.6-sol",
    input="Which models feed fct_orders?",
    tools=[{"type": "mcp", "server_label": "dbt",
            "server_url": "litellm_proxy/mcp/dbt", "require_approval": "never"}],
)
print(r.output_text)
```

You can also call the tools directly:
- `GET /mcp-rest/tools/list`
- `POST /mcp-rest/tools/call` with `{"server_id": "dbt", "name": "get_lineage_dev", "arguments": {"unique_id": "model.dbt_dwh.fct_orders"}}`

## Exposed tools

| Tool | What it does |
|---|---|
| `list` | `dbt list` with a selector, e.g. `tag:finance` |
| `get_lineage_dev` | parents and children of a node, from the local manifest |
| `get_node_details_dev` | description, columns, path, config of a node; `node_id` is a dbt selector (`fct_orders`), not a unique_id |

## Known limits (PoC)

- **Slow calls:** each tool call takes about 10–15 s. LiteLLM starts a new dbt-mcp process per call, and every call runs `dbt parse`. Calls run one at a time (`max_concurrent_requests: 1`).
- **Shared admin key:** the master key is LiteLLM's admin key, it is shared with every Caller, and it is sent over plain HTTP.
- **One tool round per request:** the Gateway runs one round of tool calls per `/v1/responses` request. If the model asks for a second tool, that call goes back to the Caller unexecuted.
- **Follow-up call may fail upstream:** the follow-up call to the Managed LiteLLM carries `previous_response_id`. If the Managed LiteLLM can't resolve it, Callers should send `store: false`. This is untested against the real instance.
- **Startup needs the network:** `dbt deps` runs at start, so the container needs to reach hub.getdbt.com.
