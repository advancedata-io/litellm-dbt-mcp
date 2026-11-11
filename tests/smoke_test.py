#!/usr/bin/env python3
"""Smoke test for the Gateway. Stdlib only (urllib); run with plain `python3`.

Env:
  GATEWAY_URL          default http://localhost:4000
  LITELLM_MASTER_KEY   required
  SMOKE_TIMEOUT        per-request timeout in seconds, default 180
                       (each dbt tool call spawns dbt-mcp and runs dbt parse/ls)

Exit code 0 when every check passes, 1 otherwise.
"""

from __future__ import annotations

import json
import os
import sys
import time
import urllib.error
import urllib.request
from collections.abc import Callable

GATEWAY_URL = os.environ.get("GATEWAY_URL", "http://localhost:4000").rstrip("/")
MASTER_KEY = os.environ.get("LITELLM_MASTER_KEY", "")
TIMEOUT = float(os.environ.get("SMOKE_TIMEOUT", "180"))
MODEL = "gpt-5.6-sol"
SERVER = "dbt"
EXPECTED_TOOLS = {"get_lineage_dev", "get_node_details_dev", "list"}
TARGET = "model.dbt_dwh.fct_orders"


class CheckFailed(Exception):
    pass


def request(method: str, path: str, body: dict | None = None) -> tuple[int, object]:
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(f"{GATEWAY_URL}{path}", data=data, method=method)
    req.add_header("Authorization", f"Bearer {MASTER_KEY}")
    if data is not None:
        req.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
            status, raw = resp.status, resp.read()
    except urllib.error.HTTPError as err:
        status, raw = err.code, err.read()
    try:
        return status, json.loads(raw)
    except json.JSONDecodeError:
        return status, raw.decode(errors="replace")


def expect_ok(status: int, payload: object) -> None:
    if status != 200:
        raise CheckFailed(f"HTTP {status}: {short(payload)}")


def short(value: object, limit: int = 400) -> str:
    text = value if isinstance(value, str) else json.dumps(value)
    return text if len(text) <= limit else text[:limit] + "..."


def bare(name: str) -> str:
    """LiteLLM may prefix MCP tool names with `<server><MCP_TOOL_PREFIX_SEPARATOR>` (default `-`)."""
    return name.split("-", 1)[1] if name.startswith(f"{SERVER}-") else name


# --------------------------------------------------------------------------- checks


def check_liveliness() -> str:
    status, payload = request("GET", "/health/liveliness")
    expect_ok(status, payload)
    return short(payload, 80)


def check_tools_list() -> str:
    status, payload = request("GET", f"/mcp-rest/tools/list?server_id={SERVER}")
    expect_ok(status, payload)
    if not isinstance(payload, dict) or not isinstance(payload.get("tools"), list):
        raise CheckFailed(f"unexpected payload: {short(payload)}")
    if payload.get("error"):
        raise CheckFailed(f"error: {payload.get('error')} {payload.get('message')}")
    names = [t.get("name", "") for t in payload["tools"]]
    found = {bare(n) for n in names}
    if len(names) != len(EXPECTED_TOOLS) or found != EXPECTED_TOOLS:
        raise CheckFailed(f"expected exactly {sorted(EXPECTED_TOOLS)}, got {names}")
    return f"tools: {names}"


def call_tool(name: str, arguments: dict) -> str:
    """POST /mcp-rest/tools/call and return the joined text content. Retries with the prefixed name."""
    last = ""
    for candidate in (name, f"{SERVER}-{name}"):
        status, payload = request("POST", "/mcp-rest/tools/call", {"server_id": SERVER, "name": candidate, "arguments": arguments})
        if status != 200 or not isinstance(payload, dict):
            last = f"{candidate}: HTTP {status}: {short(payload)}"
            continue
        if payload.get("isError") or payload.get("is_error"):
            raise CheckFailed(f"tool returned isError: {short(payload)}")
        content = payload.get("content") or []
        text = " ".join(str(c.get("text", "")) for c in content if isinstance(c, dict))
        if not text and payload.get("structuredContent") is not None:
            text = json.dumps(payload["structuredContent"])
        return text or json.dumps(payload)
    raise CheckFailed(last)


def expect_in(text: str, *needles: str) -> None:
    missing = [n for n in needles if n not in text]
    if missing:
        raise CheckFailed(f"missing {missing} in: {short(text)}")


def check_call_list() -> str:
    text = call_tool("list", {"node_selection": "tag:finance"})
    expect_in(text, "fct_orders")
    return short(text, 160)


def check_call_node_details() -> str:
    # node_id is a dbt selector (it runs `dbt list --select`), not a unique_id
    text = call_tool("get_node_details_dev", {"node_id": "fct_orders"})
    expect_in(text, "fct_orders")
    return short(text, 160)


def check_call_lineage() -> str:
    text = call_tool("get_lineage_dev", {"unique_id": TARGET})
    expect_in(text, "fct_orders", "stg_orders")
    return short(text, 160)


def check_responses_mcp() -> str:
    body = {
        "model": MODEL,
        "input": "Which models feed fct_orders?",
        "tools": [{"type": "mcp", "server_label": SERVER, "server_url": f"litellm_proxy/mcp/{SERVER}", "require_approval": "never"}],
    }
    status, payload = request("POST", "/v1/responses", body)
    expect_ok(status, payload)
    if not isinstance(payload, dict):
        raise CheckFailed(f"unexpected payload: {short(payload)}")
    output = payload.get("output") or []
    types = [item.get("type") for item in output if isinstance(item, dict)]
    texts = [
        part.get("text", "")
        for item in output
        if isinstance(item, dict) and item.get("type") == "message"
        for part in item.get("content") or []
        if isinstance(part, dict)
    ]
    final = " ".join(texts)
    if "function_call" in types and not final:
        raise CheckFailed(f"Gateway returned the tool call instead of running it (output types {types})")
    expect_in(final, "stg_orders")
    return f"output types {types}; text: {short(final, 160)}"


CHECKS: list[tuple[str, Callable[[], str]]] = [
    ("a. GET /health/liveliness", check_liveliness),
    ("b. GET /mcp-rest/tools/list exactly 3 tools", check_tools_list),
    ("c1. tools/call list tag:finance", check_call_list),
    ("c2. tools/call get_node_details_dev", check_call_node_details),
    ("c3. tools/call get_lineage_dev", check_call_lineage),
    ("d. POST /v1/responses with MCP tool", check_responses_mcp),
]


def main() -> int:
    if not MASTER_KEY:
        print("LITELLM_MASTER_KEY is not set", file=sys.stderr)
        return 2
    print(f"Gateway: {GATEWAY_URL}")
    failures = 0
    for label, check in CHECKS:
        start = time.monotonic()
        try:
            detail, ok = check(), True
        except CheckFailed as err:
            detail, ok = str(err), False
        except Exception as err:  # noqa: BLE001 - report anything (timeouts, connection refused) as a failure
            detail, ok = f"{type(err).__name__}: {err}", False
        elapsed = time.monotonic() - start
        failures += not ok
        print(f"{'PASS' if ok else 'FAIL'} {label} ({elapsed:.1f}s) {detail}", flush=True)
    print(f"{len(CHECKS) - failures}/{len(CHECKS)} passed")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
