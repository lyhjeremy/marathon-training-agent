"""Run the safety panel from src/eval.py and measure cost, latency and revision loops.

    python -m eval.measure

Uses the three synthetic runners in src/eval.py (PROFILES), each run twice, and the
same node sequence as src/eval.run_profile: assess, plan, adjust, then critique and
revise until the plan is clean or 2 revisions are spent. Plans are scored by the
agent's own `_safety_checks` before the loop (the raw draft out of `adjust`) and
after it.

The Claude CLI is called with the agent's own prompts and flags plus
`--output-format json`, which adds `total_cost_usd` (the API-equivalent cost; the
CLI runs on a subscription) and `duration_ms` to each reply.
Writes eval/runs.json (every draft and final plan), eval/calls.csv,
eval/results.csv and eval/summary.json.
"""

from __future__ import annotations

import csv
import inspect
import json
import statistics
import subprocess
import time
from pathlib import Path

from src import graph as G
from src import llm as llm_mod
from src.eval import PROFILES
from src.graph import _safety_checks, adjust, assess, critique, plan, revise

EVAL = Path(__file__).resolve().parent
CALLS: list[dict] = []
CURRENT = {"run": None}
REPEATS = 2
CALL_BUDGET = 34   # don't start a new plan past this many CLI calls


def _node_name() -> str:
    for fr in inspect.stack():
        if fr.filename.endswith("graph.py") and fr.function != "_llm":
            return fr.function
    return "?"


def _complete_cli_json(self, prompt, system):
    cmd = llm_mod._claude_command() + ["-p"]
    if system:
        cmd += ["--append-system-prompt", system]
    if llm_mod.DEFAULT_CLI_MODEL:
        cmd += ["--model", llm_mod.DEFAULT_CLI_MODEL]
    cmd += ["--output-format", "json"]
    t0 = time.perf_counter()
    res = subprocess.run(cmd, input=prompt, capture_output=True, text=True,
                         encoding="utf-8", errors="replace", timeout=self.timeout)
    wall = time.perf_counter() - t0
    if res.returncode != 0:
        raise llm_mod.LLMError(f"claude CLI failed: {res.stderr.strip()}")
    out = json.loads(res.stdout)
    u = out.get("usage", {})
    CALLS.append({
        "run": CURRENT["run"], "node": _node_name(),
        "wall_s": round(wall, 2), "duration_ms": out.get("duration_ms"),
        "cost_usd": out.get("total_cost_usd"),
        "input_tokens": u.get("input_tokens"), "output_tokens": u.get("output_tokens"),
        "cache_read": u.get("cache_read_input_tokens"),
        "cache_write": u.get("cache_creation_input_tokens"),
        "models": "+".join(sorted(out.get("modelUsage", {}).keys())),
    })
    return (out.get("result") or "").strip()


llm_mod.LLM._complete_cli = _complete_cli_json


def _pct(xs, p):
    xs = sorted(xs)
    k = (len(xs) - 1) * p
    lo, hi = int(k), min(int(k) + 1, len(xs) - 1)
    return xs[lo] + (xs[hi] - xs[lo]) * (k - lo)


def run_one(profile: dict, max_revisions: int = 2) -> dict:
    state = {"profile": profile, "max_revisions": max_revisions}
    state.update(assess(state))
    state.update(plan(state))
    state.update(adjust(state))
    draft = state["weeks"]
    raw = _safety_checks(draft)
    critiques = []
    state.update(critique(state))
    critiques.append(state["critique"]["issues"])
    while not state["critique"]["ok"] and state.get("revisions", 0) < max_revisions:
        state.update(revise(state))
        state.update(critique(state))
        critiques.append(state["critique"]["issues"])
    final = _safety_checks(state["weeks"])
    return {"assessment": state["assessment"], "raw_issues": raw, "final_issues": final,
            "critiques": critiques, "revisions": state.get("revisions", 0),
            "ended_clean": state["critique"]["ok"], "draft": draft,
            "final": state["weeks"]}


def main():
    G._LLM = llm_mod.LLM(timeout=300)
    runs = []
    for rep in range(REPEATS):
        for p in PROFILES:
            if len(CALLS) >= CALL_BUDGET:
                break
            rid = f"{p['goal_race']}-{p['goal_time']}-r{rep + 1}"
            CURRENT["run"] = rid
            n0, t0 = len(CALLS), time.perf_counter()
            try:
                r, err = run_one(p), None
            except Exception as e:
                r, err = {}, f"{type(e).__name__}: {e}"
            wall = time.perf_counter() - t0
            calls = CALLS[n0:]
            r.update({"run": rid, "profile": p, "error": err, "llm_calls": len(calls),
                      "wall_s": round(wall, 1),
                      "cost_usd": round(sum(c["cost_usd"] or 0 for c in calls), 4)})
            runs.append(r)
            print(f"{rid:<26} raw={len(r.get('raw_issues', []))} "
                  f"final={len(r.get('final_issues', []))} rev={r.get('revisions')} "
                  f"clean={r.get('ended_clean')} calls={len(calls)} {wall:.0f}s "
                  f"${r['cost_usd']:.3f} {err or ''}", flush=True)
            (EVAL / "runs.json").write_text(json.dumps(runs, indent=1, ensure_ascii=False))

    with open(EVAL / "calls.csv", "w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(CALLS[0]))
        w.writeheader()
        w.writerows(CALLS)
    ok = [r for r in runs if not r["error"]]
    with open(EVAL / "results.csv", "w", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["run", "race", "goal", "raw_issues", "final_issues", "raw_pass",
                    "final_pass", "revisions", "ended_clean", "llm_calls", "wall_s", "cost_usd"])
        for r in ok:
            w.writerow([r["run"], r["profile"]["goal_race"], r["profile"]["goal_time"],
                        len(r["raw_issues"]), len(r["final_issues"]), not r["raw_issues"],
                        not r["final_issues"], r["revisions"], r["ended_clean"],
                        r["llm_calls"], r["wall_s"], r["cost_usd"]])
    walls = [r["wall_s"] for r in ok]
    costs = [r["cost_usd"] for r in ok]
    chip = subprocess.run(["sysctl", "-n", "machdep.cpu.brand_string"],
                          capture_output=True, text=True).stdout.strip()
    summary = {
        "date": time.strftime("%Y-%m-%d"), "machine": chip,
        "n_plans": len(runs), "n_completed": len(ok),
        "raw_pass": sum(not r["raw_issues"] for r in ok),
        "final_pass": sum(not r["final_issues"] for r in ok),
        "raw_issues_total": sum(len(r["raw_issues"]) for r in ok),
        "final_issues_total": sum(len(r["final_issues"]) for r in ok),
        "ended_clean": sum(r["ended_clean"] for r in ok),
        "revisions": [r["revisions"] for r in ok],
        "llm_calls": len(CALLS),
        "cost_per_plan_median": round(statistics.median(costs), 3),
        "cost_per_plan_mean": round(statistics.mean(costs), 3),
        "latency_median_s": round(statistics.median(walls), 1),
        "latency_p95_s": round(_pct(walls, 0.95), 1),
        "models": sorted({c["models"] for c in CALLS}),
    }
    (EVAL / "summary.json").write_text(json.dumps(summary, indent=2))
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
