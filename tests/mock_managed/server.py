"""Fake Managed LiteLLM for the Gateway PoC. Stdlib only.

The Gateway reaches its upstream through the `litellm_proxy/` provider. For
/v1/responses LiteLLM uses LiteLLMProxyResponsesAPIConfig, which posts to
`{api_base}/responses` natively; chat completions go to `{api_base}/chat/completions`.
Whether api_base ends in /v1 depends on MANAGED_LITELLM_URL, so every route is
served both with and without the /v1 prefix.

Behaviour (non-streaming by default, minimal SSE when "stream": true):
- tools offered that include the dbt lineage tool, no tool result yet
  -> one function/tool call to that tool for model.dbt_dwh.fct_orders
- a tool result is present
  -> final text quoting the first 500 chars of that result
- otherwise -> a fixed text answer

Every request body is logged to stdout as one JSON line.
"""

from __future__ import annotations

import json
import os
import sys
import time
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

MODEL_ID = "gpt-5.6-sol"
LINEAGE_TOOL = "get_lineage_dev"
TARGET_NODE = "model.dbt_dwh.fct_orders"
QUOTE_CHARS = 500
MOCK_KEY = os.environ.get("MOCK_KEY", "")


def log(event: str, **fields: object) -> None:
    print(json.dumps({"ts": time.time(), "event": event, **fields}, default=str), flush=True)


def new_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:24]}"


def as_text(value: object) -> str:
    """Tool output may be a string or a list of content parts."""
    if isinstance(value, str):
        return value
    if isinstance(value, list):
        parts = []
        for part in value:
            if isinstance(part, dict):
                parts.append(str(part.get("text", part.get("output", json.dumps(part)))))
            else:
                parts.append(str(part))
        return " ".join(parts)
    return json.dumps(value)


def lineage_tool_name(names: list[str]) -> str | None:
    """Gateway prefixes MCP tool names with the server name (e.g. `dbt-get_lineage_dev`)."""
    for name in names:
        if name == LINEAGE_TOOL or name.endswith(LINEAGE_TOOL):
            return name
    return None


def final_text(tool_output: str | None, offered: list[str]) -> str:
    if tool_output is not None:
        return f"Mock answer based on the dbt tool result. Tool result (first {QUOTE_CHARS} chars): {tool_output[:QUOTE_CHARS]}"
    if offered:
        return f"Mock answer. Offered tools did not include {LINEAGE_TOOL}: {', '.join(offered)}"
    return "Mock answer. No tools were offered."


# --------------------------------------------------------------------------- /responses


def responses_tool_names(body: dict) -> list[str]:
    names = []
    for tool in body.get("tools") or []:
        if not isinstance(tool, dict):
            continue
        name = tool.get("name") or (tool.get("function") or {}).get("name")
        if tool.get("type") == "function" and name:
            names.append(name)
    return names


def responses_tool_output(body: dict) -> str | None:
    items = body.get("input")
    if not isinstance(items, list):
        return None
    outputs = [as_text(i.get("output")) for i in items if isinstance(i, dict) and i.get("type") == "function_call_output"]
    return "\n".join(outputs) if outputs else None


def responses_reply(body: dict) -> dict:
    offered = responses_tool_names(body)
    tool_output = responses_tool_output(body)
    tool = lineage_tool_name(offered)
    if tool and tool_output is None:
        output = [
            {
                "type": "function_call",
                "id": new_id("fc"),
                "call_id": new_id("call"),
                "name": tool,
                "arguments": json.dumps({"unique_id": TARGET_NODE}),
                "status": "completed",
            }
        ]
    else:
        output = [
            {
                "type": "message",
                "id": new_id("msg"),
                "role": "assistant",
                "status": "completed",
                "content": [{"type": "output_text", "text": final_text(tool_output, offered), "annotations": []}],
            }
        ]
    return {
        "id": new_id("resp"),
        "object": "response",
        "created_at": int(time.time()),
        "status": "completed",
        "model": body.get("model", MODEL_ID),
        "output": output,
        "parallel_tool_calls": bool(body.get("parallel_tool_calls", True)),
        "tool_choice": body.get("tool_choice") or "auto",
        "tools": body.get("tools") or [],
        "previous_response_id": body.get("previous_response_id"),
        "error": None,
        "incomplete_details": None,
        "usage": {
            "input_tokens": 10,
            "input_tokens_details": {"cached_tokens": 0},
            "output_tokens": 10,
            "output_tokens_details": {"reasoning_tokens": 0},
            "total_tokens": 20,
        },
    }


def responses_sse(reply: dict) -> list[tuple[str, dict]]:
    in_progress = {**reply, "status": "in_progress", "output": []}
    events: list[tuple[str, dict]] = [
        ("response.created", {"type": "response.created", "response": in_progress}),
    ]
    for index, item in enumerate(reply["output"]):
        events.append(("response.output_item.added", {"type": "response.output_item.added", "output_index": index, "item": item}))
        if item["type"] == "message":
            text = item["content"][0]["text"]
            events.append(
                (
                    "response.output_text.delta",
                    {"type": "response.output_text.delta", "item_id": item["id"], "output_index": index, "content_index": 0, "delta": text},
                )
            )
            events.append(
                (
                    "response.output_text.done",
                    {"type": "response.output_text.done", "item_id": item["id"], "output_index": index, "content_index": 0, "text": text},
                )
            )
        events.append(("response.output_item.done", {"type": "response.output_item.done", "output_index": index, "item": item}))
    events.append(("response.completed", {"type": "response.completed", "response": reply}))
    return events


# --------------------------------------------------------------------------- /chat/completions


