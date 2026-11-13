"""Structured plan output: a schema the model must fill, checked in code.

The November 2026 failures were structural. The critique-revise loop handed back an
18-week plan to a runner with 10 weeks, and two runs of the same runner were assessed
at 3:45 and 4:15. This module fixes both in code:

* ``assess_runner`` replaces the LLM's feasibility call with a calculation:
  Riegel's formula (T2 = T1 x (D2 / D1) ** 1.06) from the runner's recent half
  marathon, and a peak mileage from the 10% rule the plan prompt already states.
  Same inputs, same answer, every time.
* ``Plan`` / ``Week`` / ``Session`` are pydantic models: seven sessions a week, each
  with a day, a type from a fixed list and a distance.
* ``validate_plan`` parses the model's JSON against the schema, then checks what a
  schema cannot express: the number of weeks equals the runner's input, weeks run
  1..N, each day appears once, running days do not exceed the runner's days per
  week, rest days are 0 miles, phases run Base, Build, Peak, Taper in order, and the
  last week holds the race. Every failure becomes a plain sentence that goes back to
  the model on a retry.
* ``summarize_weeks`` turns a valid plan into the weekly totals that the agent's
  original ``_safety_checks`` score, so old and new plans are judged by the same
  function.
"""

from __future__ import annotations

import json
import math
from typing import Literal

from pydantic import BaseModel, Field, ValidationError

DAYS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
PHASES = ["Base", "Build", "Peak", "Taper"]
SessionType = Literal["rest", "easy", "long", "tempo", "intervals", "marathon_pace", "hills", "race"]
RIEGEL_EXP = 1.06
MARATHON_MI = 26.2


