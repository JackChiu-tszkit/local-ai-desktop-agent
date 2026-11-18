import sys
from pathlib import Path

from app.mcp.client import MCPClient, MCPServerConfig
from app.mcp.tool_adapter import connect_configured_servers
from app.tools.registry import build_registry
from tests.conftest import make_context
from tests.fake_platform import FakePlatform


def test_mcp_round_trip_and_approval_gate(tmp_path, workspace):
    server = Path(__file__).parent / "mcp_fake_server.py"
    config = MCPServerConfig(name="fake", command=sys.executable, args=[str(server)], enabled=True)
    client = MCPClient(config)
    try:
        client.start()
        tools = client.list_tools()
        assert tools[0]["name"] == "echo"
        assert client.call_tool("echo", {"value": 1})["content"][0]["text"] == "ok"
    finally:
        client.close()

    disabled = MCPClient(MCPServerConfig(name="off", command=sys.executable, args=[str(server)], enabled=False))
    try:
        disabled.start()
        raised = False
    except PermissionError:
        raised = True
    assert raised

    registry = build_registry()
    connect_configured_servers(
        registry,
        [{"name": "fake", "command": sys.executable, "args": [str(server)], "enabled": True}],
    )
    tool_name = "mcp.fake.echo"
    ctx = make_context(workspace, FakePlatform(), tmp_path, approved=False)
    try:
        try:
            registry.call(tool_name, {"value": "x"}, ctx)
            denied = False
        except PermissionError:
            denied = True
        assert denied
        ctx.approved = True
        _model, result = registry.call(tool_name, {"value": "x"}, ctx)
        assert result.ok
        assert result.message == "ok"
    finally:
        # The adapter keeps the server process alive for the registry lifetime.
        for spec in registry._tools.values():
            client_ref = getattr(spec.handler, "__closure__", None)
            if not client_ref:
                continue
            for cell in client_ref:
                maybe = cell.cell_contents
                if isinstance(maybe, MCPClient):
                    maybe.close()
