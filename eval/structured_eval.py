"""Before and after structured outputs, on the same frozen runners.

Runners: eval/structured/runners.json (6: the three November 5 profiles plus three
new ones, each with a recent half-marathon time), frozen with its hash in
eval/structured/freeze.json before any run.

    before   the original graph: LLM assess, plan, adjust, then critique (safety
             checks + LLM review) and revise, at most 2 revisions; as in eval/measure.py
    after    src/structured.py: assess in code, one schema-bound draft, validation in
             code, at most 2 repairs
    assess   the original LLM assess node twice more per runner, so each runner has
             three LLM assessments (with the one inside its "before" run)

Both systems run on the same model (the CLI's ``sonnet`` alias), with the same
isolated CLI flags, one call at a time. Every plan is scored by the original
`graph._safety_checks` plus one more check: the plan has as many weeks as the
runner has until race day.

    python -m eval.structured_eval --system before     # resumable; one process per system
    python -m eval.structured_eval --system after
    python -m eval.structured_eval --system assess
    python -m eval.structured_eval --summarize
"""

from __future__ import annotations

import argparse
import hashlib
import json
import statistics
import time
from datetime import date
from pathlib import Path

from src import graph as G
from src import structured as S
from src.graph import _safety_checks, adjust, assess, critique, plan, revise
from src.llm import LLM
from src.schema import assess_runner, parse_hms

D = Path(__file__).resolve().parent / "structured"
RUNNERS = D / "runners.json"


def runners() -> list[dict]:
    freeze = json.loads((D / "freeze.json").read_text())
    if hashlib.sha256(RUNNERS.read_bytes()).hexdigest() != freeze["sha256"]:
        raise SystemExit("runners.json differs from the frozen version; refusing to run.")
    return json.loads(RUNNERS.read_text())["runners"]


def score(weeks, profile: dict) -> dict:
    weeks = weeks if isinstance(weeks, list) else []
    try:
        safety = _safety_checks(weeks)
    except Exception as exc:  # malformed week objects
        safety = [f"could not score: {type(exc).__name__}"]
    length_ok = len(weeks) == int(profile["weeks"])
    return {"n_weeks": len(weeks), "length_ok": length_ok, "safety_issues": safety,
            "all_pass": length_ok and not safety}


def _calls(n0: int) -> list[dict]:
    return LLM.ledger[n0:]


def run_before(p: dict) -> dict:
    state = {"profile": p, "max_revisions": 2}
    state.update(assess(state))
    state.update(plan(state))
    state.update(adjust(state))
    draft = state["weeks"]
    state.update(critique(state))
    rounds = [state["critique"]["issues"]]
    while not state["critique"]["ok"] and state.get("revisions", 0) < 2:
        state.update(revise(state))
        state.update(critique(state))
        rounds.append(state["critique"]["issues"])
    return {"assessment": state["assessment"], "draft_score": score(draft, p),
            "final_score": score(state["weeks"], p), "critique_rounds": rounds,
            "revisions": state.get("revisions", 0), "draft": draft, "final": state["weeks"],
            "log": state["log"]}


def run_after(p: dict) -> dict:
    st = S.run_structured(p, max_calls=3)
    first = st["history"][0]
    return {"assessment": st["assessment"], "history": st["history"],
            "first_valid": not first["problems"],
            "final_score": score(st.get("weeks") or [], p),
            "validator_problems": st["problems"], "plan": st.get("plan"),
            "weeks": st.get("weeks"), "repairs": st["calls"] - 1, "log": st["log"]}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--system", choices=["before", "after", "assess"])
    ap.add_argument("--summarize", action="store_true")
    args = ap.parse_args()
    if args.summarize:
        summarize()
        return
    G._LLM = S._LLM = LLM()
    path = D / f"runs_{args.system}.jsonl"
    done = {json.loads(x)["key"] for x in path.read_text().splitlines() if x} if path.exists() else set()
    for p in runners():
        keys = [f"{p['id']}-a{i}" for i in (2, 3)] if args.system == "assess" else [p["id"]]
        for key in keys:
            if key in done:
                continue
            n0, t0 = len(LLM.ledger), time.perf_counter()
            try:
                if args.system == "before":
                    rec = run_before(p)
                elif args.system == "after":
                    rec = run_after(p)
                else:
                    rec = {"assessment": assess({"profile": p})["assessment"]}
                err = None
            except Exception as exc:
                rec, err = {}, f"{type(exc).__name__}: {exc}"
            calls = _calls(n0)
            rec.update({"key": key, "runner": p["id"], "system": args.system, "error": err,
                        "wall_s": round(time.perf_counter() - t0, 1), "llm_calls": len(calls),
                        "cost_usd": round(sum(c.get("cost_usd") or 0 for c in calls), 4),
                        "calls": calls, "date": date.today().isoformat()})
            with open(path, "a") as fh:
                fh.write(json.dumps(rec, ensure_ascii=False) + "\n")
            fs = rec.get("final_score") or {}
            print(f"{key} {args.system} weeks={fs.get('n_weeks')} pass={fs.get('all_pass')} "
                  f"calls={len(calls)} {rec['wall_s']}s ${rec['cost_usd']} "
                  f"target={(rec.get('assessment') or {}).get('recommended_goal_time')} {err or ''}", flush=True)


