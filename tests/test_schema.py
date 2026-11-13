"""Schema, validator and deterministic assessment: no model calls."""

import copy

from src.graph import _safety_checks
from src.schema import assess_runner, summarize_weeks, validate_plan

PROFILE = {"goal_race": "nyc", "goal_time": "3:30:00", "weeks": 3, "current_mpw": 25,
           "longest_run_mi": 12, "days_per_week": 4, "recent_half": "1:48:00"}


def _week(n, phase, miles, race=False):
    days = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
    types = ["rest", "easy", "tempo", "rest", "easy", "rest", "race" if race else "long"]
    ms = [0, miles[0], miles[1], 0, miles[2], 0, 26.2 if race else miles[3]]
    return {"week": n, "phase": phase, "focus": "",
            "sessions": [{"day": d, "type": t, "miles": m} for d, t, m in zip(days, types, ms)]}


def good_plan():
    return {"weeks": [_week(1, "Build", [5, 6, 5, 10]), _week(2, "Peak", [5, 7, 5, 12]),
                      _week(3, "Taper", [3, 3, 2, 0], race=True)]}


def test_good_plan_validates_and_passes_safety():
    plan, errs = validate_plan(good_plan(), PROFILE)
    assert errs == []
    weeks = summarize_weeks(plan)
    assert [w["weekly_miles"] for w in weeks] == [26, 29, 8]     # race left out of week 3
    assert _safety_checks(weeks) == []


def test_length_drift_is_caught():
    p = good_plan()
    p["weeks"].insert(1, _week(2, "Build", [5, 6, 5, 10]))
    for i, w in enumerate(p["weeks"], 1):
        w["week"] = i
    _, errs = validate_plan(p, PROFILE)
    assert any("has 4 weeks" in e for e in errs)


def test_too_many_running_days_and_rest_miles():
    p = good_plan()
    p["weeks"][0]["sessions"][0] = {"day": "Mon", "type": "easy", "miles": 4}
    p["weeks"][1]["sessions"][3] = {"day": "Thu", "type": "rest", "miles": 3}
    _, errs = validate_plan(p, PROFILE)
    assert any("5 running days" in e for e in errs)
    assert any("rest day must be 0" in e for e in errs)


def test_schema_errors_are_sentences():
    p = good_plan()
    p["weeks"][0]["sessions"] = p["weeks"][0]["sessions"][:6]
    p["weeks"][1]["phase"] = "Sharpen"
    plan, errs = validate_plan(p, PROFILE)
    assert plan is None and len(errs) >= 2
    assert all(isinstance(e, str) for e in errs)


def test_race_must_close_the_plan():
    p = good_plan()
    p["weeks"][2] = _week(3, "Taper", [3, 3, 2, 6])
    _, errs = validate_plan(p, PROFILE)
    assert any("race session" in e for e in errs)


def test_assessment_is_deterministic_and_uses_riegel():
    a1, a2 = assess_runner(PROFILE), assess_runner(copy.deepcopy(PROFILE))
    assert a1 == a2
    # 108 min * (26.2/13.1) ** 1.06 = 225.2 min, slower than the 3:30 goal
    assert abs(a1["predicted_min"] - 108 * 2 ** 1.06) < 0.01
    assert a1["feasible"] is False and a1["recommended_goal_time"] == "3:46:00"
    assert assess_runner({**PROFILE, "goal_time": "3:50:00"})["recommended_goal_time"] == "3:50:00"


def test_peak_mileage_cap():
    a = assess_runner({**PROFILE, "weeks": 18, "current_mpw": 35})
    assert a["peak_weekly_miles"] == 56.0
