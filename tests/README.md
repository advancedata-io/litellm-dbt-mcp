# Tests

## Mock Managed LiteLLM (`mock_managed/`)

A fake, stdlib-only, OpenAI-compatible upstream, which stands in for the Managed LiteLLM. It serves
`/responses`, `/chat/completions` and `/models`, each both with and without the `/v1` prefix, on `0.0.0.0:8080`.
It also serves `/health`, which needs no key. It checks `Authorization: Bearer $MOCK_KEY` and writes every request body to stdout as JSON.

- If the request offers the lineage tool (`dbt-get_lineage_dev`, or any name ending in `get_lineage_dev`) and contains no tool result yet, the mock answers with a single call to it for `model.dbt_dwh.fct_orders`.
- If a tool result is present, the mock answers with text that quotes the first 500 characters of that result.

To start the Gateway against the mock, run this from the repo root:

```sh
docker compose -f docker-compose.yml -f docker-compose.mock.yml up -d --build
docker compose logs -f mock-managed       # see what the Gateway sends upstream
```

`docker-compose.mock.yml` sets the Gateway's upstream to `http://mock-managed:8080` with key `sk-mock`, and the master key to `sk-poc-master`. No `.env` file is needed.

To run the mock on its own: `MOCK_KEY=sk-mock MOCK_PORT=18080 python3 tests/mock_managed/server.py`.

## Smoke test (`smoke_test.py`)

The smoke test needs only the Python standard library (urllib), so plain `python3` runs it. No `openai` package is needed.

```sh
LITELLM_MASTER_KEY=sk-poc-master python3 tests/smoke_test.py
```

It runs these checks, each printed as PASS or FAIL with its timing, and exits with 1 on any failure:

1. `GET /health/liveliness`
2. `GET /mcp-rest/tools/list?server_id=dbt` returns exactly `get_lineage_dev`, `get_node_details_dev` and `list`.
3. `POST /mcp-rest/tools/call` for `list` (`tag:finance`), `get_node_details_dev` (`node_id: fct_orders`, which is a dbt selector, not a unique_id) and `get_lineage_dev` (`model.dbt_dwh.fct_orders`).
4. `POST /v1/responses` with the `dbt` MCP tool (`require_approval: never`): the final text must contain `stg_orders`.

With the mock, check 4 shows that real dbt lineage passed through the Gateway's tool loop. With the real Managed LiteLLM, it depends on what the model answers.

`SMOKE_TIMEOUT` sets the timeout per request in seconds (default 180). Each dbt tool call starts dbt-mcp and runs `dbt parse`/`dbt ls`.
