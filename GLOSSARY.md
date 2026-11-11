# dbt tools behind LiteLLM

Our team's way of offering dbt tools (via dbt-mcp) to apps, scripts and notebooks, alongside model calls that are forwarded to another team's LiteLLM.

## Language

**Gateway**:
The LiteLLM instance our team runs on a shared host, serving both model calls and dbt tools to callers.
_Avoid_: our proxy, llm-gateway, MCP gateway, local LiteLLM

**Managed LiteLLM**:
The LiteLLM instance run by another team at a shared internal URL; the Gateway forwards all model calls to it and we cannot change its configuration.
_Avoid_: upstream proxy, the other proxy, local LiteLLM

**Shared host**:
The single on-premises machine where the Gateway runs for the whole team; Callers reach it over the network.
_Avoid_: local, the server, the box

**Devcontainer**:
The development environment in which we build and test the Gateway; it runs the same image as the Shared host, plus tooling.
_Avoid_: local, dev box

**Caller**:
An app, script or notebook that sends requests to the Gateway; the first and primary consumer of Metadata tools.
_Avoid_: client, user, consumer

## dbt

**Metadata tools**:
The only dbt tools the Gateway exposes: read-only lookups of models, sources, lineage and node details derived from the dbt project's own definitions, never from the warehouse.
_Avoid_: discovery, Discovery API, dbt tools (too broad)

**Discovery API**:
dbt platform's hosted metadata service; explicitly not used here. Named only so it is not confused with Metadata tools.

**Project checkout**:
A dedicated copy of the monorepo on the Shared host that belongs to the Gateway alone; dbt-mcp may write into it, and it changes only when someone pulls manually.
_Avoid_: repo, the project, workspace, monorepo (the monorepo is the source; the Project checkout is our copy of it)