def _p95(xs):
    xs = sorted(xs)
    k = 0.95 * (len(xs) - 1)
    f = int(k)
    return xs[f] + (xs[min(f + 1, len(xs) - 1)] - xs[f]) * (k - f)


def summarize() -> dict:
    rs = {p["id"]: p for p in runners()}
    load = lambda s: [json.loads(x) for x in (D / f"runs_{s}.jsonl").read_text().splitlines() if x] \
        if (D / f"runs_{s}.jsonl").exists() else []
    before, after, extra = load("before"), load("after"), load("assess")
    out = {"date": date.today().isoformat(), "runners": len(rs),
           "freeze": json.loads((D / "freeze.json").read_text()), "systems": {}, "per_runner": []}
    for name, rows in (("before", before), ("after", after)):
        ok = [r for r in rows if not r["error"]]
        walls, costs = [r["wall_s"] for r in ok], [r["cost_usd"] for r in ok]
        out["systems"][name] = {
            "plans": len(rows), "errors": len(rows) - len(ok),
            "all_checks_pass": sum(r["final_score"]["all_pass"] for r in ok),
            "length_drift": sum(not r["final_score"]["length_ok"] for r in ok),
            "safety_issues_total": sum(len(r["final_score"]["safety_issues"]) for r in ok),
            "llm_calls": sum(r["llm_calls"] for r in rows),
            "calls_per_plan_mean": round(statistics.mean([r["llm_calls"] for r in ok]), 2) if ok else None,
            "cost_per_plan_median": round(statistics.median(costs), 4) if ok else None,
            "cost_total": round(sum(r["cost_usd"] for r in rows), 4),
            "latency_median_s": round(statistics.median(walls), 1) if ok else None,
            "latency_p95_s": round(_p95(walls), 1) if ok else None,
            "models": sorted({c.get("model") or "" for r in rows for c in r["calls"]}),
        }
    ob = out["systems"].get("before")
    if ob:
        ob["draft_pass"] = sum(r["draft_score"]["all_pass"] for r in before if not r["error"])
        ob["draft_length_drift"] = sum(not r["draft_score"]["length_ok"] for r in before if not r["error"])
    oa = out["systems"].get("after")
    if oa:
        oa["first_draft_valid"] = sum(r["first_valid"] for r in after if not r["error"])
    spreads = []
    for rid, p in rs.items():
        targets = [r["assessment"].get("recommended_goal_time") for r in before + extra
                   if r["runner"] == rid and not r["error"]]
        mins = []
        for t in targets:
            try:
                mins.append(parse_hms(t))
            except Exception:
                pass
        det = assess_runner(p)["recommended_goal_time"]
        b = next((r for r in before if r["runner"] == rid and not r["error"]), None)
        a = next((r for r in after if r["runner"] == rid and not r["error"]), None)
        row = {"runner": rid, "race": p["goal_race"], "goal": p["goal_time"], "weeks": p["weeks"],
               "llm_targets": targets,
               "llm_spread_min": round(max(mins) - min(mins), 1) if len(mins) > 1 else None,
               "code_target": det,
               "before": b and {"n_weeks": b["final_score"]["n_weeks"], "all_pass": b["final_score"]["all_pass"],
                                "issues": b["final_score"]["safety_issues"], "revisions": b["revisions"],
                                "calls": b["llm_calls"], "wall_s": b["wall_s"], "cost_usd": b["cost_usd"],
                                "weekly_miles": [w.get("weekly_miles") for w in b["final"] if isinstance(w, dict)]},
               "after": a and {"n_weeks": a["final_score"]["n_weeks"], "all_pass": a["final_score"]["all_pass"],
                               "issues": a["final_score"]["safety_issues"], "repairs": a["repairs"],
                               "first_valid": a["first_valid"], "history": a["history"],
                               "calls": a["llm_calls"], "wall_s": a["wall_s"], "cost_usd": a["cost_usd"],
                               "weekly_miles": [w["weekly_miles"] for w in (a["weeks"] or [])]}}
        if row["llm_spread_min"] is not None:
            spreads.append(row["llm_spread_min"])
        out["per_runner"].append(row)
    out["assessment_spread"] = {"llm_runs_per_runner": 3, "llm_spread_min": spreads,
                                "llm_spread_median_min": statistics.median(spreads) if spreads else None,
                                "llm_spread_max_min": max(spreads) if spreads else None,
                                "code_spread_min": 0}
    out["llm_calls_total"] = sum(r["llm_calls"] for r in before + after + extra)
    out["cost_total_usd"] = round(sum(r["cost_usd"] for r in before + after + extra), 4)
    (D / "results.json").write_text(json.dumps(out, indent=1, ensure_ascii=False))
    print(json.dumps({k: v for k, v in out.items() if k != "per_runner"}, indent=1))
    return out


if __name__ == "__main__":
    main()
