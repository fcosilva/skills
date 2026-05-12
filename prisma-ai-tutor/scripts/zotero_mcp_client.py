#!/usr/bin/env python3
"""Minimal client for the local zotero-mcp Streamable HTTP endpoint."""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any
from urllib import request


@dataclass
class ZoteroMCPClient:
    endpoint: str
    session_id: str | None = None
    request_id: int = 0

    def initialize(self) -> None:
        payload = {
            "jsonrpc": "2.0",
            "id": self._next_id(),
            "method": "initialize",
            "params": {
                "protocolVersion": "2024-11-05",
                "capabilities": {},
                "clientInfo": {"name": "PRISMA-AI Tutor", "version": "1.0"},
            },
        }
        response = self._post(payload, capture_session=True)
        if "result" not in response:
            raise RuntimeError(f"Unexpected initialize response: {response}")

        notification = {
            "jsonrpc": "2.0",
            "method": "notifications/initialized",
            "params": {},
        }
        self._post(notification)

    def list_tools(self) -> list[dict[str, Any]]:
        response = self._post(
            {
                "jsonrpc": "2.0",
                "id": self._next_id(),
                "method": "tools/list",
                "params": {},
            }
        )
        return response.get("result", {}).get("tools", [])

    def call_tool(self, name: str, arguments: dict[str, Any]) -> Any:
        response = self._post(
            {
                "jsonrpc": "2.0",
                "id": self._next_id(),
                "method": "tools/call",
                "params": {"name": name, "arguments": arguments},
            }
        )
        result = response.get("result", {})
        content = result.get("content", [])
        if not content:
            return result
        text_chunks = [item.get("text", "") for item in content if item.get("type") == "text"]
        if not text_chunks:
            return content
        text = "".join(text_chunks).strip()
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            return text

    def _next_id(self) -> int:
        self.request_id += 1
        return self.request_id

    def _post(self, payload: dict[str, Any], capture_session: bool = False) -> dict[str, Any]:
        headers = {"Content-Type": "application/json"}
        if self.session_id:
            headers["Mcp-Session-Id"] = self.session_id
        req = request.Request(
            self.endpoint,
            data=json.dumps(payload).encode("utf-8"),
            headers=headers,
            method="POST",
        )
        with request.urlopen(req) as resp:
            if capture_session:
                self.session_id = resp.headers.get("Mcp-Session-Id")
            body = resp.read().decode("utf-8")
        return json.loads(body) if body else {}
