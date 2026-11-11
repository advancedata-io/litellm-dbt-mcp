# Our own Gateway in front of the Managed LiteLLM, with dbt-mcp over stdio and calls run one at a time

Callers are apps, scripts and notebooks on other machines, and they want model calls and Metadata tools behind one endpoint. We cannot change the Managed LiteLLM, so we run our own LiteLLM (the Gateway) on a Shared host. The Gateway forwards `gpt-5.6-sol` to the Managed LiteLLM through the `litellm_proxy/` provider, and it runs the `/v1/responses` MCP tool loop itself. The Managed LiteLLM therefore only ever sees plain function tools. dbt-mcp is registered as a stdio server and launched directly from a pre-installed, pinned package, with `max_concurrent_requests: 1`.

> **Partly superseded by [ADR 0003](0003-dbt-mcp-long-lived-local-http.md):** dbt-mcp now runs as one long-lived process over local HTTP, not stdio.

## Considered Options

- **No Gateway, IDE agents start dbt-mcp themselves**: rejected. Our Callers are programs, not IDE agents.
- **dbt-mcp as its own HTTP service**: rejected. dbt documents that transport for debugging only, it has no authentication, and it would be one more service to run.
- **Ask the Managed LiteLLM team to host dbt-mcp**: rejected. It depends on their roadmap, and they would need our dbt project on their host.
- **`uvx dbt-mcp`**: rejected. uvx resolves the package on every spawn.

## Consequences

- LiteLLM starts a new stdio process for every tool call and never keeps one running (`MCPClient.run_with_session`). Each call also runs `dbt parse`, which writes `target/manifest.json`. dbt-mcp's own lock only works within one process, so we serialise at the LiteLLM level. Bursts of calls queue up. That is acceptable for best-effort internal tooling.
- `dbt-mcp` is not on LiteLLM's default stdio allowlist, so the Gateway sets `LITELLM_MCP_STDIO_EXTRA_COMMANDS=dbt-mcp`.
- The Managed LiteLLM sees one key for all our usage. Callers still share our master key, so there is no per-Caller attribution yet.
- The Gateway has a Postgres database. We added it for LiteLLM's Admin UI, whose login needs one, so the original "no database" choice no longer holds. Prisma's client and engines are generated when the image is built, and migrations run at start. Per-Caller virtual keys are now possible but not yet used.
