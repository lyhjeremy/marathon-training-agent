"""The marathon training-plan agent, built as a LangGraph state machine.

    assess ─▶ plan ─▶ adjust ─▶ critique ─┬─(issues & budget)─▶ revise ─┐
                                          │                             │
                                          └──────────── (clean) ──▶ END ┘
                                                    revise ─▶ critique

`assess` judges whether the goal is realistic; `plan` drafts a periodized
week-by-week build; `adjust` tailors it to the specific race (course + heat)
using my own analyses; `critique` runs deterministic safety checks *and* an LLM
review; `revise` fixes what critique flags and loops back until the plan is clean
or the revision budget is spent.
"""

from __future__ import annotations

from typing import TypedDict

from langgraph.graph import END, StateGraph

from .knowledge import knowledge_brief
from .llm import LLM
from .util import json_complete


class PlanState(TypedDict, total=False):
    profile: dict          # runner inputs
    assessment: dict       # feasibility judgement
    weeks: list            # the plan: list of week dicts
    critique: dict         # {issues: [...], ok: bool}
    revisions: int
    max_revisions: int
    log: list              # human-readable trace


WEEK_SCHEMA = (
    'Each week is an object: {"week": int, "phase": '
    '"Base"|"Build"|"Peak"|"Taper", "weekly_miles": number, '
    '"long_run_miles": number, "quality_sessions": [short strings], '
    '"focus": short string}. Return a JSON array of weeks.'
)


_LLM: LLM | None = None


def _llm(state=None) -> LLM:
    # Lazy module-level singleton — kept out of graph state (not serializable).
    global _LLM
    if _LLM is None:
        _LLM = LLM()
    return _LLM


# --------------------------------------------------------------------------- #
# Nodes
# --------------------------------------------------------------------------- #
def assess(state: PlanState) -> PlanState:
    p = state["profile"]
    prompt = (
        f"A runner wants to run {p['goal_race'].title()} in {p['goal_time']}.\n"
        f"Current fitness: {p['current_mpw']} miles/week, longest recent run "
        f"{p['longest_run_mi']} miles, {p['weeks']} weeks until race day, can train "
        f"{p['days_per_week']} days/week.\n\n"
        "Judge whether the goal time is realistic. Return JSON: "
        '{"feasible": bool, "recommended_goal_time": "H:MM:SS", '
        '"peak_weekly_miles": number, "rationale": "one or two sentences"}.'
    )
    a = json_complete(_llm(state), prompt, system="You are a pragmatic marathon coach.")
    log = state.get("log", []) + [
        f"assess → feasible={a.get('feasible')}, "
        f"target {a.get('recommended_goal_time')}, peak {a.get('peak_weekly_miles')} mpw"
    ]
    return {"assessment": a, "log": log, "revisions": 0}


def plan(state: PlanState) -> PlanState:
    p, a = state["profile"], state["assessment"]
    prompt = (
        f"Build a {p['weeks']}-week marathon plan for {p['goal_race'].title()}, "
        f"target {a.get('recommended_goal_time', p['goal_time'])}.\n"
        f"Start near {p['current_mpw']} miles/week (longest run {p['longest_run_mi']} mi), "
        f"peak around {a.get('peak_weekly_miles')} miles/week, {p['days_per_week']} "
        "days/week. Periodize Base → Build → Peak → Taper. Increase weekly mileage "
        "gradually (roughly 10% per step, with easier step-back weeks) and TAPER over "
        "the final 2–3 weeks. Cap the longest run around 20–22 miles.\n\n"
        f"{WEEK_SCHEMA}"
    )
    weeks = json_complete(_llm(state), prompt, system="You are a marathon coach.")
    log = state.get("log", []) + [f"plan → drafted {len(weeks)} weeks"]
    return {"weeks": weeks, "log": log}


def adjust(state: PlanState) -> PlanState:
    p = state["profile"]
    brief = knowledge_brief(p.get("goal_race"), p.get("race_temp_f"))
    prompt = (
        "Here is a draft marathon plan (JSON):\n"
        f"{state['weeks']}\n\n"
        "Tailor it to this specific race using these evidence-based notes:\n"
        f"{brief}\n\n"
        "Adjust workout emphasis and focus fields accordingly (e.g. downhill/quad "
        "work and late-race hill simulation for a hilly course; heat acclimation and "
        "hydration practice for a hot race; race-pace segments in the 30–42 km zone). "
        "Keep the same week structure and JSON schema; return the full updated array.\n\n"
        f"{WEEK_SCHEMA}"
    )
    weeks = json_complete(_llm(state), prompt, system="You are a marathon coach.")
    log = state.get("log", []) + ["adjust → tailored plan to course & weather"]
    return {"weeks": weeks, "log": log}


