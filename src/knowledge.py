"""Domain knowledge the agent uses to tailor plans.

Several figures come from my own marathon data analyses (see the Marathon
Strategy RAG and related projects); they let the agent adjust a plan for the
specific race a runner picked rather than emitting a generic template.
"""

from __future__ import annotations

# Course Difficulty Index vs Berlin (seconds slower for an equivalent runner).
# From my "Marathon Majors Course Difficulty" analysis.
# SIMULATED, NOT RACE RESULTS. That study ran on a simulated field (800 athletes,
# seed 42) with course penalties planted in code, so these figures test a method
# and do not measure the real courses. They also come from an earlier version of
# the simulation and differ from the current study (for example Tokyo 33 s here
# vs 21.0 s, Boston index 1.036 here vs 1.0092). Left unchanged so the recorded
# runs stay reproducible; the brief below labels them as simulated.
COURSE_DIFFICULTY = {
    "berlin": {"index": 1.000, "penalty_s": 0, "note": "flattest, fastest — a PR course"},
    "chicago": {"index": 1.004, "penalty_s": 12, "note": "flat and fast"},
    "london": {"index": 1.010, "penalty_s": 28, "note": "flat, but crowded early"},
    "tokyo": {"index": 1.012, "penalty_s": 33, "note": "flat with a few bridges"},
    "nyc": {"index": 1.028, "penalty_s": 78, "note": "hilly bridges; tough late"},
    "boston": {"index": 1.036, "penalty_s": 101,
               "note": "net downhill but the Newton hills at ~30 km punish quads and legs"},
}

# The Heat Tax: ~1 minute slower per °F of race-day midday temperature above a
# comfortable ~50–55°F baseline (r=0.86 across 14 years of Boston).
HEAT_MIN_PER_DEG_F = 1.0
HEAT_COMFORT_F = 55

# The wall: field pace inflects sharply at ~30 km; the race is decided in the
# 30–42 km segment. Long runs and late-race fueling should target that zone.
WALL_KM = 30

# Even-pacing: only ~2.5% of runners negative-split; ~94% slow (median +14%).
# Plans should train even effort and controlled starts, not heroic negative splits.
NEGATIVE_SPLIT_RATE = 0.025


def heat_penalty_minutes(temp_f: float | None) -> float:
    if temp_f is None:
        return 0.0
    return max(0.0, (temp_f - HEAT_COMFORT_F) * HEAT_MIN_PER_DEG_F)


def course_note(race: str | None) -> dict | None:
    if not race:
        return None
    return COURSE_DIFFICULTY.get(race.strip().lower())


def knowledge_brief(race: str | None, temp_f: float | None) -> str:
    """A compact brief the LLM can use when adjusting a plan."""
    lines = [
        f"- Even pacing: only ~{NEGATIVE_SPLIT_RATE:.1%} of runners negative-split; "
        "train controlled starts and even effort, not negative splits.",
        f"- The wall: pace inflects at ~{WALL_KM} km; long runs and fueling must "
        "prepare the 30–42 km segment.",
    ]
    c = course_note(race)
    if c:
        lines.append(
            f"- Course ({race.title()}): {c['note']}. Expect ~{c['penalty_s']}s "
            f"slower than a flat course (a simulated estimate from a method test, "
            f"not race results); train specificity for it."
        )
    if temp_f is not None:
        pen = heat_penalty_minutes(temp_f)
        lines.append(
            f"- Heat: ~{temp_f:.0f}°F on race day implies ~{pen:.0f} min slower than "
            f"a cool day (rule of thumb ~1 min/°F above {HEAT_COMFORT_F}°F); set a "
            "hot-day pace band and practice heat/hydration."
        )
    return "\n".join(lines)
