"""The structured-output agent (November 2026), also a LangGraph state machine.

    assess (code) -> draft (model) -> check (code) -+-(problems, budget left)-> repair (model) -> check
                                                    +-(clean or out of budget)-> END

* ``assess`` is `schema.assess_runner`: Riegel from the recent half, peak mileage from
  the 10% rule. No model call, so the same runner always gets the same target.
* ``draft`` asks for the whole plan in the JSON schema from `schema.SCHEMA_TEXT`, with
  the course and heat notes the old ``adjust`` node used folded into the same prompt.
* ``check`` parses and validates in code (`schema.validate_plan`), then runs the
  original `graph._safety_checks` on the weekly totals. No model review.
* ``repair`` sends the plan back with every problem listed, word for word.

At most ``max_calls`` model calls (default 3: one draft and two repairs, matching the
old loop's two revisions).

    from src.structured import run_structured
    result = run_structured(profile)
"""

from __future__ import annotations

import json
from typing import TypedDict

from langgraph.graph import END, StateGraph

from .graph import _safety_checks
from .knowledge import knowledge_brief
from .llm import LLM
from .schema import SCHEMA_TEXT, assess_runner, summarize_weeks, validate_plan
from .util import parse_json

SYSTEM = ("You are a marathon coach who writes training plans as strict JSON. "
          "Reply with only the JSON object the user asks for.")


class SState(TypedDict, total=False):
    profile: dict
    assessment: dict
    raw: str                 # last model reply
    plan: dict | None        # last parsed plan (validated model dump, or raw JSON)
    weeks: list              # weekly totals of the last schema-valid plan
    problems: list           # structural errors + safety issues from the last check
    history: list            # one entry per check: calls so far and the problems found
    calls: int
    max_calls: int
    log: list


_LLM: LLM | None = None


def _llm() -> LLM:
    global _LLM
    if _LLM is None:
        _LLM = LLM()
    return _LLM


def _schema_text(p: dict) -> str:
    return SCHEMA_TEXT.replace("{weeks}", str(p["weeks"])).replace("{days}", str(p["days_per_week"]))


def assess(state: SState) -> SState:
    a = assess_runner(state["profile"])
    return {"assessment": a, "calls": 0, "history": [],
            "log": [f"assess (code): target {a['recommended_goal_time']}, peak {a['peak_weekly_miles']} mi/week"]}


def draft(state: SState) -> SState:
    p, a = state["profile"], state["assessment"]
    brief = knowledge_brief(p.get("goal_race"), p.get("race_temp_f"))
    prompt = (
        f"Write a {p['weeks']}-week marathon plan for {p['goal_race'].title()}, target "
        f"{a['recommended_goal_time']}.\n"
        f"Runner: {p['current_mpw']} miles/week now, longest recent run {p['longest_run_mi']} miles, "
        f"{p['days_per_week']} running days a week.\n"
        f"Start near {p['current_mpw']} miles/week and peak near {a['peak_weekly_miles']} miles/week. "
        "Raise weekly mileage gradually (about 10% a step, never more than 20% over the week before, "
        "with easier step-back weeks), keep the long run at most 20 to 22 miles and below the week's total, "
        f"and taper over the final {a['taper_weeks']} weeks so race-week training is well under the peak.\n"
        f"Tailor sessions to the race with these notes:\n{brief}\n\n{_schema_text(p)}"
    )
    raw = _llm().complete(prompt, system=SYSTEM)
    return {"raw": raw, "calls": state.get("calls", 0) + 1,
            "log": state["log"] + ["draft (model): plan written"]}


def check(state: SState) -> SState:
    p = state["profile"]
    try:
        data = parse_json(state["raw"])
    except ValueError as exc:
        data, problems, plan, weeks = None, [f"reply was not valid JSON ({str(exc)[:80]})"], None, []
    if data is not None:
        plan, problems = validate_plan(data, p)
        weeks = summarize_weeks(plan) if plan is not None else []
        if plan is not None and not problems:
            problems = _safety_checks(weeks)
        elif plan is not None:
            problems = problems + _safety_checks(weeks)
    hist = state.get("history", []) + [{"calls": state["calls"], "problems": problems,
                                        "n_weeks": len(weeks) if weeks else None}]
    return {"plan": plan.model_dump() if plan is not None else data, "weeks": weeks,
            "problems": problems, "history": hist,
            "log": state["log"] + [f"check (code): {'clean' if not problems else str(len(problems)) + ' problem(s)'}"]}


def repair(state: SState) -> SState:
    p = state["profile"]
    prev = json.dumps(state["plan"], ensure_ascii=False) if state.get("plan") is not None else state["raw"][:20000]
    prompt = (
        "This marathon plan failed validation. Fix every problem below and return the corrected full plan.\n"
        "Problems:\n" + "\n".join(f"- {x}" for x in state["problems"]) +
        f"\n\nPlan:\n{prev}\n\n{_schema_text(p)}"
    )
    raw = _llm().complete(prompt, system=SYSTEM)
    return {"raw": raw, "calls": state["calls"] + 1,
            "log": state["log"] + [f"repair (model): asked to fix {len(state['problems'])} problem(s)"]}


def _route(state: SState) -> str:
    if not state["problems"] or state["calls"] >= state.get("max_calls", 3):
        return "done"
    return "repair"


def build_structured_agent():
    g = StateGraph(SState)
    for name, fn in (("assess", assess), ("draft", draft), ("check", check), ("repair", repair)):
        g.add_node(name, fn)
    g.set_entry_point("assess")
    g.add_edge("assess", "draft")
    g.add_edge("draft", "check")
    g.add_conditional_edges("check", _route, {"repair": "repair", "done": END})
    g.add_edge("repair", "check")
    return g.compile()


def run_structured(profile: dict, max_calls: int = 3) -> SState:
    return build_structured_agent().invoke({"profile": profile, "max_calls": max_calls},
                                           {"recursion_limit": 30})