def chat_tool_names(body: dict) -> list[str]:
    names = []
    for tool in body.get("tools") or []:
        if isinstance(tool, dict):
            name = (tool.get("function") or {}).get("name") or tool.get("name")
            if name:
                names.append(name)
    return names


def chat_tool_output(body: dict) -> str | None:
    outputs = [as_text(m.get("content")) for m in body.get("messages") or [] if isinstance(m, dict) and m.get("role") == "tool"]
    return "\n".join(outputs) if outputs else None


def chat_reply(body: dict) -> dict:
    offered = chat_tool_names(body)
    tool_output = chat_tool_output(body)
    tool = lineage_tool_name(offered)
    if tool and tool_output is None:
        message = {
            "role": "assistant",
            "content": None,
            "tool_calls": [
                {
                    "id": new_id("call"),
                    "type": "function",
                    "function": {"name": tool, "arguments": json.dumps({"unique_id": TARGET_NODE})},
                }
            ],
        }
        finish = "tool_calls"
    else:
        message = {"role": "assistant", "content": final_text(tool_output, offered)}
        finish = "stop"
    return {
        "id": new_id("chatcmpl"),
        "object": "chat.completion",
        "created": int(time.time()),
        "model": body.get("model", MODEL_ID),
        "choices": [{"index": 0, "message": message, "finish_reason": finish}],
        "usage": {"prompt_tokens": 10, "completion_tokens": 10, "total_tokens": 20},
    }


def chat_sse(reply: dict) -> list[dict]:
    choice = reply["choices"][0]
    message = choice["message"]
    delta: dict = {"role": "assistant"}
    if message.get("tool_calls"):
        delta["tool_calls"] = [{"index": i, **tc} for i, tc in enumerate(message["tool_calls"])]
    else:
        delta["content"] = message["content"]
    base = {k: reply[k] for k in ("id", "created", "model")} | {"object": "chat.completion.chunk"}
    return [
        {**base, "choices": [{"index": 0, "delta": delta, "finish_reason": None}]},
        {**base, "choices": [{"index": 0, "delta": {}, "finish_reason": choice["finish_reason"]}], "usage": reply["usage"]},
    ]


# --------------------------------------------------------------------------- HTTP


def route(path: str) -> str:
    path = path.split("?", 1)[0].rstrip("/")
    return path[3:] if path.startswith("/v1/") else path


class Handler(BaseHTTPRequestHandler):
    server_version = "mock-managed/0.1"

    def log_message(self, fmt: str, *args: object) -> None:  # silence default stderr access log
        pass

    def _send_json(self, status: int, payload: dict) -> None:
        data = json.dumps(payload).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def _send_sse(self, chunks: list[tuple[str | None, dict]], done_marker: bool) -> None:
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.send_header("Cache-Control", "no-cache")
        self.end_headers()
        for event, payload in chunks:
            prefix = f"event: {event}\n" if event else ""
            self.wfile.write(f"{prefix}data: {json.dumps(payload)}\n\n".encode())
        if done_marker:
            self.wfile.write(b"data: [DONE]\n\n")
        self.wfile.flush()
        self.close_connection = True

    def _authorized(self) -> bool:
        auth = self.headers.get("Authorization", "")
        key = auth[7:] if auth.lower().startswith("bearer ") else self.headers.get("x-api-key", "")
        if MOCK_KEY and key == MOCK_KEY:
            return True
        log("auth_rejected", path=self.path, got_key_prefix=key[:6])
        self._send_json(401, {"error": {"message": "Invalid API key (mock-managed)", "type": "auth_error", "code": "401"}})
        return False

    def do_GET(self) -> None:
        path = route(self.path)
        log("request", method="GET", path=self.path)
        if path in ("/health", "/health/liveliness", "/health/readiness"):
            self._send_json(200, {"status": "healthy"})
            return
        if not self._authorized():
            return
        if path == "/models":
            self._send_json(200, {"object": "list", "data": [{"id": MODEL_ID, "object": "model", "created": 0, "owned_by": "mock-managed"}]})
            return
        self._send_json(404, {"error": {"message": f"not found: {self.path}"}})

    def do_POST(self) -> None:
        path = route(self.path)
        length = int(self.headers.get("Content-Length") or 0)
        raw = self.rfile.read(length) if length else b""
        try:
            body = json.loads(raw or b"{}")
        except json.JSONDecodeError:
            log("request", method="POST", path=self.path, raw=raw.decode(errors="replace"))
            self._send_json(400, {"error": {"message": "invalid JSON"}})
            return
        log("request", method="POST", path=self.path, body=body)
        if not self._authorized():
            return
        stream = bool(body.get("stream"))
        if path == "/responses":
            reply = responses_reply(body)
            log("response", path=self.path, stream=stream, body=reply)
            if stream:
                self._send_sse(responses_sse(reply), done_marker=False)
            else:
                self._send_json(200, reply)
            return
        if path == "/chat/completions":
            reply = chat_reply(body)
            log("response", path=self.path, stream=stream, body=reply)
            if stream:
                self._send_sse([(None, c) for c in chat_sse(reply)], done_marker=True)
            else:
                self._send_json(200, reply)
            return
        self._send_json(404, {"error": {"message": f"not found: {self.path}"}})


def main() -> None:
    if not MOCK_KEY:
        print("MOCK_KEY is not set; every authenticated request will be rejected", file=sys.stderr, flush=True)
    host = os.environ.get("MOCK_HOST", "0.0.0.0")
    port = int(os.environ.get("MOCK_PORT", "8080"))
    log("listening", host=host, port=port)
    ThreadingHTTPServer((host, port), Handler).serve_forever()


if __name__ == "__main__":
    main()