def _safety_checks(weeks: list) -> list[str]:
    """Deterministic guardrails — the objective half of the critique."""
    issues = []
    if not weeks:
        return ["plan is empty"]
    try:
        miles = [float(w.get("weekly_miles", 0)) for w in weeks]
        longs = [float(w.get("long_run_miles", 0)) for w in weeks]
    except (TypeError, ValueError):
        return ["weekly_miles / long_run_miles are not all numeric"]

    peak = max(miles)
    # Aggressive week-over-week ramp (ignore step-downs).
    for i in range(1, len(miles)):
        if miles[i - 1] > 0 and (miles[i] - miles[i - 1]) / miles[i - 1] > 0.20:
            issues.append(
                f"week {i + 1} jumps mileage >20% ({miles[i-1]:.0f}→{miles[i]:.0f})"
            )
    # Taper: final week should be well below peak.
    if miles[-1] > 0.75 * peak:
        issues.append("insufficient taper — race-week mileage is too close to peak")
    # Long-run caps and sanity.
    if max(longs) > 22.5:
        issues.append(f"longest run {max(longs):.0f} mi exceeds ~22 mi cap")
    for i, (m, lr) in enumerate(zip(miles, longs)):
        if m > 0 and lr > m:
            issues.append(f"week {i + 1} long run ({lr:.0f}) exceeds weekly total ({m:.0f})")
            break
    return issues


def critique(state: PlanState) -> PlanState:
    weeks = state["weeks"]
    hard = _safety_checks(weeks)

    # LLM review for realism/quality on top of the deterministic checks.
    prompt = (
        "Review this marathon plan for safety and realism (JSON):\n"
        f"{weeks}\n\n"
        "List any genuine problems (too-fast ramp, missing taper, monotony, "
        "unrealistic long runs, too many hard days). Return JSON: "
        '{"issues": [short strings], "ok": bool}. If it is sound, return '
        '{"issues": [], "ok": true}.'
    )
    review = json_complete(_llm(state), prompt, system="You are a cautious coach reviewing a plan.")
    soft = [i for i in review.get("issues", []) if isinstance(i, str)]

    issues = hard + [s for s in soft if s not in hard]
    ok = len(issues) == 0
    log = state.get("log", []) + [
        f"critique → {'clean' if ok else str(len(issues)) + ' issue(s)'}"
        + (f": {issues[0]}" if issues else "")
    ]
    return {"critique": {"issues": issues, "ok": ok}, "log": log}


def revise(state: PlanState) -> PlanState:
    issues = state["critique"]["issues"]
    prompt = (
        "Revise this marathon plan to fix these specific problems:\n"
        + "\n".join(f"- {i}" for i in issues)
        + f"\n\nCurrent plan (JSON):\n{state['weeks']}\n\n"
        "Return the corrected full plan. Keep it realistic: gradual ramp (~10%/step "
        "with step-back weeks), a real 2–3 week taper, longest run ≤ ~22 mi.\n\n"
        f"{WEEK_SCHEMA}"
    )
    weeks = json_complete(_llm(state), prompt, system="You are a marathon coach fixing a plan.")
    n = state.get("revisions", 0) + 1
    log = state.get("log", []) + [f"revise #{n} → addressed {len(issues)} issue(s)"]
    return {"weeks": weeks, "revisions": n, "log": log}


def _route(state: PlanState) -> str:
    if state["critique"]["ok"]:
        return "done"
    if state.get("revisions", 0) >= state.get("max_revisions", 2):
        return "done"
    return "revise"


def build_agent():
    g = StateGraph(PlanState)
    g.add_node("assess", assess)
    g.add_node("plan", plan)
    g.add_node("adjust", adjust)
    g.add_node("critique", critique)
    g.add_node("revise", revise)

    g.set_entry_point("assess")
    g.add_edge("assess", "plan")
    g.add_edge("plan", "adjust")
    g.add_edge("adjust", "critique")
    g.add_conditional_edges("critique", _route, {"revise": "revise", "done": END})
    g.add_edge("revise", "critique")
    return g.compile()
