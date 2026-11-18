"""Minimal MCP stdio client. Server commands come from user settings, never from model text."""

from __future__ import annotations

import json
import subprocess
import threading
import time
from queue import Empty, Queue

from pydantic import BaseModel, Field


class MCPServerConfig(BaseModel):
    name: str
    command: str
    args: list[str] = Field(default_factory=list)
    enabled: bool = False


class MCPClient:
    def __init__(self, config: MCPServerConfig) -> None:
        self.config = config
        self.proc: subprocess.Popen | None = None
        self._id = 0
        self._queue: Queue = Queue()
        self._reader: threading.Thread | None = None
        self._stop = False

    def start(self) -> None:
        if not self.config.enabled:
            raise PermissionError("The MCP server is not enabled")
        if not self.config.command:
            raise PermissionError("The MCP command is empty")
        self.proc = subprocess.Popen(
            [self.config.command, *self.config.args],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            shell=False,
        )
        self._reader = threading.Thread(target=self._read_loop, daemon=True)
        self._reader.start()
        self._rpc(
            "initialize",
            {
                "protocolVersion": "2024-11-05",
                "capabilities": {},
                "clientInfo": {"name": "local-ai-desktop-agent", "version": "0.1.0"},
            },
        )
        self._notify("notifications/initialized", {})

    def list_tools(self) -> list[dict]:
        result = self._rpc("tools/list", {})
        tools = result.get("tools", []) if isinstance(result, dict) else []
        return list(tools)

    def call_tool(self, name: str, arguments: dict) -> dict:
        result = self._rpc("tools/call", {"name": name, "arguments": arguments})
        return result if isinstance(result, dict) else {"result": result}

    def close(self) -> None:
        self._stop = True
        if self.proc is not None and self.proc.poll() is None:
            self.proc.terminate()
            try:
                self.proc.wait(timeout=3)
            except subprocess.TimeoutExpired:
                self.proc.kill()

    def _notify(self, method: str, params: dict) -> None:
        self._send({"jsonrpc": "2.0", "method": method, "params": params})

    def _rpc(self, method: str, params: dict, timeout: float = 20) -> dict:
        self._id += 1
        ident = self._id
        self._send({"jsonrpc": "2.0", "id": ident, "method": method, "params": params})
        deadline = time.monotonic() + timeout
        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise TimeoutError(f"The MCP call timed out: {method}")
            try:
                item = self._queue.get(timeout=remaining)
            except Empty as exc:
                raise TimeoutError(f"The MCP call timed out: {method}") from exc
            if isinstance(item, Exception):
                raise item
            if item.get("id") != ident:
                continue
            if "error" in item:
                raise RuntimeError(str(item["error"]))
            return item.get("result") or {}

    def _send(self, payload: dict) -> None:
        if self.proc is None or self.proc.stdin is None:
            raise RuntimeError("The MCP server did not start")
        body = json.dumps(payload).encode("utf-8")
        header = f"Content-Length: {len(body)}\r\n\r\n".encode("ascii")
        self.proc.stdin.write(header + body)
        self.proc.stdin.flush()

    def _read_loop(self) -> None:
        try:
            while not self._stop:
                message = self._read_message()
                if message is None:
                    break
                self._queue.put(message)
        except Exception as exc:
            self._queue.put(exc)

    def _read_message(self) -> dict | None:
        if self.proc is None or self.proc.stdout is None:
            return None
        header = b""
        while b"\r\n\r\n" not in header:
            chunk = self.proc.stdout.read(1)
            if not chunk:
                return None
            header += chunk
            if len(header) > 65536:
                raise RuntimeError("The MCP header is too long")
        length = None
        for line in header.split(b"\r\n\r\n", 1)[0].split(b"\r\n"):
            if line.lower().startswith(b"content-length:"):
                length = int(line.split(b":", 1)[1].strip())
        if length is None:
            raise RuntimeError("The MCP response is missing Content-Length")
        body = b""
        while len(body) < length:
            part = self.proc.stdout.read(length - len(body))
            if not part:
                raise RuntimeError("The MCP response is incomplete")
            body += part
        return json.loads(body.decode("utf-8"))