class Session(BaseModel):
    day: Literal["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
    type: SessionType
    miles: float = Field(ge=0, le=30)
    note: str = Field(default="", max_length=120)


class Week(BaseModel):
    week: int = Field(ge=1)
    phase: Literal["Base", "Build", "Peak", "Taper"]
    focus: str = Field(default="", max_length=160)
    sessions: list[Session] = Field(min_length=7, max_length=7)


class Plan(BaseModel):
    weeks: list[Week] = Field(min_length=1)


# --------------------------------------------------------------------------- #
# Deterministic assessment
# --------------------------------------------------------------------------- #
def parse_hms(t: str) -> float:
    """'3:05:00' or '1:42:00' or '3:05' (h:mm) -> minutes."""
    parts = [float(x) for x in str(t).strip().split(":")]
    if len(parts) == 3:
        return parts[0] * 60 + parts[1] + parts[2] / 60
    if len(parts) == 2:
        return parts[0] * 60 + parts[1]
    return parts[0]


def fmt_hms(minutes: float) -> str:
    s = int(round(minutes * 60))
    return f"{s // 3600}:{s % 3600 // 60:02d}:{s % 60:02d}"


def taper_weeks(weeks: int) -> int:
    return 2 if weeks < 12 else 3


def assess_runner(profile: dict) -> dict:
    """Feasibility and targets from the inputs alone. No model call."""
    goal = parse_hms(profile["goal_time"])
    out = {"method": "riegel_1.06_from_recent_half + 10pct_rule", "goal_min": round(goal, 2)}
    half = profile.get("recent_half")
    if half:
        pred = parse_hms(half) * (MARATHON_MI / 13.1) ** RIEGEL_EXP
        rec = goal if goal >= pred else math.ceil(pred)
        out.update(predicted_min=round(pred, 2), feasible=goal >= pred,
                   recommended_goal_time=fmt_hms(rec))
    else:
        out.update(predicted_min=None, feasible=None, recommended_goal_time=profile["goal_time"])
    cur = float(profile["current_mpw"])
    build = max(0, int(profile["weeks"]) - taper_weeks(int(profile["weeks"])))
    steps = build - build // 4          # every fourth week is a step-back week
    out["peak_weekly_miles"] = round(min(cur * 1.1 ** steps, 1.6 * cur, 70.0), 1)
    out["taper_weeks"] = taper_weeks(int(profile["weeks"]))
    out["rationale"] = (
        (f"Riegel from a {half} half predicts {fmt_hms(out['predicted_min'])}; "
         f"goal {profile['goal_time']} is {'within' if out['feasible'] else 'faster than'} that. ")
        if half else "No recent race given, so the goal is kept. ")
    out["rationale"] += (f"Peak {out['peak_weekly_miles']} mi/week: {cur:g} grown 10% per build week "
                         f"with every fourth week a step back, capped at 1.6 times the current load and at 70.")
    return out


# --------------------------------------------------------------------------- #
# Validation
# --------------------------------------------------------------------------- #
def _schema_errors(exc: ValidationError) -> list[str]:
    out = []
    for e in exc.errors()[:12]:
        loc = ".".join(str(x) for x in e["loc"])
        out.append(f"{loc}: {e['msg']}")
    if len(exc.errors()) > 12:
        out.append(f"... and {len(exc.errors()) - 12} more schema errors")
    return out


def validate_plan(data, profile: dict) -> tuple[Plan | None, list[str]]:
    """Return (plan, []) if valid, else (None or plan, [error sentences])."""
    if isinstance(data, list):              # tolerate a bare array of weeks
        data = {"weeks": data}
    if isinstance(data, str):
        try:
            data = json.loads(data)
        except json.JSONDecodeError as exc:
            return None, [f"not valid JSON: {exc}"]
    try:
        plan = Plan.model_validate(data)
    except ValidationError as exc:
        return None, _schema_errors(exc)
    errs: list[str] = []
    n = int(profile["weeks"])
    if len(plan.weeks) != n:
        errs.append(f"the plan has {len(plan.weeks)} weeks; the runner has exactly {n} weeks until race day")
    nums = [w.week for w in plan.weeks]
    if nums != list(range(1, len(plan.weeks) + 1)):
        errs.append("weeks must be numbered 1, 2, 3, ... in order")
    order = [PHASES.index(w.phase) for w in plan.weeks]
    if any(b < a for a, b in zip(order, order[1:])):
        errs.append("phases must run Base, then Build, then Peak, then Taper, without going back")
    if plan.weeks and plan.weeks[-1].phase != "Taper":
        errs.append("the final week must be a Taper week")
    days_cap = int(profile["days_per_week"])
    for w in plan.weeks:
        days = [s.day for s in w.sessions]
        if sorted(days, key=DAYS.index) != DAYS:
            errs.append(f"week {w.week}: each day Mon to Sun must appear exactly once")
        run = [s for s in w.sessions if s.type != "rest"]
        if len(run) > days_cap:
            errs.append(f"week {w.week}: {len(run)} running days; the runner can train {days_cap} days a week")
        for s in w.sessions:
            if s.type == "rest" and s.miles != 0:
                errs.append(f"week {w.week} {s.day}: a rest day must be 0 miles")
            if s.type != "rest" and s.miles <= 0:
                errs.append(f"week {w.week} {s.day}: a {s.type} session needs a distance above 0")
        if sum(1 for s in w.sessions if s.type == "long") > 1:
            errs.append(f"week {w.week}: at most one long run a week")
        races = [s for s in w.sessions if s.type == "race"]
        if w is plan.weeks[-1]:
            if len(races) != 1 or abs(races[0].miles - MARATHON_MI) > 0.05:
                errs.append(f"week {w.week}: the final week must contain exactly one race session of {MARATHON_MI} miles")
        elif races:
            errs.append(f"week {w.week}: only the final week may contain the race")
    return plan, errs


def summarize_weeks(plan: Plan) -> list[dict]:
    """Weekly totals for `graph._safety_checks`. The race itself is left out of the
    final week's mileage and of the long run, so the taper check reads the training
    load and not the 26.2 miles of the race."""
    out = []
    for w in plan.weeks:
        train = [s for s in w.sessions if s.type != "race"]
        longs = [s.miles for s in train if s.type == "long"] or [0.0]
        out.append({"week": w.week, "phase": w.phase,
                    "weekly_miles": round(sum(s.miles for s in train), 1),
                    "long_run_miles": max(longs),
                    "quality_sessions": [s.type for s in train if s.type in
                                         ("tempo", "intervals", "marathon_pace", "hills")],
                    "focus": w.focus})
    return out


SCHEMA_TEXT = """Return ONLY a JSON object of this shape (no prose, no code fences):
{"weeks": [
  {"week": 1, "phase": "Base"|"Build"|"Peak"|"Taper", "focus": "<short>",
   "sessions": [
     {"day": "Mon", "type": "rest"|"easy"|"long"|"tempo"|"intervals"|"marathon_pace"|"hills"|"race", "miles": <number>, "note": "<short, optional>"},
     ... exactly seven sessions, one per day Mon, Tue, Wed, Thu, Fri, Sat, Sun
   ]},
  ...
]}
Rules: exactly {weeks} weeks numbered 1 to {weeks}; at most {days} running days a week (the others are "rest" with 0 miles); at most one "long" run a week; phases in the order Base, Build, Peak, Taper; the final week is Taper and contains the race as one session of type "race" with 26.2 miles."""
