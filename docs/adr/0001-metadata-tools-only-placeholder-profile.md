# Metadata tools only, with a placeholder warehouse profile

Callers only need to look up models, sources, lineage and node details, so dbt-mcp exposes exactly `get_lineage_dev`, `get_node_details_dev` and `list` (via `DBT_MCP_ENABLE_TOOLS`) and nothing else: no `run`, `build`, `test` or `show`, and no dbt platform toolsets. Because these tools only need `dbt parse` and `dbt ls`, which read the project's own definitions, the container carries a committed `profiles.yml` with fake ClickHouse connection details (profile `dev`) instead of real credentials. That removes warehouse secrets and the warehouse blast radius from the design entirely.

## Considered Options

- **dbt platform Discovery API**: rejected. It needs the project to run in dbt platform and a service token, and it moves the metadata source outside our host.
- **Real read-only ClickHouse user** (`readonly=2`, which dbt-clickhouse needs because it always sets session settings): rejected for now. It would only protect against a macro or adapter that connects during parse, and it would bring back secret handling.
- **Wider tool set including `show`**: rejected. `show` runs arbitrary SQL against the warehouse.

## Consequences

- If a future tool needs the warehouse, this decision must be revisited: real credentials, a dedicated read-only user, and a fresh look at the blast radius.
- The placeholder profile name must match `profile:` in `dbt_dwh/dbt_project.yml`. If it is renamed there, parse breaks.
- Not yet verified: that `dbt parse` and `dbt ls` with dbt-clickhouse never open a connection. The prototype must confirm this.
