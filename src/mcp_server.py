"""MCP server: the plan validator, safety checks and assessment over stdio.

Same pattern as marathon-strategy-rag's server (official `mcp` Python SDK, version 2).
None of these tools calls a model: an MCP client such as Claude Code can write a plan
itself and have it checked by the same code the agent uses.

    python src/mcp_server.py
    claude mcp add plan-checks -- ~/venvs/marathon-training-agent/bin/python /path/to/src/mcp_server.py
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from mcp.server.mcpserver import MCPServer  # noqa: E402

from src.graph import _safety_checks  # noqa: E402
from src.schema import SCHEMA_TEXT, assess_runner, summarize_weeks, validate_plan  # noqa: E402

server = MCPServer(
    name="marathon-plan-checks",
    log_level="WARNING",
    instructions=(
        "Checks for marathon training plans. assess_runner gives a target time (Riegel from a "
        "recent half) and a peak weekly mileage. validate_plan checks a plan against the JSON "
        "schema and the runner's inputs, then runs the safety checks. plan_schema returns the "
        "schema text to write against."),
)


@server.tool(name="assess_runner", description="Target time and peak weekly mileage for a runner, computed in code. "
                         "goal_time and recent_half as 'h:mm:ss'.")
def assess_runner_tool(goal_time: str, weeks: int, current_mpw: float,
                       recent_half: str | None = None) -> dict:
    return assess_runner({"goal_time": goal_time, "weeks": weeks, "current_mpw": current_mpw,
                          "recent_half": recent_half})


@server.tool(description="The JSON shape a plan must follow, filled in for a number of weeks "
                         "and running days per week.")
def plan_schema(weeks: int, days_per_week: int) -> str:
    return SCHEMA_TEXT.replace("{weeks}", str(weeks)).replace("{days}", str(days_per_week))


@server.tool(name="validate_plan", description="Validate a plan ({'weeks': [...]}, see plan_schema) for a runner with "
                         "this many weeks and running days a week. Returns schema and structure "
                         "errors, weekly totals and safety issues; ok is true only if all are empty.")
def validate_plan_tool(plan: dict, weeks: int, days_per_week: int) -> dict:
    parsed, errors = validate_plan(plan, {"weeks": weeks, "days_per_week": days_per_week})
    totals = summarize_weeks(parsed) if parsed is not None else []
    safety = _safety_checks(totals) if totals else []
    return {"ok": parsed is not None and not errors and not safety, "errors": errors,
            "safety_issues": safety, "weekly_miles": [w["weekly_miles"] for w in totals]}


@server.tool(description="The agent's four safety checks on weekly totals: no week more than 20% "
                         "above the week before, race week under 75% of peak, longest run at most "
                         "22.5 miles, long run below the week's total. weeks: [{'weekly_miles': n, "
                         "'long_run_miles': n}, ...]")
def safety_checks(weeks: list[dict]) -> dict:
    issues = _safety_checks(weeks)
    return {"ok": not issues, "issues": issues}


if __name__ == "__main__":
    server.run("stdio")
