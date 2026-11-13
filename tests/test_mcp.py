"""Start the MCP server over stdio, list its tools and validate a plan through it."""

import asyncio
import json
import sys
from pathlib import Path

from mcp import ClientSession, StdioServerParameters, stdio_client

from tests.test_schema import good_plan

ROOT = Path(__file__).resolve().parent.parent


async def _roundtrip():
    params = StdioServerParameters(command=sys.executable, args=[str(ROOT / "src" / "mcp_server.py")],
                                   cwd=str(ROOT))
    async with stdio_client(params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            names = sorted(t.name for t in (await session.list_tools()).tools)
            res = await session.call_tool("validate_plan", {"plan": good_plan(), "weeks": 3, "days_per_week": 4})
            ok = json.loads("".join(getattr(c, "text", "") for c in res.content))
            res = await session.call_tool("validate_plan", {"plan": good_plan(), "weeks": 10, "days_per_week": 4})
            bad = json.loads("".join(getattr(c, "text", "") for c in res.content))
    return names, ok, bad


def test_mcp_roundtrip():
    names, ok, bad = asyncio.run(_roundtrip())
    assert names == ["assess_runner", "plan_schema", "safety_checks", "validate_plan"]
    assert ok["ok"] is True and ok["weekly_miles"] == [26, 29, 8]
    assert bad["ok"] is False and any("exactly 10 weeks" in e for e in bad["errors"])
