"""MCP JSON-RPC client with HTTP and STDIN/STDOUT transports."""

from __future__ import annotations

import itertools
import json
import os
import subprocess

import requests

from jarvis_db import list_mcp_servers, log_event
from security_utils import is_safe_external_url

_ids = itertools.count(1)


def enabled_servers() -> list[dict]:
    return [server for server in list_mcp_servers() if server.get("enabled")]


def _payload(method: str, params: dict | None = None) -> dict:
    return {"jsonrpc": "2.0", "id": next(_ids), "method": method, "params": params or {}}


def _call_http(server: dict, method: str, params: dict | None = None) -> dict:
    endpoint = str(server.get("endpoint", ""))
    allow_private = bool((server.get("config") or {}).get("allow_private_network"))
    ok, reason = is_safe_external_url(endpoint, allow_private=allow_private)
    if not ok:
        raise ValueError(reason)
    response = requests.post(endpoint, json=_payload(method, params), timeout=30)
    response.raise_for_status()
    data = response.json()
    if data.get("error"):
        raise RuntimeError(data["error"])
    return data.get("result", data)


def _call_stdio(server: dict, method: str, params: dict | None = None) -> dict:
    config = server.get("config") or {}
    command = str(config.get("command") or server.get("endpoint") or "").strip()
    if not command:
        raise ValueError("stdio_command_required")
    args = config.get("args") or []
    if isinstance(args, str):
        args = [part for part in args.split(" ") if part]
    env = os.environ.copy()
    if isinstance(config.get("env"), dict):
        env.update({str(k): str(v) for k, v in config["env"].items()})
    timeout = max(1, min(int(config.get("timeout_seconds", 20) or 20), 120))
    proc = subprocess.run(
        [command, *[str(arg) for arg in args]],
        input=json.dumps(_payload(method, params), separators=(",", ":")) + "\n",
        capture_output=True,
        text=True,
        timeout=timeout,
        env=env,
    )
    if proc.returncode != 0:
        raise RuntimeError((proc.stderr or proc.stdout or f"exit {proc.returncode}")[:1000])
    lines = [line.strip() for line in proc.stdout.splitlines() if line.strip()]
    if not lines:
        raise RuntimeError("stdio_empty_response")
    data = json.loads(lines[-1])
    if data.get("error"):
        raise RuntimeError(data["error"])
    return data.get("result", data)


def call_mcp(server: dict, method: str, params: dict | None = None) -> dict:
    if str(server.get("transport", "http")).lower() in {"stdio", "stdinout", "stdin/stdout"}:
        return _call_stdio(server, method, params)
    return _call_http(server, method, params)


def test_mcp_server(server: dict) -> dict:
    try:
        result = call_mcp(server, "initialize", {"clientInfo": {"name": "jarvis-agent", "version": "1.0"}})
        log_event("INFO", "mcp", f"MCP server test passed: {server.get('name')}")
        return {"ok": True, "result": result}
    except Exception as exc:
        log_event("WARN", "mcp", f"MCP server test failed: {server.get('name')}", {"error": str(exc)})
        return {"ok": False, "error": str(exc)}


test_mcp_server.__test__ = False
