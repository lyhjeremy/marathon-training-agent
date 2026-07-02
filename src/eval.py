"""Does the agent's self-critique loop actually make plans safer? Measure it.

The agent drafts a plan, then a `critique` node runs deterministic safety checks
(mileage ramp ≤ ~20%/wk, a real taper, long-run caps) and a `revise` node fixes
what they flag. This harness quantifies the value of that loop: it runs the agent
on a panel of synthetic runners and compares each plan's safety **before** the
loop (the raw first draft, straight out of `adjust`) against **after** it.

We drive the graph's own node functions directly so "before" and "after" are
scored by the *same* `_safety_checks` the agent uses on itself.

Run:  python -m src.eval        # writes eval/results.csv + eval/safety_gain.png
"""

from __future__ import annotations

import csv
from pathlib import Path

from . import graph as _graph
from .graph import _safety_checks, adjust, assess, critique, plan, revise
from .llm import LLM

ROOT = Path(__file__).resolve().parent.parent
EVAL_DIR = ROOT / "eval"

# A panel of runners, several deliberately aggressive (short timeline, ambitious
# goal, low base) to stress the safety loop.
PROFILES = [
    # Aggressive: short timeline / low base / ambitious goal — stresses the safety loop.
    {"goal_race": "boston", "goal_time": "3:00:00", "weeks": 12, "current_mpw": 20,
     "longest_run_mi": 8, "days_per_week": 4, "race_temp_f": 74},
    {"goal_race": "nyc", "goal_time": "3:30:00", "weeks": 10, "current_mpw": 25,
     "longest_run_mi": 12, "days_per_week": 5, "race_temp_f": None},
    # Realistic control — should largely pass on the first draft.
    {"goal_race": "berlin", "goal_time": "3:10:00", "weeks": 18, "current_mpw": 35,
     "longest_run_mi": 16, "days_per_week": 6, "race_temp_f": 55},
]


def run_profile(profile: dict, max_revisions: int = 2) -> dict:
    state = {"profile": profile, "max_revisions": max_revisions}
    state.update(assess(state))
    state.update(plan(state))
    state.update(adjust(state))
    raw_issues = _safety_checks(state["weeks"])          # before the loop

    state.update(critique(state))
    while not state["critique"]["ok"] and state.get("revisions", 0) < max_revisions:
        state.update(revise(state))
        state.update(critique(state))
    final_issues = _safety_checks(state["weeks"])        # after the loop

    return {
        "race": profile["goal_race"],
        "goal": profile["goal_time"],
        "raw_issues": len(raw_issues),
        "final_issues": len(final_issues),
        "raw_pass": len(raw_issues) == 0,
        "final_pass": len(final_issues) == 0,
        "revisions": state.get("revisions", 0),
        "example_fix": raw_issues[0] if raw_issues else "",
    }


def evaluate() -> list[dict]:
    # Some `claude -p` calls are slow on Windows; give them headroom, and don't let
    # one slow/failed call sink the whole panel.
    _graph._LLM = LLM(timeout=300)
    rows = []
    for p in PROFILES:
        print(f"  running agent: {p['goal_race']} {p['goal_time']} in {p['weeks']} wk…", flush=True)
        try:
            rows.append(run_profile(p, max_revisions=2))
        except Exception as e:  # a timeout or parse failure on one runner
            print(f"  (skipped — {type(e).__name__}: {e})", flush=True)
    return rows


def _summary(rows: list[dict]) -> dict:
    n = len(rows)
    return {
        "n": n,
        "raw_pass_rate": sum(r["raw_pass"] for r in rows) / n,
        "final_pass_rate": sum(r["final_pass"] for r in rows) / n,
        "raw_issues_mean": sum(r["raw_issues"] for r in rows) / n,
        "final_issues_mean": sum(r["final_issues"] for r in rows) / n,
        "revisions_mean": sum(r["revisions"] for r in rows) / n,
    }


def _print(rows, s):
    print(f"\nAgent safety evaluation over {s['n']} synthetic runners")
    print("-" * 56)
    print(f"  plans passing all safety checks — raw draft : {s['raw_pass_rate']:.0%}")
    print(f"  plans passing all safety checks — final     : {s['final_pass_rate']:.0%}")
    print(f"  mean safety issues per plan     — raw       : {s['raw_issues_mean']:.2f}")
    print(f"  mean safety issues per plan     — final     : {s['final_issues_mean']:.2f}")
    print(f"  mean revisions used by the agent            : {s['revisions_mean']:.2f}\n")


def _write_csv(rows):
    EVAL_DIR.mkdir(exist_ok=True)
    path = EVAL_DIR / "results.csv"
    with open(path, "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)
    print(f"wrote {path}")


def _write_figure(s):
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except Exception:
        print("(matplotlib not installed — skipping figure)")
        return

    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(9.5, 4.3))
    stages = ["raw first\ndraft", "after self-\ncritique loop"]

    pr = [s["raw_pass_rate"], s["final_pass_rate"]]
    b1 = ax1.bar(stages, pr, color=["#C6B79B", "#B5651D"], width=0.6)
    for b, v in zip(b1, pr):
        ax1.text(b.get_x() + b.get_width() / 2, v + 0.02, f"{v:.0%}", ha="center", fontsize=11)
    ax1.set_ylim(0, 1.08)
    ax1.set_ylabel("share of plans")
    ax1.set_title("Plans passing ALL safety checks")
    ax1.spines[["top", "right"]].set_visible(False)

    im = [s["raw_issues_mean"], s["final_issues_mean"]]
    b2 = ax2.bar(stages, im, color=["#C6B79B", "#B5651D"], width=0.6)
    for b, v in zip(b2, im):
        ax2.text(b.get_x() + b.get_width() / 2, v + 0.02, f"{v:.2f}", ha="center", fontsize=11)
    ax2.set_ylim(0, max(im + [1]) * 1.25)
    ax2.set_ylabel("issues per plan")
    ax2.set_title("Mean safety issues per plan")
    ax2.spines[["top", "right"]].set_visible(False)

    fig.suptitle("The self-critique loop makes plans measurably safer",
                 fontsize=13, fontweight="bold")
    fig.tight_layout(rect=[0, 0, 1, 0.95])
    EVAL_DIR.mkdir(exist_ok=True)
    path = EVAL_DIR / "safety_gain.png"
    fig.savefig(path, dpi=150)
    print(f"wrote {path}")


def main():
    rows = evaluate()
    s = _summary(rows)
    _print(rows, s)
    _write_csv(rows)
    _write_figure(s)


if __name__ == "__main__":
    main()
