# dbt-mcp as one long-lived process over local HTTP, inside the Gateway container

Supersedes the stdio part of ADR 0002. With stdio, LiteLLM started a new dbt-mcp for every MCP operation, and a single question needs several (list tools, call a tool, list again). Each start took about 8.4s, so one question with one tool call took over 70s, mostly spent starting dbt-mcp. The entrypoint now starts dbt-mcp once with `MCP_TRANSPORT=streamable-http`, and LiteLLM connects to `http://127.0.0.1:8000/mcp` (`transport: "http"`). The entrypoint restarts dbt-mcp if it exits.

## Considered Options

- **Keep stdio**: rejected. The startup cost is paid several times per question.
- **dbt-mcp in its own container**: rejected for now. dbt-mcp 2.10.1 always binds 127.0.0.1:8000 (no host setting) and has no authentication. Reaching it from another container would need a patch to bind elsewhere, and it would be one more service to run.

## Consequences

- dbt-mcp listens only on the container's loopback, so it is not reachable from the compose network or the host. This answers ADR 0002's "no authentication" concern: only LiteLLM, which checks keys, can reach it.
- It runs in the same container but is not a separate service: no extra compose entry. If it crashes, the entrypoint loop restarts it within a few seconds. Calls during that window fail.
- Each tool call still runs `dbt parse`. Calls stay serialised with `max_concurrent_requests: 1`, and dbt-mcp's own in-process lock now also applies, because there is one process.
- LiteLLM's stdio settings (`LITELLM_ENABLE_MCP_STDIO`, `LITELLM_MCP_STDIO_EXTRA_COMMANDS`) are no longer needed.
