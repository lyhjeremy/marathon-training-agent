"""Generate a marathon training plan with the LangGraph agent.

    python -m src.cli --race boston --goal 3:15:00 --weeks 16 \
        --current-mpw 25 --longest 10 --days 5 --temp 72

Run with no args for an interactive prompt.
"""

from __future__ import annotations

import argparse
import sys

from .graph import build_agent

# Windows consoles/pipes default to cp1252, which can't encode the → and emoji in
# our output; force UTF-8 so the CLI prints cleanly on every platform.
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")


def _collect_interactive() -> dict:
    print("🏃 Marathon Training Plan Agent — tell me about your race.\n")

    def ask(q, default=None, cast=str):
        suffix = f" [{default}]" if default is not None else ""
        while True:
            raw = input(f"{q}{suffix}: ").strip()
            if not raw and default is not None:
                return default
            try:
                return cast(raw)
            except ValueError:
                print("  (please try again)")

    return {
        "goal_race": ask("Goal race (e.g. boston, chicago, berlin)", "chicago"),
        "goal_time": ask("Goal finish time (H:MM:SS)", "3:30:00"),
        "weeks": ask("Weeks until race day", 16, int),
        "current_mpw": ask("Current weekly mileage", 25, float),
        "longest_run_mi": ask("Longest recent run (miles)", 10, float),
        "days_per_week": ask("Days/week you can train", 5, int),
        "race_temp_f": ask("Expected race-day temp °F (blank if unknown)", 0, float) or None,
    }


def _profile_from_args(a) -> dict:
    return {
        "goal_race": a.race,
        "goal_time": a.goal,
        "weeks": a.weeks,
        "current_mpw": a.current_mpw,
        "longest_run_mi": a.longest,
        "days_per_week": a.days,
        "race_temp_f": a.temp,
    }


def _print_plan(result: dict) -> None:
    a = result.get("assessment", {})
    print("\n" + "=" * 64)
    print("ASSESSMENT")
    print("=" * 64)
    verdict = "realistic ✅" if a.get("feasible") else "ambitious ⚠️"
    print(f"Goal looks {verdict}. Target: {a.get('recommended_goal_time')}  "
          f"(peak ~{a.get('peak_weekly_miles')} mpw)")
    print(a.get("rationale", ""))

    print("\n" + "=" * 64)
    print("TRAINING PLAN")
    print("=" * 64)
    print(f"{'Wk':>2}  {'Phase':<6} {'Miles':>5} {'Long':>5}  Focus / key sessions")
    print("-" * 64)
    for w in result.get("weeks", []):
        q = "; ".join(w.get("quality_sessions", [])[:2])
        focus = w.get("focus", "")
        detail = focus if not q else f"{focus} — {q}"
        print(f"{w.get('week',''):>2}  {w.get('phase',''):<6} "
              f"{w.get('weekly_miles',''):>5} {w.get('long_run_miles',''):>5}  {detail}")

    print("\n" + "=" * 64)
    print("AGENT TRACE")
    print("=" * 64)
    for step in result.get("log", []):
        print(f"  • {step}")
    c = result.get("critique", {})
    if c.get("ok"):
        print("  ✔ final plan passed all safety checks")
    else:
        print(f"  ⚠ finalized with remaining notes: {c.get('issues')}")
    print()


def main() -> None:
    ap = argparse.ArgumentParser(description="Marathon Training Plan Agent (LangGraph)")
    ap.add_argument("--race", help="e.g. boston, chicago, berlin, nyc, london, tokyo")
    ap.add_argument("--goal", help="goal time H:MM:SS")
    ap.add_argument("--weeks", type=int, default=16)
    ap.add_argument("--current-mpw", type=float, default=25)
    ap.add_argument("--longest", type=float, default=10)
    ap.add_argument("--days", type=int, default=5)
    ap.add_argument("--temp", type=float, default=None, help="expected race-day °F")
    ap.add_argument("--max-revisions", type=int, default=2)
    args = ap.parse_args()

    profile = _profile_from_args(args) if args.race and args.goal else _collect_interactive()

    agent = build_agent()
    print("\n…running agent (assess → plan → adjust → critique → revise)…")
    result = agent.invoke(
        {"profile": profile, "max_revisions": args.max_revisions},
        {"recursion_limit": 50},
    )
    _print_plan(result)


if __name__ == "__main__":
    main()
