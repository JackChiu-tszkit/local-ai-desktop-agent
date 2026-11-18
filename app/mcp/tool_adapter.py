"""Adapt MCP tools into the local registry without bypassing approval."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict

from app.mcp.client import MCPClient, MCPServerConfig
from app.storage.models import RiskLevel, ToolResult
from app.tools.base import ToolContext, ToolSpec
from app.tools.registry import ToolRegistry


class MCPArgs(BaseModel):
    model_config = ConfigDict(extra="allow")


def connect_configured_servers(registry: ToolRegistry, servers: list[dict]) -> list[str]:
    connected: list[str] = []
    for raw in servers:
        enabled = bool(raw.get("enabled"))
        if not enabled:
            continue
        client = MCPClient(MCPServerConfig.model_validate(raw))
        client.start()
        for tool in client.list_tools():
            name = f"mcp.{raw['name']}.{tool['name']}"
            description = str(tool.get("description") or tool["name"])
            registry.add(_mcp_spec(name, description, client, str(tool["name"])))
        connected.append(str(raw["name"]))
    return connected


def _mcp_spec(name: str, description: str, client: MCPClient, remote_name: str) -> ToolSpec:
    def handler(args: MCPArgs, ctx: ToolContext) -> ToolResult:
        if not ctx.approved:
            raise PermissionError("MCP 工具必须经过这次调用的确认")
        payload = args.model_dump()
        result = client.call_tool(remote_name, payload)
        text = json_text(result)
        return ToolResult(
            ok=True,
            verified=True,
            verification_detail="MCP 返回了结果；这不代表产生了未核对的系统更改",
            message=text[:2000],
            data={"text": text[:2000], "count": 1},
        )

    return ToolSpec(
        name=name,
        description=description,
        args_model=MCPArgs,
        handler=handler,
        risk=RiskLevel.high,
        requires_granted_flag=True,
    )


def json_text(result: dict) -> str:
    import json

    content = result.get("content")
    if isinstance(content, list):
        parts = []
        for item in content:
            if isinstance(item, dict) and item.get("type") == "text":
                parts.append(str(item.get("text", "")))
        if parts:
            return "\n".join(parts)
    return json.dumps(result, ensure_ascii=False)
